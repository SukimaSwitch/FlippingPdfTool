import unittest
from json import JSONDecodeError

from src.worker.catalog_client import MagentoCatalogClient
from src.worker.models import SiteConfiguration


class FakeResponse:
    def __init__(self, payload, status_code: int = 200, text: str | None = None) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text if text is not None else (payload if isinstance(payload, str) else "")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, response_payload, token_payload: object = "generated-admin-token", token_text: str | None = None) -> None:
        self.response_payload = response_payload
        self.token_payload = token_payload
        self.token_text = token_text
        self.requests = []
        self.headers = {}

    def get(self, url: str, *, timeout: int):
        self.requests.append({"method": "GET", "url": url, "timeout": timeout, "headers": dict(self.headers)})
        return FakeResponse(self.response_payload)

    def post(self, url: str, *, data: str, headers: dict, timeout: int):
        self.requests.append(
            {
                "method": "POST",
                "url": url,
                "data": data,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeResponse(self.token_payload, text=self.token_text)


class MagentoCatalogClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.site_configuration = SiteConfiguration.for_prefix("currentcatalog")
        self.colorfulimages_site_configuration = SiteConfiguration.for_prefix("colorfulimages")
        self.lillianvernon_site_configuration = SiteConfiguration.for_prefix("lillianvernon")

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
        self.assertEqual(result.product_url, "https://www.currentcatalog.com/buy/spring-floral-mug.html")

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

    def test_lookup_product_match_fetches_admin_token_when_credentials_are_provided(self) -> None:
        session = FakeSession(
            {
                "items": [
                    {
                        "sku": "123456",
                        "custom_attributes": [
                            {"attribute_code": "url_key", "value": "spring-floral-mug"}
                        ],
                    }
                ]
            }
        )
        client = MagentoCatalogClient(
            session=session,
            base_url="https://api.cmgdev.com",
            username="user",
            password="pass",
        )

        result = client.lookup_product_match(self.site_configuration, "123456")

        self.assertEqual(session.requests[0]["method"], "POST")
        self.assertEqual(session.requests[0]["url"], "https://api.cmgdev.com/rest/V1/integration/admin/token")
        self.assertEqual(
            session.requests[0]["data"],
            "<login><username>user</username><password>pass</password></login>",
        )
        self.assertEqual(session.requests[1]["method"], "GET")
        self.assertEqual(session.requests[1]["headers"]["Authorization"], "Bearer generated-admin-token")
        self.assertEqual(result.product_url, "https://www.currentcatalog.com/buy/spring-floral-mug.html")

    def test_lookup_product_match_reuses_existing_admin_token_after_first_exchange(self) -> None:
        session = FakeSession(
            {
                "items": [
                    {
                        "sku": "123456",
                        "custom_attributes": [
                            {"attribute_code": "url_key", "value": "spring-floral-mug"}
                        ],
                    }
                ]
            }
        )
        client = MagentoCatalogClient(
            session=session,
            base_url="https://api.cmgdev.com",
            username="user",
            password="pass",
        )

        client.lookup_product_match(self.site_configuration, "123456")
        client.lookup_product_match(self.site_configuration, "123456")

        post_requests = [request for request in session.requests if request["method"] == "POST"]
        get_requests = [request for request in session.requests if request["method"] == "GET"]
        self.assertEqual(len(post_requests), 1)
        self.assertEqual(len(get_requests), 2)

    def test_lookup_product_match_parses_xml_admin_token_response(self) -> None:
        session = FakeSession(
            {
                "items": [
                    {
                        "sku": "123456",
                        "custom_attributes": [
                            {"attribute_code": "url_key", "value": "spring-floral-mug"}
                        ],
                    }
                ]
            },
            token_payload=JSONDecodeError("Expecting value", "", 0),
            token_text="<?xml version=\"1.0\" encoding=\"utf-8\"?><response>xml-admin-token</response>",
        )
        client = MagentoCatalogClient(
            session=session,
            base_url="https://api.cmgdev.com",
            username="user",
            password="pass",
        )

        client.lookup_product_match(self.site_configuration, "123456")

        self.assertEqual(session.requests[1]["headers"]["Authorization"], "Bearer xml-admin-token")

    def test_lookup_product_match_uses_token_provider_when_present(self) -> None:
        session = FakeSession(
            {
                "items": [
                    {
                        "sku": "123456",
                        "custom_attributes": [
                            {"attribute_code": "url_key", "value": "spring-floral-mug"}
                        ],
                    }
                ]
            }
        )
        client = MagentoCatalogClient(
            session=session,
            token_provider=lambda: "secret-bearer-token",
        )

        client.lookup_product_match(self.site_configuration, "123456")

        self.assertEqual(len(session.requests), 1)
        self.assertEqual(session.requests[0]["headers"]["Authorization"], "Bearer secret-bearer-token")

    def test_build_url_template_uses_site_specific_product_paths(self) -> None:
        client = MagentoCatalogClient()

        self.assertEqual(
            client.build_url_template(self.site_configuration),
            "https://www.currentcatalog.com/buy/{url_key}.html",
        )
        self.assertEqual(
            client.build_url_template(self.colorfulimages_site_configuration),
            "https://www.colorfulimages.com/buy/{url_key}.html",
        )
        self.assertEqual(
            client.build_url_template(self.lillianvernon_site_configuration),
            "https://www.lillianvernon.com/goods/{url_key}.html",
        )


if __name__ == "__main__":
    unittest.main()