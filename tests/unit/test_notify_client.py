import unittest

from src.worker.notify_client import NotificationClient, build_failure_notification_payload, build_success_notification_payload


class NotificationClientTests(unittest.TestCase):
    def test_build_success_notification_payload_matches_contract_fields(self) -> None:
        payload = build_success_notification_payload(
            job_id="job-notify-001",
            recipient_group="catalog-ops@example.com",
            site_prefix="currentcatalog",
            filename="catalog.pdf",
            flipbook_url="https://flipbook.example.com/books/12345",
        )

        self.assertEqual(payload["notificationType"], "success")
        self.assertEqual(payload["recipientGroup"], "catalog-ops@example.com")
        self.assertEqual(payload["sitePrefix"], "currentcatalog")
        self.assertEqual(payload["filename"], "catalog.pdf")
        self.assertEqual(payload["finalStatus"], "completed")
        self.assertEqual(payload["flipbookUrl"], "https://flipbook.example.com/books/12345")
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
            flipbook_url="https://flipbook.example.com/books/12345",
        )

        self.assertEqual(len(sent_payloads), 1)
        self.assertEqual(sent_payloads[0], payload)
        self.assertEqual(payload["notificationType"], "success")
        self.assertEqual(payload["finalStatus"], "completed")

    def test_build_failure_notification_payload_preserves_partial_success_fields(self) -> None:
        payload = build_failure_notification_payload(
            job_id="job-notify-002",
            recipient_group="catalog-ops@example.com",
            site_prefix="currentcatalog",
            filename="catalog.pdf",
            final_status="partial-success",
            failure_stage="publication",
            failure_message="Flipbook service rejected the PDF.",
            flipbook_url="https://flipbook.example.com/books/12345",
        )

        self.assertEqual(payload["notificationType"], "failure")
        self.assertEqual(payload["finalStatus"], "partial-success")
        self.assertEqual(payload["failureStage"], "publication")
        self.assertEqual(payload["failureMessage"], "Flipbook service rejected the PDF.")
        self.assertEqual(payload["flipbookUrl"], "https://flipbook.example.com/books/12345")

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
            flipbook_url="https://flipbook.example.com/books/12345",
        )

        self.assertEqual(len(sent_payloads), 1)
        self.assertEqual(sent_payloads[0], payload)
        self.assertEqual(payload["notificationType"], "failure")
        self.assertEqual(payload["failureStage"], "notification")


if __name__ == "__main__":
    unittest.main()