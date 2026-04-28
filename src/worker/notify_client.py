"""Notification client for worker outcomes."""

from __future__ import annotations

from typing import Callable, Dict, Optional


def build_success_notification_payload(
    *,
    job_id: str,
    recipient_group: str,
    site_prefix: str,
    filename: str,
    flipbook_url: str,
) -> Dict[str, Optional[str]]:
    return {
        "jobId": job_id,
        "notificationType": "success",
        "recipientGroup": recipient_group,
        "sitePrefix": site_prefix,
        "filename": filename,
        "finalStatus": "completed",
        "flipbookUrl": flipbook_url,
        "failureStage": None,
        "failureMessage": None,
    }


def build_failure_notification_payload(
    *,
    job_id: str,
    recipient_group: str,
    site_prefix: str,
    filename: str,
    final_status: str,
    failure_stage: str,
    failure_message: str,
    flipbook_url: Optional[str],
) -> Dict[str, Optional[str]]:
    return {
        "jobId": job_id,
        "notificationType": "failure",
        "recipientGroup": recipient_group,
        "sitePrefix": site_prefix,
        "filename": filename,
        "finalStatus": final_status,
        "flipbookUrl": flipbook_url,
        "failureStage": failure_stage,
        "failureMessage": failure_message,
    }


class NotificationClient:
    def __init__(self, sender: Optional[Callable[[Dict[str, Optional[str]]], None]] = None):
        self._sender = sender

    def send_success_notification(
        self,
        *,
        job_id: str,
        recipient_group: str,
        site_prefix: str,
        filename: str,
        flipbook_url: str,
    ) -> Dict[str, Optional[str]]:
        payload = build_success_notification_payload(
            job_id=job_id,
            recipient_group=recipient_group,
            site_prefix=site_prefix,
            filename=filename,
            flipbook_url=flipbook_url,
        )
        if self._sender:
            self._sender(payload)
        return payload

    def send_failure_notification(
        self,
        *,
        job_id: str,
        recipient_group: str,
        site_prefix: str,
        filename: str,
        final_status: str,
        failure_stage: str,
        failure_message: str,
        flipbook_url: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        payload = build_failure_notification_payload(
            job_id=job_id,
            recipient_group=recipient_group,
            site_prefix=site_prefix,
            filename=filename,
            final_status=final_status,
            failure_stage=failure_stage,
            failure_message=failure_message,
            flipbook_url=flipbook_url,
        )
        if self._sender:
            self._sender(payload)
        return payload