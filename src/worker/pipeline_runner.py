"""Worker wrapper around the reusable PDF-linking pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from src.main import run_pipeline_from_options

from .models import WorkerJob


def run_worker_pipeline(
    *,
    job: WorkerJob,
    source_pdf_path: Path,
    workspace_dir: Path,
    url_template: str,
    url_resolver: Optional[Callable[[str], Any]] = None,
    pipeline_callable: Callable[..., Dict[str, Any]] = run_pipeline_from_options,
) -> Dict[str, Any]:
    output_dir = workspace_dir / "extracted_images"
    figure_info_dir = workspace_dir / "figure_info"
    return pipeline_callable(
        pdf=str(source_pdf_path),
        domain=job.site_configuration.public_domain,
        output_dir=str(output_dir),
        figure_info_dir=str(figure_info_dir),
        url_template=url_template,
        url_resolver=url_resolver,
        aws_region=None,
        skip_existing=False,
        keep_rendered_pages=False,
        debug_overlays=False,
    )