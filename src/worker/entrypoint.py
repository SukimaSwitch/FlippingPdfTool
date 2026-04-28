"""Worker orchestration entrypoint for accepted jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .catalog_client import MagentoCatalogClient
from .job_repository import JobRepository
from .models import WorkerJob, WorkerResult
from .pipeline_runner import run_worker_pipeline
from .storage_client import S3StorageClient


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def process_worker_job(
    job: WorkerJob,
    *,
    storage_client: Optional[Any] = None,
    catalog_client: Optional[Any] = None,
    job_repository: Optional[Any] = None,
    pipeline_runner: Callable[..., Dict[str, Any]] = run_worker_pipeline,
    workspace_dir: Optional[Path] = None,
) -> WorkerResult:
    storage = storage_client or S3StorageClient()
    catalog = catalog_client or MagentoCatalogClient()
    repository = job_repository or JobRepository("ProcessingJobs")
    base_dir = Path(workspace_dir or Path.cwd() / ".worker")
    base_dir.mkdir(parents=True, exist_ok=True)

    repository.create_job(job)
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