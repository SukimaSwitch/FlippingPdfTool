"""Shared data models for worker orchestration payloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Literal, Mapping, Optional


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


def _copy_bbox(value: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    return dict(value) if value is not None else None


@dataclass(frozen=True)
class SourceDocument:
    bucket: str
    key: str

    @property
    def filename(self) -> str:
        return self.key.rsplit("/", 1)[-1]

    def to_dict(self) -> Dict[str, str]:
        return {"bucket": self.bucket, "key": self.key, "filename": self.filename}


@dataclass(frozen=True)
class ProductMatch:
    page_number: int
    sku: str
    product_url: Optional[str]
    figure_bbox: Optional[Dict[str, Any]] = None
    description_bbox: Optional[Dict[str, Any]] = None
    description_text: Optional[str] = None
    score: Optional[float] = None
    sku_source: Optional[str] = None

    @property
    def status(self) -> str:
        return "linked" if self.product_url else "unmatched"

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "pageNumber": self.page_number,
            "sku": self.sku,
            "status": self.status,
        }
        if self.product_url is not None:
            payload["productUrl"] = self.product_url
        if self.figure_bbox is not None:
            payload["figureBbox"] = self.figure_bbox
        if self.description_bbox is not None:
            payload["descriptionBbox"] = self.description_bbox
        if self.description_text is not None:
            payload["descriptionText"] = self.description_text
        if self.score is not None:
            payload["score"] = self.score
        if self.sku_source is not None:
            payload["skuSource"] = self.sku_source
        return payload

    @classmethod
    def from_summary_match(cls, *, page_number: int, payload: Mapping[str, Any]) -> "ProductMatch":
        return cls(
            page_number=page_number,
            sku=payload.get("sku", ""),
            product_url=payload.get("url"),
            figure_bbox=_copy_bbox(payload.get("figure_bbox")),
            description_bbox=_copy_bbox(payload.get("description_bbox")),
            description_text=payload.get("description_text"),
            score=payload.get("score"),
            sku_source=payload.get("sku_source"),
        )


@dataclass(frozen=True)
class UnmatchedSku:
    page_number: int
    sku: str

    def to_dict(self) -> Dict[str, Any]:
        return {"pageNumber": self.page_number, "sku": self.sku, "status": "unmatched"}


@dataclass(frozen=True)
class UnresolvedMatch:
    page_number: int
    sku: Optional[str]
    matched_sku: Optional[str] = None
    reason: Optional[str] = None
    figure_bbox: Optional[Dict[str, Any]] = None
    description_bbox: Optional[Dict[str, Any]] = None
    description_text: Optional[str] = None
    sku_source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"pageNumber": self.page_number, "status": "unresolved"}
        if self.sku is not None:
            payload["sku"] = self.sku
        if self.matched_sku is not None:
            payload["matchedSku"] = self.matched_sku
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.figure_bbox is not None:
            payload["figureBbox"] = self.figure_bbox
        if self.description_bbox is not None:
            payload["descriptionBbox"] = self.description_bbox
        if self.description_text is not None:
            payload["descriptionText"] = self.description_text
        if self.sku_source is not None:
            payload["skuSource"] = self.sku_source
        return payload

    @classmethod
    def from_summary_item(cls, *, page_number: int, payload: Mapping[str, Any]) -> "UnresolvedMatch":
        return cls(
            page_number=page_number,
            sku=payload.get("sku"),
            matched_sku=payload.get("matched_sku"),
            reason=payload.get("reason"),
            figure_bbox=_copy_bbox(payload.get("figure_bbox")),
            description_bbox=_copy_bbox(payload.get("description_bbox")),
            description_text=payload.get("description_text"),
            sku_source=payload.get("sku_source"),
        )


@dataclass(frozen=True)
class PageResult:
    page_number: int
    status: Optional[str]
    figure_count: int = 0
    description_candidate_count: int = 0
    link_count: int = 0
    unmatched_sku_count: int = 0
    unresolved_match_count: int = 0
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "pageNumber": self.page_number,
            "figureCount": self.figure_count,
            "descriptionCandidateCount": self.description_candidate_count,
            "linkCount": self.link_count,
            "unmatchedSkuCount": self.unmatched_sku_count,
            "unresolvedMatchCount": self.unresolved_match_count,
        }
        if self.status is not None:
            payload["status"] = self.status
        if self.error_message is not None:
            payload["errorMessage"] = self.error_message
        return payload

    @classmethod
    def from_summary(cls, summary: Mapping[str, Any]) -> "PageResult":
        return cls(
            page_number=summary.get("page", 0),
            status=summary.get("status"),
            figure_count=summary.get("figure_count", 0),
            description_candidate_count=summary.get("description_candidate_count", 0),
            link_count=summary.get("links_added", 0),
            unmatched_sku_count=len(summary.get("unmatched_skus", [])),
            unresolved_match_count=len(summary.get("unresolved_matches", [])),
            error_message=summary.get("error"),
        )


@dataclass(frozen=True)
class PersistedPageArtifacts:
    page_results: List[PageResult]
    product_matches: List[ProductMatch]
    unmatched_skus: List[UnmatchedSku]
    unresolved_matches: List[UnresolvedMatch]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pageResults": [page_result.to_dict() for page_result in self.page_results],
            "productMatches": [product_match.to_dict() for product_match in self.product_matches],
            "unmatchedSkus": [unmatched_sku.to_dict() for unmatched_sku in self.unmatched_skus],
            "unresolvedMatches": [unresolved_match.to_dict() for unresolved_match in self.unresolved_matches],
        }

    @classmethod
    def from_page_summaries(cls, page_summaries: List[Mapping[str, Any]]) -> "PersistedPageArtifacts":
        page_results: List[PageResult] = []
        product_matches: List[ProductMatch] = []
        unmatched_skus: List[UnmatchedSku] = []
        unresolved_matches: List[UnresolvedMatch] = []

        for summary in page_summaries:
            page_number = summary.get("page", 0)
            page_results.append(PageResult.from_summary(summary))
            for match in summary.get("matches", []):
                product_matches.append(ProductMatch.from_summary_match(page_number=page_number, payload=match))
            for sku in summary.get("unmatched_skus", []):
                unmatched_skus.append(UnmatchedSku(page_number=page_number, sku=sku))
            for unresolved in summary.get("unresolved_matches", []):
                unresolved_matches.append(UnresolvedMatch.from_summary_item(page_number=page_number, payload=unresolved))

        return cls(
            page_results=page_results,
            product_matches=product_matches,
            unmatched_skus=unmatched_skus,
            unresolved_matches=unresolved_matches,
        )


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
    source_document: Optional[SourceDocument] = None
    correlation_id: Optional[str] = None
    requested_by: Optional[str] = None
    notification_group: Optional[str] = None
    flipbook_profile: Optional[str] = None

    @property
    def filename(self) -> str:
        if self.source_document is not None:
            return self.source_document.filename
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
            source_document=SourceDocument(
                bucket=payload["sourceBucket"],
                key=payload["sourceKey"],
            ),
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
    unresolved_match_count: Optional[int] = None
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
        if self.unresolved_match_count is not None:
            payload["unresolvedMatchCount"] = self.unresolved_match_count
        if self.link_count is not None:
            payload["linkCount"] = self.link_count
        return payload


SUPPORTED_SITE_PREFIXES = tuple(_SITE_DOMAIN_BY_PREFIX)
