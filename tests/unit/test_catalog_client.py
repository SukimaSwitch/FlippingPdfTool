import unittest

from src.worker.catalog_client import MagentoCatalogClient
from src.worker.models import SiteConfiguration


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

    def get(self, url: str, *, timeout: int):
        self.requests.append({"url": url, "timeout": timeout})
        return FakeResponse(self.response_payload)


class MagentoCatalogClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.site_configuration = SiteConfiguration.for_prefix("currentcatalog")

    def test_lookup_product_match_returns_html_url_for_exact_sku_match(self) -> None:
        session = FakeSession(
            {
                "items": [
                    {
                        "sku": "123456",
                        "custom_attributes": [
                            {"attribute_code": "url_key", "value": "spring-floral-mug"}
                        ],
                    },
                    {
                        "sku": "123456-B",
                        "custom_attributes": [
                            {"attribute_code": "url_key", "value": "wrong-product"}
                        ],
                    },
                ]
            }
        )
        client = MagentoCatalogClient(session=session)

        result = client.lookup_product_match(self.site_configuration, "123456")

        self.assertEqual(
            session.requests[0]["url"],
            "https://www.currentcatalog.com/rest/currentcatalog/V1/products?searchCriteria[filterGroups][0][filters][0][field]=sku&searchCriteria[filterGroups][0][filters][0][value]=123456&searchCriteria[filterGroups][0][filters][0][conditionType]=like",
        )
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.matched_sku, "123456")
        self.assertEqual(result.url_key, "spring-floral-mug")
        self.assertEqual(result.product_url, "https://www.currentcatalog.com/spring-floral-mug.html")

    def test_lookup_product_match_ignores_partial_only_candidates(self) -> None:
        session = FakeSession(
            {
                "items": [
                    {
                        "sku": "123456-B",
                        "custom_attributes": [
                            {"attribute_code": "url_key", "value": "wrong-product"}
                        ],
                    }
                ]
            }
        )
        client = MagentoCatalogClient(session=session)

        result = client.lookup_product_match(self.site_configuration, "123456")

        self.assertEqual(result.status, "unmatched")
        self.assertIsNone(result.product_url)
        self.assertIsNone(result.matched_sku)
        self.assertIsNone(result.unresolved_reason)

    def test_lookup_product_match_records_exact_match_without_url_key_as_unresolved(self) -> None:
        session = FakeSession({"items": [{"sku": "123456", "custom_attributes": []}]})
        client = MagentoCatalogClient(session=session)

        result = client.lookup_product_match(self.site_configuration, "123456")

        self.assertEqual(result.status, "unresolved")
        self.assertEqual(result.matched_sku, "123456")
        self.assertEqual(result.unresolved_reason, "missing_url_key")
        self.assertIsNone(result.product_url)


if __name__ == "__main__":
    unittest.main()