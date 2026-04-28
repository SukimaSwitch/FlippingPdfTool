"""Magento catalog lookup adapter for worker jobs."""

from __future__ import annotations

from typing import Optional

import requests

from .models import SiteConfiguration


class MagentoCatalogClient:
    def __init__(self, session: Optional[requests.Session] = None, timeout: int = 30):
        self._session = session or requests.Session()
        self._timeout = timeout

    def build_url_template(self, site_configuration: SiteConfiguration) -> str:
        return f"{site_configuration.public_domain}/sku/{{sku}}"

    def lookup_product_url(self, site_configuration: SiteConfiguration, sku: str) -> Optional[str]:
        template = self.build_url_template(site_configuration)
        return template.format(sku=sku)