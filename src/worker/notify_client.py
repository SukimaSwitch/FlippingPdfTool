"""Notification client for worker outcomes."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Optional


def build_success_notification_payload(
    *,
    job_id: str,
    recipient_group: str,
    site_prefix: str,
    filename: str,
    flipbook_url: str,
    output_pdf_url: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    return {
        "jobId": job_id,
        "notificationType": "success",
        "recipientGroup": recipient_group,
        "sitePrefix": site_prefix,
        "filename": filename,
        "finalStatus": "completed",
        "flipbookUrl": flipbook_url,
        "outputPdfUrl": output_pdf_url,
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
    output_pdf_url: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    return {
        "jobId": job_id,
        "notificationType": "failure",
        "recipientGroup": recipient_group,
        "sitePrefix": site_prefix,
        "filename": filename,
        "finalStatus": final_status,
        "flipbookUrl": flipbook_url,
        "outputPdfUrl": output_pdf_url,
        "failureStage": failure_stage,
        "failureMessage": failure_message,
    }


def build_notification_subject(payload: Dict[str, Optional[str]]) -> str:
    notification_type = payload.get("notificationType") or "update"
    site_prefix = payload.get("sitePrefix") or "unknown-site"
    filename = payload.get("filename") or "unknown-file"
    return f"[{site_prefix}] PDF processing {notification_type}: {filename}"


def build_notification_message(payload: Dict[str, Optional[str]]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _parse_recipient_group(recipient_group: Optional[str]) -> list[str]:
    if not recipient_group:
        return []
    return [recipient.strip() for recipient in re.split(r"[;,\n]", recipient_group) if recipient.strip()]


def build_ses_sender(*, ses_client: Any, source_email: str) -> Callable[[Dict[str, Optional[str]]], None]:
    def sender(payload: Dict[str, Optional[str]]) -> None:
        recipient = payload.get("recipientGroup")
        recipients = _parse_recipient_group(recipient)
        if not recipients:
            raise ValueError("Notification payload is missing recipientGroup")
        ses_client.send_email(
            Source=source_email,
            Destination={"ToAddresses": recipients},
            Message={
                "Subject": {"Data": build_notification_subject(payload)},
                "Body": {"Text": {"Data": build_notification_message(payload)}},
            },
        )

    return sender


def build_sns_sender(*, sns_client: Any, topic_arn: str, subject_prefix: Optional[str] = None) -> Callable[[Dict[str, Optional[str]]], None]:
    def sender(payload: Dict[str, Optional[str]]) -> None:
        subject = build_notification_subject(payload)
        if subject_prefix:
            subject = f"{subject_prefix} {subject}"
        sns_client.publish(
            TopicArn=topic_arn,
            Subject=subject[:100],
            Message=build_notification_message(payload),
        )

    return sender


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
        output_pdf_url: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        payload = build_success_notification_payload(
            job_id=job_id,
            recipient_group=recipient_group,
            site_prefix=site_prefix,
            filename=filename,
            flipbook_url=flipbook_url,
            output_pdf_url=output_pdf_url,
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
        output_pdf_url: Optional[str] = None,
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
            output_pdf_url=output_pdf_url,
        )
        if self._sender:
            self._sender(payload)
        return payload