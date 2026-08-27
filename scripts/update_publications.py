#!/usr/bin/env python3

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests


ORCID_ID = "0000-0003-4012-9557"

ORCID_API = "https://pub.orcid.org/v3.0"

OUTPUT_FILE = Path("data/publications.json")

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "YAN-LAB-Publications/1.0"
}


def get_access_token():
    """Get an ORCID Public API access token."""

    client_id = os.environ.get("ORCID_CLIENT_ID")
    client_secret = os.environ.get("ORCID_CLIENT_SECRET")

    if not client_id or not client_secret:
        print(
            "ERROR: ORCID_CLIENT_ID and ORCID_CLIENT_SECRET "
            "are not configured."
        )
        sys.exit(1)

    response = requests.post(
        "https://orcid.org/oauth/token",
        headers={
            "Accept": "application/json"
        },
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "scope": "/read-public"
        },
        timeout=30
    )

    response.raise_for_status()

    return response.json()["access_token"]


def safe_value(value):
    """Return an empty string instead of failing on null values."""

    if value is None:
        return ""

    if isinstance(value, dict):
        return value.get("value", "") or ""

    return str(value)


def clean_text(value):
    """Clean whitespace safely."""

    value = safe_value(value)

    return " ".join(value.split())


def get_works(token):
    """Download the public ORCID works record."""

    url = f"{ORCID_API}/{ORCID_ID}/works"

    response = requests.get(
        url,
        headers={
            **HEADERS,
            "Authorization": f"Bearer {token}"
        },
        timeout=30
    )

    response.raise_for_status()

    return response.json()


def extract_year(summary):
    """Extract publication year safely."""

    publication_date = summary.get("publication-date")

    if not publication_date:
        return ""

    year = publication_date.get("year")

    if not year:
        return ""

    return clean_text(year)


def extract_external_id(external_ids, wanted_type):
    """Find DOI, PMID, or other external identifier."""

    if not external_ids:
        return ""

    for item in external_ids:

        if not isinstance(item, dict):
            continue

        id_type = clean_text(
            item.get("external-id-type")
        )

        id_value = clean_text(
            item.get("external-id-value")
        )

        if id_type.lower() == wanted_type.lower():
            return id_value

    return ""


def extract_url(summary):
    """Extract ORCID-provided URL safely."""

    url_data = summary.get("url")

    if not url_data:
        return ""

    return clean_text(url_data)


def extract_publication(work_group):
    """Convert one ORCID work group into a clean publication."""

    summaries = work_group.get("work-summary") or []

    if not summaries:
        return None

    summary = summaries[0]

    if not isinstance(summary, dict):
        return None

    # ----------------------------------------
    # Title
    # ----------------------------------------

    title_data = summary.get("title") or {}

    if not isinstance(title_data, dict):
        title_data = {}

    title_data_inner = (
        title_data.get("title") or {}
    )

    title = clean_text(
        title_data_inner
    )

    if not title:
        return None

    # ----------------------------------------
    # Publication year
    # ----------------------------------------

    year = extract_year(summary)

    # ----------------------------------------
    # Journal
    # ----------------------------------------

    journal_data = summary.get(
        "journal-title"
    )

    journal = clean_text(
        journal_data
    )

    # ----------------------------------------
    # External identifiers
    # ----------------------------------------

    external_ids_data = (
        summary.get("external-ids") or {}
    )

    if isinstance(external_ids_data, dict):

        external_ids = (
            external_ids_data.get(
                "external-id"
            ) or []
        )

    else:

        external_ids = []

    doi = extract_external_id(
        external_ids,
        "doi"
    )

    pmid = extract_external_id(
        external_ids,
        "pmid"
    )

    # ----------------------------------------
    # URL
    # ----------------------------------------

    url = extract_url(summary)

    if doi:

        doi_url = (
            f"https://doi.org/{doi}"
        )

    elif url:

        doi_url = url

    else:

        doi_url = ""

    # ----------------------------------------
    # PubMed URL
    # ----------------------------------------

    if pmid:

        pubmed_url = (
            f"https://pubmed.ncbi.nlm.nih.gov/"
            f"{pmid}/"
        )

    else:

        pubmed_url = ""

    # ----------------------------------------
    # Work type
    # ----------------------------------------

    work_type = clean_text(
        summary.get("type")
    )

    return {
        "title": title,
        "year": year,
        "journal": journal,
        "doi": doi,
        "doi_url": doi_url,
        "pmid": pmid,
        "pubmed_url": pubmed_url,
        "url": url,
        "type": work_type
    }


def publication_key(publication):
    """Create a stable identifier for deduplication."""

    doi = publication.get("doi")

    if doi:
        return (
            "doi:"
            + doi.lower().strip()
        )

    pmid = publication.get("pmid")

    if pmid:
        return (
            "pmid:"
            + pmid.lower().strip()
        )

    title = publication.get("title", "")

    return (
        "title:"
        + title.lower().strip()
    )


def build_publication_list(data):

    publications = []

    groups = data.get("group") or []

    for group in groups:

        try:

            publication = (
                extract_publication(group)
            )

            if publication:
                publications.append(
                    publication
                )

        except Exception as error:

            print(
                "WARNING: Could not process "
                f"one ORCID work: {error}"
            )

            continue

    # ----------------------------------------
    # Deduplicate
    # ----------------------------------------

    unique = {}

    for publication in publications:

        key = publication_key(
            publication
        )

        unique[key] = publication

    publications = list(
        unique.values()
    )

    # ----------------------------------------
    # Newest first
    # ----------------------------------------

    publications.sort(
        key=lambda item: (
            item.get("year") or "0000",
            item.get("title") or ""
        ),
        reverse=True
    )

    return publications


def main():

    print(
        "Updating YAN LAB publications "
        f"from ORCID {ORCID_ID}"
    )

    token = get_access_token()

    print("Successfully authenticated with ORCID.")

    works = get_works(token)

    print(
        f"ORCID returned "
        f"{len(works.get('group', []))} work groups."
    )

    publications = build_publication_list(
        works
    )

    print(
        f"Processed {len(publications)} "
        "publications."
    )

    output = {

        "lab": "YAN LAB",

        "orcid": ORCID_ID,

        "source": "ORCID",

        "google_scholar": (
            "https://scholar.google.com/"
            "citations?user=l6LJdzAAAAAJ&hl=en"
        ),

        "updated": datetime.now(
            timezone.utc
        ).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),

        "publication_count": len(
            publications
        ),

        "publications": publications
    }

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False
        )

        file.write("\n")

    print(
        f"Successfully saved publications "
        f"to {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
