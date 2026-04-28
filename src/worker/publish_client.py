"""Flipbook publication client for processed PDFs."""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests


def build_publication_request(
    *,
    job_id: str,
    site_prefix: str,
    pdf_bucket: str,
    pdf_key: str,
    filename: str,
) -> Dict[str, str]:
    return {
        "jobId": job_id,
        "sitePrefix": site_prefix,
        "pdfBucket": pdf_bucket,
        "pdfKey": pdf_key,
        "filename": filename,
    }


class FlipbookPublishClient:
    def __init__(self, *, api_url: Optional[str] = None, api_key: Optional[str] = None, session: Optional[requests.Session] = None):
        self._api_url = api_url
        self._api_key = api_key
        self._session = session or requests.Session()

    def publish_pdf(
        self,
        *,
        job_id: str,
        site_prefix: str,
        pdf_bucket: str,
        pdf_key: str,
        filename: str,
    ) -> Dict[str, str]:
        payload = build_publication_request(
            job_id=job_id,
            site_prefix=site_prefix,
            pdf_bucket=pdf_bucket,
            pdf_key=pdf_key,
            filename=filename,
        )
        if not self._api_url:
            raise ValueError("Flipbook API URL is required for publication")

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        response = self._session.post(self._api_url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()
        return {
            "jobId": job_id,
            "publicationStatus": data.get("publicationStatus", "published"),
            "flipbookUrl": data["flipbookUrl"],
        }