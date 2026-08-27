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
    """
    Obtain an ORCID Public API /read-public token.

    Required GitHub Actions secrets:
        ORCID_CLIENT_ID
        ORCID_CLIENT_SECRET
    """

    client_id = os.environ.get("ORCID_CLIENT_ID")
    client_secret = os.environ.get("ORCID_CLIENT_SECRET")

    if not client_id or not client_secret:
        print(
            "ERROR: ORCID_CLIENT_ID and ORCID_CLIENT_SECRET "
            "must be configured as GitHub Secrets."
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

    token_data = response.json()

    return token_data["access_token"]


def get_works(token):
    """
    Retrieve all public works from the ORCID record.
    """

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


def clean_text(value):
    if not value:
        return ""

    return " ".join(str(value).split())


def extract_year(summary):
    publication_date = summary.get("publication-date")

    if not publication_date:
        return ""

    year = publication_date.get("year")

    if not year:
        return ""

    return str(year.get("value", ""))


def extract_external_id(external_ids, id_type):
    for item in external_ids or []:
        external_id = item.get("external-id-value", "")
        external_id_type = item.get("external-id-type", "")

        if external_id_type.lower() == id_type.lower():
            return external_id

    return ""


def extract_url(summary):
    url_data = summary.get("url")

    if not url_data:
        return ""

    return url_data.get("value", "") or ""


def extract_publication(work_group):
    summaries = work_group.get("work-summary", [])

    if not summaries:
        return None

    # ORCID normally provides a preferred/first summary.
    summary = summaries[0]

    title_data = summary.get("title", {})
    title = clean_text(
        title_data.get("title", {}).get("value", "")
    )

    if not title:
        return None

    external_ids = summary.get("external-ids", {}).get(
        "external-id",
        []
    )

    doi = extract_external_id(
        external_ids,
        "doi"
    )

    pmid = extract_external_id(
        external_ids,
        "pmid"
    )

    year = extract_year(summary)

    journal = clean_text(
        summary.get("journal-title", {}).get("value", "")
    )

    work_type = summary.get("type", "")

    url = extract_url(summary)

    if doi:
        doi_url = f"https://doi.org/{doi}"
    elif url:
        doi_url = url
    else:
        doi_url = ""

    return {
        "title": title,
        "year": year,
        "journal": journal,
        "doi": doi,
        "doi_url": doi_url,
        "pmid": pmid,
        "pubmed_url": (
            f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            if pmid
            else ""
        ),
        "url": url,
        "type": work_type
    }


def build_publication_list(data):
    publications = []

    for group in data.get("group", []):
        publication = extract_publication(group)

        if publication:
            publications.append(publication)

    # Remove duplicate records.
    unique = {}

    for publication in publications:
        key = (
            publication["doi"].lower()
            if publication["doi"]
            else publication["title"].lower()
        )

        unique[key] = publication

    publications = list(unique.values())

    # Newest publications first.
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
        f"Updating YAN LAB publications from ORCID "
        f"{ORCID_ID}"
    )

    token = get_access_token()

    works = get_works(token)

    publications = build_publication_list(works)

    output = {
        "orcid": ORCID_ID,
        "source": "ORCID",
        "google_scholar": (
            "https://scholar.google.com/"
            "citations?user=l6LJdzAAAAAJ&hl=en"
        ),
        "updated": datetime.now(
            timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "publication_count": len(publications),
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

    print(
        f"Successfully saved {len(publications)} "
        f"publications to {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
