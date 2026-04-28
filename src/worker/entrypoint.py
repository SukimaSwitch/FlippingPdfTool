"""Worker orchestration entrypoint for accepted jobs."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

import boto3

from .catalog_client import MagentoCatalogClient
from .job_repository import JobRepository
from .models import WorkerJob, WorkerResult
from .notify_client import NotificationClient, build_ses_sender, build_sns_sender
from .pipeline_runner import run_worker_pipeline
from .publish_client import FlipbookPublishClient
from .routing import RejectedRouting, build_worker_job, route_source_object
from .storage_client import S3StorageClient


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_secrets_client(region_name: Optional[str] = None) -> Any:
    kwargs: Dict[str, Any] = {}
    if region_name:
        kwargs["region_name"] = region_name
    return boto3.client("secretsmanager", **kwargs)


def _build_aws_client(service_name: str, *, region_name: Optional[str] = None) -> Any:
    kwargs: Dict[str, Any] = {}
    if region_name:
        kwargs["region_name"] = region_name
    return boto3.client(service_name, **kwargs)


def _normalize_base_url(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped.startswith("http://") or stripped.startswith("https://"):
        return stripped.rstrip("/")
    return f"https://{stripped.rstrip('/')}"


def _load_secret_dict(secret_name: str, *, secrets_client: Any) -> Dict[str, Any]:
    response = secrets_client.get_secret_value(SecretId=secret_name)
    secret_string = response.get("SecretString", "")
    payload = json.loads(secret_string) if secret_string else {}
    if not isinstance(payload, dict):
        raise ValueError(f"Secret '{secret_name}' must contain a JSON object")
    return payload


def _optional_secret_dict(secret_name: Optional[str], *, secrets_client: Any) -> Dict[str, Any]:
    if not secret_name:
        return {}
    return _load_secret_dict(secret_name, secrets_client=secrets_client)


def _required_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if value is None or not value.strip():
        raise ValueError(f"Missing required environment variable '{name}'")
    return value


def _build_job_payload_from_env(
    env: Mapping[str, str],
    *,
    secrets_client: Any,
    now_fn: Callable[[], str] = _utc_now,
) -> Dict[str, Any]:
    notification_secret = _optional_secret_dict(env.get("NOTIFICATION_SECRET_NAME"), secrets_client=secrets_client)
    notification_group = env.get("NOTIFICATION_TARGET") or notification_secret.get("recipient")

    payload: Dict[str, Any] = {
        "jobId": _required_env(env, "JOB_ID"),
        "sourceBucket": _required_env(env, "SOURCE_BUCKET"),
        "sourceKey": _required_env(env, "SOURCE_KEY"),
        "triggeredAt": env.get("TRIGGERED_AT") or now_fn(),
    }
    if notification_group:
        payload["notificationGroup"] = notification_group
    if env.get("CORRELATION_ID"):
        payload["correlationId"] = env["CORRELATION_ID"]
    if env.get("REQUESTED_BY"):
        payload["requestedBy"] = env["REQUESTED_BY"]
    if env.get("FLIPBOOK_PROFILE"):
        payload["flipbookProfile"] = env["FLIPBOOK_PROFILE"]
    return payload


def _build_catalog_client_from_env(env: Mapping[str, str], *, secrets_client: Any) -> MagentoCatalogClient:
    magento_secret_name = env.get("MAGENTO_SECRET_NAME") or env.get("MAGENTO_BEARER_TOKEN_SECRET_NAME")
    magento_secret = _optional_secret_dict(magento_secret_name, secrets_client=secrets_client)
    base_url = _normalize_base_url(env.get("MAGENTO_SEARCH_BASE_URL") or magento_secret.get("host"))

    auth_headers: Dict[str, str] = {}
    bearer_token = magento_secret.get("bearer_token") or magento_secret.get("api_key")
    if isinstance(bearer_token, str) and bearer_token.strip():
        auth_headers["Authorization"] = f"Bearer {bearer_token.strip()}"

    username = magento_secret.get("username") if isinstance(magento_secret.get("username"), str) else None
    password = magento_secret.get("password") if isinstance(magento_secret.get("password"), str) else None
    return MagentoCatalogClient(
        base_url=base_url,
        auth_headers=auth_headers or None,
        username=username,
        password=password,
    )


def _build_publish_client_from_env(env: Mapping[str, str], *, secrets_client: Any) -> Optional[FlipbookPublishClient]:
    flipbook_secret = _optional_secret_dict(env.get("FLIPBOOK_SECRET_NAME"), secrets_client=secrets_client)
    api_url = _normalize_base_url(env.get("FLIPBOOK_API_BASE_URL") or flipbook_secret.get("url"))
    api_key = env.get("FLIPBOOK_API_KEY") or flipbook_secret.get("api_key")
    if not api_url or not api_key:
        return None
    return FlipbookPublishClient(api_url=api_url, api_key=api_key)


def _build_notify_client_from_env(
    env: Mapping[str, str],
    *,
    secrets_client: Any,
    ses_client: Optional[Any] = None,
    sns_client: Optional[Any] = None,
) -> NotificationClient:
    mode = (env.get("NOTIFICATION_MODE") or "").strip().lower()
    notification_secret = _optional_secret_dict(env.get("NOTIFICATION_SECRET_NAME"), secrets_client=secrets_client)
    if mode == "ses":
        source_email = env.get("NOTIFICATION_SOURCE") or notification_secret.get("source")
        if not isinstance(source_email, str) or not source_email.strip():
            raise ValueError("NOTIFICATION_MODE=ses requires NOTIFICATION_SOURCE or notification secret source")
        client = ses_client or _build_aws_client("ses", region_name=env.get("AWS_REGION"))
        return NotificationClient(sender=build_ses_sender(ses_client=client, source_email=source_email.strip()))
    if mode == "sns":
        topic_arn = env.get("NOTIFICATION_TOPIC_ARN") or notification_secret.get("topic_arn")
        if not isinstance(topic_arn, str) or not topic_arn.strip():
            raise ValueError("NOTIFICATION_MODE=sns requires NOTIFICATION_TOPIC_ARN or notification secret topic_arn")
        client = sns_client or _build_aws_client("sns", region_name=env.get("AWS_REGION"))
        subject_prefix = env.get("NOTIFICATION_SUBJECT_PREFIX")
        return NotificationClient(
            sender=build_sns_sender(
                sns_client=client,
                topic_arn=topic_arn.strip(),
                subject_prefix=subject_prefix.strip() if isinstance(subject_prefix, str) and subject_prefix.strip() else None,
            )
        )
    return NotificationClient()


def _build_job_repository_from_env(env: Mapping[str, str], *, dynamodb_resource: Optional[Any] = None) -> JobRepository:
    return JobRepository(env.get("DYNAMODB_TABLE_NAME", "ProcessingJobs"), dynamodb_resource=dynamodb_resource)


def _normalize_result_payload(result: Any) -> Dict[str, Any]:
    if hasattr(result, "to_dict"):
        return result.to_dict()
    if isinstance(result, dict):
        return result
    raise TypeError("Worker result must be a dict-like payload")


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
    notifier = notify_client or NotificationClient()
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
        if payload.get("notificationGroup"):
            notification_payload = notifier.send_failure_notification(
                job_id=payload["jobId"],
                recipient_group=payload["notificationGroup"],
                site_prefix="unknown",
                filename=payload["sourceKey"].rsplit("/", 1)[-1],
                final_status="failed",
                failure_stage=decision.failure_stage,
                failure_message=decision.failure_message,
                flipbook_url=None,
            )
            repository.record_notification_result(
                job_id=payload["jobId"],
                notification_payload=notification_payload,
                recorded_at=_utc_now(),
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
    notifier = notify_client or NotificationClient()
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
            url_resolver=lambda sku: catalog.lookup_product_match(job.site_configuration, sku),
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
            unmatched_sku_count=summary.get("unmatched_sku_count", 0),
            unresolved_match_count=summary.get("unresolved_match_count", 0),
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
        if job.notification_group:
            notification_payload = notifier.send_failure_notification(
                job_id=job.job_id,
                recipient_group=job.notification_group,
                site_prefix=job.site_configuration.site_prefix,
                filename=job.filename,
                final_status="failed",
                failure_stage=failed_stage,
                failure_message=str(exc),
                flipbook_url=None,
            )
            repository.record_notification_result(
                job_id=job.job_id,
                notification_payload=notification_payload,
                recorded_at=_utc_now(),
            )
        return result


def main(env: Optional[Mapping[str, str]] = None, *, secrets_client: Optional[Any] = None) -> int:
    runtime_env = env or os.environ
    region_name = runtime_env.get("AWS_REGION")
    secrets = secrets_client or _build_secrets_client(region_name)
    payload = _build_job_payload_from_env(runtime_env, secrets_client=secrets)
    repository = _build_job_repository_from_env(runtime_env)
    catalog_client = _build_catalog_client_from_env(runtime_env, secrets_client=secrets)
    publish_client = _build_publish_client_from_env(runtime_env, secrets_client=secrets)
    notify_client = _build_notify_client_from_env(runtime_env, secrets_client=secrets)

    result = process_worker_request(
        payload,
        catalog_client=catalog_client,
        publish_client=publish_client,
        notify_client=notify_client,
        job_repository=repository,
    )
    normalized = _normalize_result_payload(result)
    print(json.dumps(normalized, sort_keys=True))

    if normalized.get("status") == "failed":
        return 1
    if normalized.get("routingStatus") == "rejected":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())