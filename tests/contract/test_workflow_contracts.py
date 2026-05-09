import re
import unittest

from src.worker.models import WorkerResult
from src.worker.notify_client import build_failure_notification_payload, build_success_notification_payload
from src.worker.routing import route_source_object
from src.worker.routing import build_worker_job


class WorkflowContractTests(unittest.TestCase):
    def test_worker_input_payload_matches_us1_contract(self) -> None:
        job = build_worker_job(
            job_id="job-contract-001",
            source_bucket="cmg-catalog-book",
            source_key="input/currentcatalog/spring-2026-catalog.pdf",
            triggered_at="2026-04-28T12:00:00Z",
            notification_group="catalog-ops@example.com",
        )

        payload = job.to_dict()

        self.assertEqual(payload["jobId"], "job-contract-001")
        self.assertEqual(payload["sourceBucket"], "cmg-catalog-book")
        self.assertRegex(payload["sourceKey"], r"^input/(currentcatalog|colorfulimages|lillianvernon)/.*\.pdf$")
        self.assertEqual(payload["outputBucket"], "cmg-catalog-book")
        self.assertRegex(payload["outputKey"], r"^output/currentcatalog/.*\.pdf$")
        self.assertEqual(payload["artifactBucket"], "cmg-catalog-book")
        self.assertEqual(payload["artifactPrefix"], "artifacts/job-contract-001/")
        self.assertEqual(
            set(payload["siteConfiguration"].keys()),
            {"sitePrefix", "publicDomain", "magentoStoreCode", "magentoProductLookupRoute", "productUrlTemplate"},
        )
        self.assertEqual(payload["siteConfiguration"]["sitePrefix"], "currentcatalog")
        self.assertEqual(payload["siteConfiguration"]["publicDomain"], "https://www.currentcatalog.com")
        self.assertEqual(payload["siteConfiguration"]["magentoStoreCode"], "currentcatalog")
        self.assertEqual(
            payload["siteConfiguration"]["magentoProductLookupRoute"],
            "/rest/currentcatalog/V1/products?searchCriteria[filterGroups][0][filters][0][field]=sku"
            "&searchCriteria[filterGroups][0][filters][0][value]={sku}"
            "&searchCriteria[filterGroups][0][filters][0][conditionType]=like",
        )
        self.assertEqual(
            payload["siteConfiguration"]["productUrlTemplate"],
            "https://www.currentcatalog.com/buy/{url_key}.html",
        )
        self.assertEqual(payload["notificationGroup"], "catalog-ops@example.com")

        self.assertTrue(re.match(r"^\d{4}-\d{2}-\d{2}T", payload["triggeredAt"]))

    def test_processed_worker_result_reports_unmatched_and_unresolved_us1_counts(self) -> None:
        payload = WorkerResult(
            job_id="job-result-001",
            status="processed",
            site_prefix="currentcatalog",
            artifact_prefix="artifacts/job-result-001/",
            worker_run_id="run-result-001",
            output_bucket="cmg-catalog-book",
            output_key="output/currentcatalog/spring-2026-catalog.pdf",
            page_count=96,
            matched_sku_count=148,
            unmatched_sku_count=7,
            unresolved_match_count=2,
            link_count=296,
        ).to_dict()

        self.assertEqual(payload["status"], "processed")
        self.assertEqual(payload["outputBucket"], "cmg-catalog-book")
        self.assertEqual(payload["outputKey"], "output/currentcatalog/spring-2026-catalog.pdf")
        self.assertEqual(payload["matchedSkuCount"], 148)
        self.assertEqual(payload["unmatchedSkuCount"], 7)
        self.assertEqual(payload["unresolvedMatchCount"], 2)
        self.assertEqual(payload["linkCount"], 296)

    def test_success_notification_payload_matches_us2_contract(self) -> None:
        payload = build_success_notification_payload(
            job_id="job-notify-001",
            recipient_group="catalog-ops@example.com",
            site_prefix="currentcatalog",
            filename="spring-2026-catalog.pdf",
            output_pdf_url="https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/spring-2026-catalog.pdf",
        )

        self.assertEqual(payload["jobId"], "job-notify-001")
        self.assertEqual(payload["notificationType"], "success")
        self.assertEqual(payload["recipientGroup"], "catalog-ops@example.com")
        self.assertEqual(payload["sitePrefix"], "currentcatalog")
        self.assertEqual(payload["filename"], "spring-2026-catalog.pdf")
        self.assertEqual(payload["finalStatus"], "success")
        self.assertNotIn("flipbookUrl", payload)
        self.assertEqual(
            payload["outputPdfUrl"],
            "https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/spring-2026-catalog.pdf",
        )
        self.assertIsNone(payload["failureStage"])
        self.assertIsNone(payload["failureMessage"])

    def test_rejected_routing_contract_reports_ingest_failure(self) -> None:
        decision = route_source_object(
            job_id="job-reject-001",
            source_bucket="cmg-catalog-book",
            source_key="input/unknown/spring-2026-catalog.pdf",
        )

        payload = decision.to_dict()

        self.assertEqual(payload["routingStatus"], "rejected")
        self.assertEqual(payload["failureStage"], "ingest-routing")
        self.assertEqual(payload["failureCode"], "unknown-prefix")
        self.assertIn("Unsupported site prefix", payload["failureMessage"])

    def test_failure_notification_payload_matches_us3_contract(self) -> None:
        payload = build_failure_notification_payload(
            job_id="job-failure-001",
            recipient_group="catalog-ops@example.com",
            site_prefix="currentcatalog",
            filename="spring-2026-catalog.pdf",
            final_status="partial-success",
            failure_stage="notification",
            failure_message="Notification delivery failed.",
            output_pdf_url="https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/spring-2026-catalog.pdf",
        )

        self.assertEqual(payload["jobId"], "job-failure-001")
        self.assertEqual(payload["notificationType"], "failure")
        self.assertEqual(payload["recipientGroup"], "catalog-ops@example.com")
        self.assertEqual(payload["finalStatus"], "partial-success")
        self.assertEqual(payload["failureStage"], "notification")
        self.assertEqual(payload["failureMessage"], "Notification delivery failed.")
        self.assertNotIn("flipbookUrl", payload)
        self.assertEqual(
            payload["outputPdfUrl"],
            "https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/spring-2026-catalog.pdf",
        )


if __name__ == "__main__":
    unittest.main()