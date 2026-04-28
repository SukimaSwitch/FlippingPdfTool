"""Shared data models for worker orchestration payloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Literal, Optional


SitePrefix = Literal["currentcatalog", "colorfulimages", "lillianvernon"]
WorkerStatus = Literal["processed", "failed"]
FailureStage = Literal["download", "processing", "upload"]

_SITE_DOMAIN_BY_PREFIX: Dict[SitePrefix, str] = {
    "currentcatalog": "https://www.currentcatalog.com",
    "colorfulimages": "https://www.colorfulimages.com",
    "lillianvernon": "https://www.lillianvernon.com",
}


def _parse_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized)


@dataclass(frozen=True)
class SiteConfiguration:
    site_prefix: SitePrefix
    public_domain: str
    magento_store_code: str
    output_bucket: str = "cmg-catalog-book"

    @property
    def output_prefix(self) -> str:
        return f"output/{self.site_prefix}/"

    @property
    def magento_product_lookup_route(self) -> str:
        return (
            "/rest/"
            f"{self.magento_store_code}"
            "/V1/products?searchCriteria[filterGroups][0][filters][0][field]=sku"
            "&searchCriteria[filterGroups][0][filters][0][value]={sku}"
            "&searchCriteria[filterGroups][0][filters][0][conditionType]=like"
        )

    def output_key_for(self, filename: str) -> str:
        return f"{self.output_prefix}{filename}"

    def to_dict(self) -> Dict[str, str]:
        return {
            "sitePrefix": self.site_prefix,
            "publicDomain": self.public_domain,
            "magentoStoreCode": self.magento_store_code,
            "outputBucket": self.output_bucket,
            "outputKey": self.output_prefix,
            "magentoProductLookupRoute": self.magento_product_lookup_route,
        }

    @classmethod
    def for_prefix(cls, site_prefix: SitePrefix) -> "SiteConfiguration":
        return cls(
            site_prefix=site_prefix,
            public_domain=_SITE_DOMAIN_BY_PREFIX[site_prefix],
            magento_store_code=site_prefix,
        )


@dataclass(frozen=True)
class WorkerJob:
    job_id: str
    source_bucket: str
    source_key: str
    triggered_at: datetime
    output_bucket: str
    output_key: str
    artifact_bucket: str
    artifact_prefix: str
    site_configuration: SiteConfiguration
    correlation_id: Optional[str] = None
    requested_by: Optional[str] = None
    notification_group: Optional[str] = None
    flipbook_profile: Optional[str] = None

    @property
    def filename(self) -> str:
        return self.source_key.rsplit("/", 1)[-1]

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "jobId": self.job_id,
            "sourceBucket": self.source_bucket,
            "sourceKey": self.source_key,
            "triggeredAt": self.triggered_at.isoformat(),
            "outputBucket": self.output_bucket,
            "outputKey": self.output_key,
            "artifactBucket": self.artifact_bucket,
            "artifactPrefix": self.artifact_prefix,
            "siteConfiguration": self.site_configuration.to_dict(),
        }
        if self.correlation_id:
            payload["correlationId"] = self.correlation_id
        if self.requested_by:
            payload["requestedBy"] = self.requested_by
        if self.notification_group:
            payload["notificationGroup"] = self.notification_group
        if self.flipbook_profile:
            payload["flipbookProfile"] = self.flipbook_profile
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "WorkerJob":
        site_payload = payload["siteConfiguration"]
        site_configuration = SiteConfiguration(
            site_prefix=site_payload["sitePrefix"],
            public_domain=site_payload["publicDomain"],
            magento_store_code=site_payload["magentoStoreCode"],
            output_bucket=site_payload.get("outputBucket", payload["outputBucket"]),
        )
        return cls(
            job_id=payload["jobId"],
            source_bucket=payload["sourceBucket"],
            source_key=payload["sourceKey"],
            triggered_at=_parse_datetime(payload["triggeredAt"]),
            output_bucket=payload["outputBucket"],
            output_key=payload["outputKey"],
            artifact_bucket=payload["artifactBucket"],
            artifact_prefix=payload["artifactPrefix"],
            site_configuration=site_configuration,
            correlation_id=payload.get("correlationId"),
            requested_by=payload.get("requestedBy"),
            notification_group=payload.get("notificationGroup"),
            flipbook_profile=payload.get("flipbookProfile"),
        )


@dataclass(frozen=True)
class WorkerResult:
    job_id: str
    status: WorkerStatus
    site_prefix: SitePrefix
    artifact_prefix: str
    worker_run_id: Optional[str] = None
    output_bucket: Optional[str] = None
    output_key: Optional[str] = None
    failure_stage: Optional[FailureStage] = None
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    page_count: Optional[int] = None
    matched_sku_count: Optional[int] = None
    unmatched_sku_count: Optional[int] = None
    link_count: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "jobId": self.job_id,
            "status": self.status,
            "sitePrefix": self.site_prefix,
            "artifactPrefix": self.artifact_prefix,
        }
        if self.worker_run_id is not None:
            payload["workerRunId"] = self.worker_run_id
        if self.output_bucket is not None:
            payload["outputBucket"] = self.output_bucket
        if self.output_key is not None:
            payload["outputKey"] = self.output_key
        if self.failure_stage is not None:
            payload["failureStage"] = self.failure_stage
        if self.failure_code is not None:
            payload["failureCode"] = self.failure_code
        if self.failure_message is not None:
            payload["failureMessage"] = self.failure_message
        if self.page_count is not None:
            payload["pageCount"] = self.page_count
        if self.matched_sku_count is not None:
            payload["matchedSkuCount"] = self.matched_sku_count
        if self.unmatched_sku_count is not None:
            payload["unmatchedSkuCount"] = self.unmatched_sku_count
        if self.link_count is not None:
            payload["linkCount"] = self.link_count
        return payload


SUPPORTED_SITE_PREFIXES = tuple(_SITE_DOMAIN_BY_PREFIX)
