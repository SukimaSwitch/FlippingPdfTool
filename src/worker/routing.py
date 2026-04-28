"""Site-prefix validation and output routing helpers for worker jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, Union, cast

from .models import SUPPORTED_SITE_PREFIXES, SiteConfiguration, SitePrefix, WorkerJob


EXPECTED_SOURCE_BUCKET = "cmg-catalog-book"
ARTIFACT_PREFIX_TEMPLATE = "artifacts/{job_id}/"
ROUTING_FAILURE_STAGE = "ingest-routing"
ROUTING_ACCEPTED = "accepted"
ROUTING_REJECTED = "rejected"


@dataclass(frozen=True)
class AcceptedRouting:
    job_id: str
    site_configuration: SiteConfiguration
    output_key: str
    routing_status: Literal["accepted"] = ROUTING_ACCEPTED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jobId": self.job_id,
            "routingStatus": self.routing_status,
            "siteConfiguration": {
                **self.site_configuration.to_dict(),
                "outputBucket": self.site_configuration.output_bucket,
                "outputKey": self.output_key,
            },
        }


@dataclass(frozen=True)
class RejectedRouting:
    job_id: str
    failure_code: str
    failure_message: str
    routing_status: Literal["rejected"] = ROUTING_REJECTED
    failure_stage: Literal["ingest-routing"] = ROUTING_FAILURE_STAGE

    def to_dict(self) -> Dict[str, str]:
        return {
            "jobId": self.job_id,
            "routingStatus": self.routing_status,
            "failureStage": self.failure_stage,
            "failureCode": self.failure_code,
            "failureMessage": self.failure_message,
        }


RoutingDecision = Union[AcceptedRouting, RejectedRouting]


def parse_site_prefix(source_key: str) -> Optional[SitePrefix]:
    parts = source_key.split("/", 2)
    if len(parts) < 3 or parts[0] != "input":
        return None

    site_prefix = parts[1]
    if site_prefix not in SUPPORTED_SITE_PREFIXES:
        return None

    return cast(SitePrefix, site_prefix)


def route_source_object(job_id: str, source_bucket: str, source_key: str) -> RoutingDecision:
    if source_bucket != EXPECTED_SOURCE_BUCKET:
        return RejectedRouting(
            job_id=job_id,
            failure_code="unknown-bucket",
            failure_message=(
                f"Unsupported source bucket '{source_bucket}'. Expected '{EXPECTED_SOURCE_BUCKET}'."
            ),
        )

    if not source_key.endswith(".pdf"):
        return RejectedRouting(
            job_id=job_id,
            failure_code="invalid-file-type",
            failure_message=f"Source key '{source_key}' must reference a PDF under input/<site-prefix>/.",
        )

    site_prefix = parse_site_prefix(source_key)
    if site_prefix is None:
        return RejectedRouting(
            job_id=job_id,
            failure_code="unknown-prefix",
            failure_message=f"Unsupported site prefix in key {source_key}",
        )

    filename = source_key.rsplit("/", 1)[-1]
    site_configuration = SiteConfiguration.for_prefix(site_prefix)
    return AcceptedRouting(
        job_id=job_id,
        site_configuration=site_configuration,
        output_key=site_configuration.output_key_for(filename),
    )


def build_worker_job(
    *,
    job_id: str,
    source_bucket: str,
    source_key: str,
    triggered_at: str,
    artifact_bucket: Optional[str] = None,
    correlation_id: Optional[str] = None,
    requested_by: Optional[str] = None,
    notification_group: Optional[str] = None,
    flipbook_profile: Optional[str] = None,
) -> WorkerJob:
    routing = route_source_object(job_id=job_id, source_bucket=source_bucket, source_key=source_key)
    if isinstance(routing, RejectedRouting):
        raise ValueError(routing.failure_message)

    payload = {
        "jobId": job_id,
        "sourceBucket": source_bucket,
        "sourceKey": source_key,
        "triggeredAt": triggered_at,
        "outputBucket": routing.site_configuration.output_bucket,
        "outputKey": routing.output_key,
        "artifactBucket": artifact_bucket or source_bucket,
        "artifactPrefix": ARTIFACT_PREFIX_TEMPLATE.format(job_id=job_id),
        "siteConfiguration": routing.site_configuration.to_dict(),
    }
    if correlation_id:
        payload["correlationId"] = correlation_id
    if requested_by:
        payload["requestedBy"] = requested_by
    if notification_group:
        payload["notificationGroup"] = notification_group
    if flipbook_profile:
        payload["flipbookProfile"] = flipbook_profile
    return WorkerJob.from_dict(payload)


__all__ = [
    "ARTIFACT_PREFIX_TEMPLATE",
    "EXPECTED_SOURCE_BUCKET",
    "ROUTING_FAILURE_STAGE",
    "AcceptedRouting",
    "RejectedRouting",
    "RoutingDecision",
    "build_worker_job",
    "parse_site_prefix",
    "route_source_object",
]