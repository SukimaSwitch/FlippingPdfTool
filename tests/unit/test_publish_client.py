import unittest

from src.worker.publish_client import FlipbookPublishClient, build_publication_request


class FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response_payload) -> None:
        self.response_payload = response_payload
        self.requests = []

    def post(self, url: str, *, json, headers, timeout: int):
        self.requests.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeResponse(self.response_payload)


class FlipbookPublishClientTests(unittest.TestCase):
    def test_build_publication_request_matches_contract_fields(self) -> None:
        payload = build_publication_request(
            job_id="job-publish-001",
            site_prefix="currentcatalog",
            pdf_bucket="cmg-catalog-book",
            pdf_key="output/currentcatalog/catalog.pdf",
            filename="catalog.pdf",
        )

        self.assertEqual(
            payload,
            {
                "jobId": "job-publish-001",
                "sitePrefix": "currentcatalog",
                "pdfBucket": "cmg-catalog-book",
                "pdfKey": "output/currentcatalog/catalog.pdf",
                "filename": "catalog.pdf",
            },
        )

    def test_publish_pdf_posts_expected_payload_and_returns_flipbook_url(self) -> None:
        session = FakeSession(
            {
                "publicationStatus": "published",
                "flipbookUrl": "https://flipbook.example.com/books/12345",
            }
        )
        client = FlipbookPublishClient(
            api_url="https://flipbook.example.com/api/publish",
            api_key="secret-token",
            session=session,
        )

        result = client.publish_pdf(
            job_id="job-publish-001",
            site_prefix="currentcatalog",
            pdf_bucket="cmg-catalog-book",
            pdf_key="output/currentcatalog/catalog.pdf",
            filename="catalog.pdf",
        )

        self.assertEqual(session.requests[0]["url"], "https://flipbook.example.com/api/publish")
        self.assertEqual(session.requests[0]["json"]["pdfKey"], "output/currentcatalog/catalog.pdf")
        self.assertEqual(session.requests[0]["headers"]["Authorization"], "Bearer secret-token")
        self.assertEqual(result["publicationStatus"], "published")
        self.assertEqual(result["flipbookUrl"], "https://flipbook.example.com/books/12345")

    def test_publish_pdf_requires_api_url(self) -> None:
        client = FlipbookPublishClient()

        with self.assertRaisesRegex(ValueError, "Flipbook API URL is required"):
            client.publish_pdf(
                job_id="job-publish-001",
                site_prefix="currentcatalog",
                pdf_bucket="cmg-catalog-book",
                pdf_key="output/currentcatalog/catalog.pdf",
                filename="catalog.pdf",
            )


if __name__ == "__main__":
    unittest.main()