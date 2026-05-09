"""Structured workflow logging helpers for worker orchestration."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, Optional


def get_workflow_logger(name: str = "src.worker.workflow") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def build_log_payload(event: str, **fields: Any) -> Dict[str, Any]:
    payload = {"event": event}
    for key, value in fields.items():
        if value is not None:
            payload[key] = value
    return payload


def log_workflow_event(
    logger: logging.Logger,
    *,
    event: str,
    level: int = logging.INFO,
    **fields: Any,
) -> Dict[str, Any]:
    payload = build_log_payload(event, **fields)
    logger.log(level, json.dumps(payload, sort_keys=True))
    return payload


def log_stage_progress(
    logger: logging.Logger,
    *,
    job_id: str,
    stage: str,
    status: str,
    worker_run_id: Optional[str] = None,
    message: Optional[str] = None,
    **fields: Any,
) -> Dict[str, Any]:
    return log_workflow_event(
        logger,
        event="workflow.stage",
        jobId=job_id,
        stage=stage,
        status=status,
        workerRunId=worker_run_id,
        message=message,
        **fields,
    )


def log_page_progress(
    logger: logging.Logger,
    *,
    job_id: str,
    page_number: int,
    status: str,
    worker_run_id: Optional[str] = None,
    match_count: Optional[int] = None,
    unmatched_sku_count: Optional[int] = None,
    unresolved_match_count: Optional[int] = None,
    **fields: Any,
) -> Dict[str, Any]:
    return log_workflow_event(
        logger,
        event="workflow.page",
        jobId=job_id,
        pageNumber=page_number,
        status=status,
        workerRunId=worker_run_id,
        matchCount=match_count,
        unmatchedSkuCount=unmatched_sku_count,
        unresolvedMatchCount=unresolved_match_count,
        **fields,
    )
