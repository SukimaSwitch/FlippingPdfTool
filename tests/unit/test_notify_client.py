import unittest

from src.worker.notify_client import NotificationClient, build_failure_notification_payload, build_notification_message, build_notification_subject, build_ses_sender, build_sns_sender, build_success_notification_payload


class FakeSesClient:
    def __init__(self) -> None:
        self.requests = []

    def send_email(self, **kwargs) -> None:
        self.requests.append(kwargs)


class FakeSnsClient:
    def __init__(self) -> None:
        self.requests = []

    def publish(self, **kwargs) -> None:
        self.requests.append(kwargs)


class NotificationClientTests(unittest.TestCase):
    def test_build_success_notification_payload_matches_contract_fields(self) -> None:
        payload = build_success_notification_payload(
            job_id="job-notify-001",
            recipient_group="catalog-ops@example.com",
            site_prefix="currentcatalog",
            filename="catalog.pdf",
            output_pdf_url="https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/catalog.pdf",
        )

        self.assertEqual(payload["notificationType"], "success")
        self.assertEqual(payload["recipientGroup"], "catalog-ops@example.com")
        self.assertEqual(payload["sitePrefix"], "currentcatalog")
        self.assertEqual(payload["filename"], "catalog.pdf")
        self.assertEqual(payload["finalStatus"], "success")
        self.assertNotIn("flipbookUrl", payload)
        self.assertEqual(payload["outputPdfUrl"], "https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/catalog.pdf")
        self.assertIsNone(payload["failureStage"])
        self.assertIsNone(payload["failureMessage"])

    def test_send_success_notification_calls_sender_with_payload(self) -> None:
        sent_payloads = []
        client = NotificationClient(sender=sent_payloads.append)

        payload = client.send_success_notification(
            job_id="job-notify-001",
            recipient_group="catalog-ops@example.com",
            site_prefix="currentcatalog",
            filename="catalog.pdf",
            output_pdf_url="https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/catalog.pdf",
        )

        self.assertEqual(len(sent_payloads), 1)
        self.assertEqual(sent_payloads[0], payload)
        self.assertEqual(payload["notificationType"], "success")
        self.assertEqual(payload["finalStatus"], "success")

    def test_build_failure_notification_payload_preserves_partial_success_fields(self) -> None:
        payload = build_failure_notification_payload(
            job_id="job-notify-002",
            recipient_group="catalog-ops@example.com",
            site_prefix="currentcatalog",
            filename="catalog.pdf",
            final_status="partial-success",
            failure_stage="notification",
            failure_message="Notification delivery failed.",
            output_pdf_url="https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/catalog.pdf",
        )

        self.assertEqual(payload["notificationType"], "failure")
        self.assertEqual(payload["finalStatus"], "partial-success")
        self.assertEqual(payload["failureStage"], "notification")
        self.assertEqual(payload["failureMessage"], "Notification delivery failed.")
        self.assertNotIn("flipbookUrl", payload)
        self.assertEqual(payload["outputPdfUrl"], "https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/catalog.pdf")

    def test_send_failure_notification_calls_sender_with_payload(self) -> None:
        sent_payloads = []
        client = NotificationClient(sender=sent_payloads.append)

        payload = client.send_failure_notification(
            job_id="job-notify-002",
            recipient_group="catalog-ops@example.com",
            site_prefix="currentcatalog",
            filename="catalog.pdf",
            final_status="partial-success",
            failure_stage="notification",
            failure_message="Email delivery failed.",
            output_pdf_url="https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/catalog.pdf",
        )

        self.assertEqual(len(sent_payloads), 1)
        self.assertEqual(sent_payloads[0], payload)
        self.assertEqual(payload["notificationType"], "failure")
        self.assertEqual(payload["failureStage"], "notification")

    def test_build_notification_subject_and_message_are_stable(self) -> None:
        payload = build_success_notification_payload(
            job_id="job-notify-003",
            recipient_group="catalog-ops@example.com",
            site_prefix="currentcatalog",
            filename="catalog.pdf",
            output_pdf_url="https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/catalog.pdf",
        )

        self.assertEqual(
            build_notification_subject(payload),
            "[currentcatalog] PDF processing success: catalog.pdf",
        )
        message = build_notification_message(payload)
        self.assertIn('"jobId": "job-notify-003"', message)
        self.assertNotIn('"flipbookUrl"', message)
        self.assertLess(message.index('"notificationType"'), message.index('"finalStatus"'))
        self.assertLess(message.index('"finalStatus"'), message.index('"filename"'))

    def test_build_ses_sender_sends_email_to_recipient_group(self) -> None:
        payload = build_success_notification_payload(
            job_id="job-notify-004",
            recipient_group="catalog-ops@example.com",
            site_prefix="currentcatalog",
            filename="catalog.pdf",
            output_pdf_url="https://cmg-catalog-book.s3.amazonaws.com/output/currentcatalog/catalog.pdf",
        )
        ses_client = FakeSesClient()
        sender = build_ses_sender(ses_client=ses_client, source_email="noreply@example.com")

        sender(payload)

        self.assertEqual(ses_client.requests[0]["Source"], "noreply@example.com")
        self.assertEqual(ses_client.requests[0]["Destination"]["ToAddresses"], ["catalog-ops@example.com"])

    def test_build_ses_sender_splits_semicolon_separated_recipients(self) -> None:
        payload = build_success_notification_payload(
            job_id="job-notify-004b",
            recipient_group="catalog-ops@example.com; merch-ops@example.com",
            site_prefix="currentcatalog",
            filename="catalog.pdf",
            output_pdf_url="https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/catalog.pdf",
        )
        ses_client = FakeSesClient()
        sender = build_ses_sender(ses_client=ses_client, source_email="noreply@example.com")

        sender(payload)

        self.assertEqual(
            ses_client.requests[0]["Destination"]["ToAddresses"],
            ["catalog-ops@example.com", "merch-ops@example.com"],
        )

    def test_build_sns_sender_publishes_to_topic(self) -> None:
        payload = build_failure_notification_payload(
            job_id="job-notify-005",
            recipient_group="catalog-ops@example.com",
            site_prefix="currentcatalog",
            filename="catalog.pdf",
            final_status="partial-success",
            failure_stage="notification",
            failure_message="Notification delivery failed.",
        )
        sns_client = FakeSnsClient()
        sender = build_sns_sender(
            sns_client=sns_client,
            topic_arn="arn:aws:sns:us-east-1:123456789012:catalog-notifications",
            subject_prefix="[staging]",
        )

        sender(payload)

        self.assertEqual(
            sns_client.requests[0]["TopicArn"],
            "arn:aws:sns:us-east-1:123456789012:catalog-notifications",
        )
        self.assertTrue(sns_client.requests[0]["Subject"].startswith("[staging]"))


if __name__ == "__main__":
    unittest.main()