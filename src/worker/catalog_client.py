"""Magento catalog lookup adapter for worker jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

import requests

from .models import SiteConfiguration


LookupStatus = Literal["matched", "unmatched", "unresolved"]


@dataclass(frozen=True)
class ProductLookupResult:
    detected_sku: str
    status: LookupStatus
    matched_sku: Optional[str] = None
    url_key: Optional[str] = None
    product_url: Optional[str] = None
    unresolved_reason: Optional[str] = None
    product: Optional[Dict[str, Any]] = None


class MagentoCatalogClient:
    def __init__(
        self,
        session: Optional[requests.Session] = None,
        timeout: int = 30,
        base_url: Optional[str] = None,
        auth_headers: Optional[Dict[str, str]] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self._session = session or requests.Session()
        self._timeout = timeout
        self._base_url = base_url.rstrip("/") if isinstance(base_url, str) and base_url.strip() else None
        if auth_headers and hasattr(self._session, "headers"):
            self._session.headers.update(auth_headers)
        if username and password and hasattr(self._session, "auth"):
            self._session.auth = (username, password)

    def build_search_url(self, site_configuration: SiteConfiguration, sku: str) -> str:
        base_url = self._base_url or site_configuration.public_domain
        return f"{base_url}{site_configuration.magento_product_lookup_route.format(sku=sku)}"

    def build_url_template(self, site_configuration: SiteConfiguration) -> str:
        return f"{site_configuration.public_domain}/{{url_key}}.html"

    def extract_url_key(self, product: Dict[str, Any]) -> Optional[str]:
        for attribute in product.get("custom_attributes", []):
            if attribute.get("attribute_code") != "url_key":
                continue
            url_key = attribute.get("value")
            if isinstance(url_key, str) and url_key.strip():
                return url_key.strip()
        return None

    def lookup_product_match(self, site_configuration: SiteConfiguration, sku: str) -> ProductLookupResult:
        response = self._session.get(self.build_search_url(site_configuration, sku), timeout=self._timeout)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items", [])

        exact_match = next((item for item in items if item.get("sku") == sku), None)
        if exact_match is None:
            return ProductLookupResult(detected_sku=sku, status="unmatched")

        url_key = self.extract_url_key(exact_match)
        if not url_key:
            return ProductLookupResult(
                detected_sku=sku,
                status="unresolved",
                matched_sku=sku,
                unresolved_reason="missing_url_key",
                product=exact_match,
            )

        return ProductLookupResult(
            detected_sku=sku,
            status="matched",
            matched_sku=sku,
            url_key=url_key,
            product_url=self.build_url_template(site_configuration).format(url_key=url_key),
            product=exact_match,
        )

    def lookup_product_url(self, site_configuration: SiteConfiguration, sku: str) -> Optional[str]:
        return self.lookup_product_match(site_configuration, sku).product_url


__all__ = ["MagentoCatalogClient", "ProductLookupResult"]