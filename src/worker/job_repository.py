"""Durable processing job-state persistence for the worker workflow."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Protocol, Union

import boto3

from .models import PersistedPageArtifacts, WorkerJob, WorkerResult
from .routing import RejectedRouting


TimestampLike = Union[str, datetime]


class DynamoDbTable(Protocol):
    def get_item(self, *, Key: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def put_item(self, *, Item: Dict[str, Any]) -> Dict[str, Any]:
        ...


def _as_iso8601(value: TimestampLike) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _prune_none_values(item: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in item.items() if value is not None}


def _normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float):
        return Decimal(str(value))
    if is_dataclass(value):
        return _normalize_value(asdict(value))
    if isinstance(value, dict):
        return {key: _normalize_value(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_normalize_value(inner) for inner in value]
    return value


class JobRepository:
    """Stores durable job metadata in a DynamoDB table keyed by jobId."""

    def __init__(self, table_name: str, dynamodb_resource: Any = None):
        resource = dynamodb_resource or boto3.resource("dynamodb")
        self._table: DynamoDbTable = resource.Table(table_name)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        response = self._table.get_item(Key={"jobId": job_id})
        item = response.get("Item")
        return deepcopy(item) if item else None

    def create_job(self, job: WorkerJob, *, dedupe_key: Optional[str] = None) -> Dict[str, Any]:
        timestamp = _as_iso8601(job.triggered_at)
        item = _prune_none_values(
            {
                "jobId": job.job_id,
                "status": "queued",
                "currentStage": "ingest-routing",
                "routingStatus": "accepted",
                "sourceBucket": job.source_bucket,
                "sourceKey": job.source_key,
                "sitePrefix": job.site_configuration.site_prefix,
                "publicDomain": job.site_configuration.public_domain,
                "magentoStoreCode": job.site_configuration.magento_store_code,
                "outputBucket": job.output_bucket,
                "outputKey": job.output_key,
                "artifactBucket": job.artifact_bucket,
                "artifactPrefix": job.artifact_prefix,
                "notificationGroup": job.notification_group,
                "flipbookProfile": job.flipbook_profile,
                "requestedBy": job.requested_by,
                "correlationId": job.correlation_id,
                "filename": job.filename,
                "createdAt": timestamp,
                "updatedAt": timestamp,
                "startedAt": timestamp,
                "dedupeKey": dedupe_key,
            }
        )
        self._table.put_item(Item=item)
        return deepcopy(item)

    def record_routing_rejection(
        self,
        *,
        job_id: str,
        source_bucket: str,
        source_key: str,
        decision: RejectedRouting,
        triggered_at: TimestampLike,
        dedupe_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        timestamp = _as_iso8601(triggered_at)
        item = _prune_none_values(
            {
                "jobId": job_id,
                "status": "failed",
                "currentStage": decision.failure_stage,
                "routingStatus": decision.routing_status,
                "sourceBucket": source_bucket,
                "sourceKey": source_key,
                "failureStage": decision.failure_stage,
                "failureCode": decision.failure_code,
                "failureMessage": decision.failure_message,
                "createdAt": timestamp,
                "updatedAt": timestamp,
                "startedAt": timestamp,
                "completedAt": timestamp,
                "dedupeKey": dedupe_key,
            }
        )
        self._table.put_item(Item=item)
        return deepcopy(item)

    def mark_processing_started(
        self,
        *,
        job_id: str,
        worker_run_id: str,
        started_at: TimestampLike,
    ) -> Dict[str, Any]:
        return self._merge_job(
            job_id,
            {
                "status": "processing",
                "currentStage": "pdf-processing",
                "workerRunId": worker_run_id,
                "updatedAt": _as_iso8601(started_at),
            },
        )

    def record_processing_result(
        self,
        result: WorkerResult,
        *,
        recorded_at: TimestampLike,
    ) -> Dict[str, Any]:
        timestamp = _as_iso8601(recorded_at)
        stage_by_failure = {
            "download": "download",
            "processing": "pdf-processing",
            "upload": "output-write",
        }
        updates: Dict[str, Any] = {
            "status": result.status,
            "sitePrefix": result.site_prefix,
            "artifactPrefix": result.artifact_prefix,
            "updatedAt": timestamp,
            "workerRunId": result.worker_run_id,
            "outputBucket": result.output_bucket,
            "outputKey": result.output_key,
            "pageCount": result.page_count,
            "matchedSkuCount": result.matched_sku_count,
            "unmatchedSkuCount": result.unmatched_sku_count,
            "unresolvedMatchCount": result.unresolved_match_count,
            "linkCount": result.link_count,
            "failureStage": result.failure_stage,
            "failureCode": result.failure_code,
            "failureMessage": result.failure_message,
        }
        if result.status == "processed":
            updates["currentStage"] = "output-write"
        else:
            updates["currentStage"] = stage_by_failure[result.failure_stage]
            updates["completedAt"] = timestamp
        return self._merge_job(result.job_id, updates)

    def record_page_results(self, *, job_id: str, page_summaries: Any) -> Dict[str, Any]:
        artifacts = PersistedPageArtifacts.from_page_summaries(list(page_summaries))
        return self._merge_job(job_id, artifacts.to_dict())

    def record_publication_result(
        self,
        *,
        job_id: str,
        flipbook_url: str,
        recorded_at: TimestampLike,
    ) -> Dict[str, Any]:
        return self._merge_job(
            job_id,
            {
                "currentStage": "flipbook-publish",
                "publicationStatus": "published",
                "flipbookUrl": flipbook_url,
                "updatedAt": _as_iso8601(recorded_at),
            },
        )

    def record_notification_result(
        self,
        *,
        job_id: str,
        notification_payload: Dict[str, Any],
        recorded_at: TimestampLike,
    ) -> Dict[str, Any]:
        notifications = self.get_job(job_id).get("notifications", []) if self.get_job(job_id) else []
        notifications.append(notification_payload)
        return self._merge_job(
            job_id,
            {
                "currentStage": "notification",
                "status": "completed",
                "notifications": notifications,
                "updatedAt": _as_iso8601(recorded_at),
                "completedAt": _as_iso8601(recorded_at),
            },
        )

    def record_terminal_summary(
        self,
        *,
        job_id: str,
        final_status: str,
        recorded_at: TimestampLike,
        failure_stage: Optional[str] = None,
        failure_code: Optional[str] = None,
        failure_message: Optional[str] = None,
        dedupe_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._merge_job(
            job_id,
            {
                "status": final_status,
                "finalStatus": final_status,
                "failureStage": failure_stage,
                "failureCode": failure_code,
                "failureMessage": failure_message,
                "dedupeKey": dedupe_key,
                "updatedAt": _as_iso8601(recorded_at),
                "completedAt": _as_iso8601(recorded_at),
            },
        )

    def _merge_job(self, job_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        item = self.get_job(job_id)
        if item is None:
            raise KeyError(f"Unknown jobId '{job_id}'")

        normalized_updates = _prune_none_values(_normalize_value(updates))
        item.update(normalized_updates)
        self._table.put_item(Item=item)
        return deepcopy(item)
