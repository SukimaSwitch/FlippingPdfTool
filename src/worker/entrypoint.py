"""Worker orchestration entrypoint for accepted jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .catalog_client import MagentoCatalogClient
from .job_repository import JobRepository
from .models import WorkerJob, WorkerResult
from .notify_client import NotificationClient
from .pipeline_runner import run_worker_pipeline
from .publish_client import FlipbookPublishClient
from .routing import RejectedRouting, build_worker_job, route_source_object
from .storage_client import S3StorageClient


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe_key(source_bucket: str, source_key: str, correlation_id: Optional[str] = None) -> str:
    parts = [source_bucket, source_key]
    if correlation_id:
        parts.append(correlation_id)
    return ":".join(parts)


def process_worker_request(
    payload: Dict[str, Any],
    *,
    storage_client: Optional[Any] = None,
    catalog_client: Optional[Any] = None,
    publish_client: Optional[Any] = None,
    notify_client: Optional[Any] = None,
    job_repository: Optional[Any] = None,
    pipeline_runner: Callable[..., Dict[str, Any]] = run_worker_pipeline,
    workspace_dir: Optional[Path] = None,
) -> Any:
    repository = job_repository or JobRepository("ProcessingJobs")
    dedupe_key = _dedupe_key(payload["sourceBucket"], payload["sourceKey"], payload.get("correlationId"))
    decision = route_source_object(
        job_id=payload["jobId"],
        source_bucket=payload["sourceBucket"],
        source_key=payload["sourceKey"],
    )
    if isinstance(decision, RejectedRouting):
        repository.record_routing_rejection(
            job_id=payload["jobId"],
            source_bucket=payload["sourceBucket"],
            source_key=payload["sourceKey"],
            decision=decision,
            triggered_at=payload["triggeredAt"],
            dedupe_key=dedupe_key,
        )
        return decision.to_dict()

    job = build_worker_job(
        job_id=payload["jobId"],
        source_bucket=payload["sourceBucket"],
        source_key=payload["sourceKey"],
        triggered_at=payload["triggeredAt"],
        artifact_bucket=payload.get("artifactBucket"),
        correlation_id=payload.get("correlationId"),
        requested_by=payload.get("requestedBy"),
        notification_group=payload.get("notificationGroup"),
        flipbook_profile=payload.get("flipbookProfile"),
    )
    return process_worker_job(
        job,
        storage_client=storage_client,
        catalog_client=catalog_client,
        publish_client=publish_client,
        notify_client=notify_client,
        job_repository=repository,
        pipeline_runner=pipeline_runner,
        workspace_dir=workspace_dir,
    )


def process_worker_job(
    job: WorkerJob,
    *,
    storage_client: Optional[Any] = None,
    catalog_client: Optional[Any] = None,
    publish_client: Optional[Any] = None,
    notify_client: Optional[Any] = None,
    job_repository: Optional[Any] = None,
    pipeline_runner: Callable[..., Dict[str, Any]] = run_worker_pipeline,
    workspace_dir: Optional[Path] = None,
) -> WorkerResult:
    storage = storage_client or S3StorageClient()
    catalog = catalog_client or MagentoCatalogClient()
    repository = job_repository or JobRepository("ProcessingJobs")
    dedupe_key = _dedupe_key(job.source_bucket, job.source_key, job.correlation_id)
    base_dir = Path(workspace_dir or Path.cwd() / ".worker")
    base_dir.mkdir(parents=True, exist_ok=True)

    repository.create_job(job, dedupe_key=dedupe_key)
    local_source_path = base_dir / "source" / job.filename
    local_source_path.parent.mkdir(parents=True, exist_ok=True)
    worker_run_id = None

    try:
        storage.download_file(
            bucket=job.source_bucket,
            key=job.source_key,
            destination_path=local_source_path,
        )
        worker_run_id = f"worker-{job.job_id}"
        repository.mark_processing_started(
            job_id=job.job_id,
            worker_run_id=worker_run_id,
            started_at=_utc_now(),
        )

        summary = pipeline_runner(
            job=job,
            source_pdf_path=local_source_path,
            workspace_dir=base_dir,
            url_template=catalog.build_url_template(job.site_configuration),
        )

        output_pdf_path = Path(summary["output_pdf"])
        storage.upload_file(
            source_path=output_pdf_path,
            bucket=job.output_bucket,
            key=job.output_key,
        )

        result = WorkerResult(
            job_id=job.job_id,
            status="processed",
            site_prefix=job.site_configuration.site_prefix,
            artifact_prefix=job.artifact_prefix,
            worker_run_id=summary.get("run_id", worker_run_id),
            output_bucket=job.output_bucket,
            output_key=job.output_key,
            page_count=summary.get("pages_processed", 0),
            matched_sku_count=summary.get("matches", 0),
            unmatched_sku_count=0,
            link_count=summary.get("links_added", 0),
        )
        repository.record_processing_result(result, recorded_at=_utc_now())
        repository.record_page_results(job_id=job.job_id, page_summaries=summary.get("page_summaries", []))
        storage.persist_artifact_metadata(
            bucket=job.artifact_bucket,
            artifact_prefix=job.artifact_prefix,
            artifacts=[
                {"type": "linked-pdf", "key": job.output_key},
                {"type": "run-summary", "path": summary.get("figure_info_dir")},
            ],
            retention_days=30,
        )

        if publish_client is not None:
            notifier = notify_client or NotificationClient()
            try:
                publication = publish_client.publish_pdf(
                    job_id=job.job_id,
                    site_prefix=job.site_configuration.site_prefix,
                    pdf_bucket=job.output_bucket,
                    pdf_key=job.output_key,
                    filename=job.filename,
                )
                repository.record_publication_result(
                    job_id=job.job_id,
                    flipbook_url=publication["flipbookUrl"],
                    recorded_at=_utc_now(),
                )
            except Exception as exc:
                if job.notification_group:
                    notification_payload = notifier.send_failure_notification(
                        job_id=job.job_id,
                        recipient_group=job.notification_group,
                        site_prefix=job.site_configuration.site_prefix,
                        filename=job.filename,
                        final_status="partial-success",
                        failure_stage="publication",
                        failure_message=str(exc),
                        flipbook_url=None,
                    )
                    repository.record_notification_result(
                        job_id=job.job_id,
                        notification_payload=notification_payload,
                        recorded_at=_utc_now(),
                    )
                repository.record_terminal_summary(
                    job_id=job.job_id,
                    final_status="partial-success",
                    failure_stage="publication",
                    failure_code="publication-failed",
                    failure_message=str(exc),
                    dedupe_key=dedupe_key,
                    recorded_at=_utc_now(),
                )
                return result

            if job.notification_group:
                try:
                    notification_payload = notifier.send_success_notification(
                        job_id=job.job_id,
                        recipient_group=job.notification_group,
                        site_prefix=job.site_configuration.site_prefix,
                        filename=job.filename,
                        flipbook_url=publication["flipbookUrl"],
                    )
                    repository.record_notification_result(
                        job_id=job.job_id,
                        notification_payload=notification_payload,
                        recorded_at=_utc_now(),
                    )
                except Exception as exc:
                    repository.record_terminal_summary(
                        job_id=job.job_id,
                        final_status="partial-success",
                        failure_stage="notification",
                        failure_code="notification-failed",
                        failure_message=str(exc),
                        dedupe_key=dedupe_key,
                        recorded_at=_utc_now(),
                    )
                    return result
        return result
    except Exception as exc:
        failed_stage = "processing" if worker_run_id is not None else "download"
        result = WorkerResult(
            job_id=job.job_id,
            status="failed",
            site_prefix=job.site_configuration.site_prefix,
            artifact_prefix=job.artifact_prefix,
            worker_run_id=worker_run_id,
            failure_stage=failed_stage,
            failure_code="pipeline-failed",
            failure_message=str(exc),
        )
        repository.record_processing_result(result, recorded_at=_utc_now())
        return result