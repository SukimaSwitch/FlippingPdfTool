"""Worker package for cloud orchestration adapters."""

from .catalog_client import MagentoCatalogClient
from .entrypoint import process_worker_job, process_worker_request
from .job_repository import JobRepository
from .logging_utils import get_workflow_logger, log_page_progress, log_stage_progress
from .models import PageResult, PersistedPageArtifacts, ProductMatch, SiteConfiguration, SourceDocument, UnmatchedSku, UnresolvedMatch, WorkerJob, WorkerResult
from .notify_client import NotificationClient
from .pipeline_runner import run_worker_pipeline
from .routing import build_worker_job, route_source_object
from .storage_client import S3StorageClient

__all__ = [
	"JobRepository",
	"MagentoCatalogClient",
	"NotificationClient",
	"PageResult",
	"PersistedPageArtifacts",
	"ProductMatch",
	"S3StorageClient",
	"SiteConfiguration",
	"SourceDocument",
	"UnmatchedSku",
	"UnresolvedMatch",
	"WorkerJob",
	"WorkerResult",
	"build_worker_job",
	"get_workflow_logger",
	"log_page_progress",
	"log_stage_progress",
	"process_worker_job",
	"process_worker_request",
	"route_source_object",
	"run_worker_pipeline",
]
