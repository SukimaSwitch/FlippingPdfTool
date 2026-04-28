import re
import unittest

from src.worker.routing import build_worker_job


class WorkflowContractTests(unittest.TestCase):
    def test_worker_input_payload_matches_us1_contract(self) -> None:
        job = build_worker_job(
            job_id="job-contract-001",
            source_bucket="cmg-catalog-book",
            source_key="input/currentcatalog/spring-2026-catalog.pdf",
            triggered_at="2026-04-28T12:00:00Z",
            notification_group="catalog-ops@example.com",
            flipbook_profile="default",
        )

        payload = job.to_dict()

        self.assertEqual(payload["jobId"], "job-contract-001")
        self.assertEqual(payload["sourceBucket"], "cmg-catalog-book")
        self.assertRegex(payload["sourceKey"], r"^input/(currentcatalog|colorfulimages|lillianvernon)/.*\.pdf$")
        self.assertEqual(payload["outputBucket"], "cmg-catalog-book")
        self.assertRegex(payload["outputKey"], r"^output/currentcatalog/.*\.pdf$")
        self.assertEqual(payload["artifactBucket"], "cmg-catalog-book")
        self.assertEqual(payload["artifactPrefix"], "artifacts/job-contract-001/")
        self.assertEqual(payload["siteConfiguration"]["sitePrefix"], "currentcatalog")
        self.assertEqual(payload["siteConfiguration"]["publicDomain"], "https://www.currentcatalog.com")
        self.assertEqual(payload["siteConfiguration"]["magentoStoreCode"], "currentcatalog")
        self.assertIn("/rest/currentcatalog/V1/products", payload["siteConfiguration"]["magentoProductLookupRoute"])
        self.assertEqual(payload["notificationGroup"], "catalog-ops@example.com")
        self.assertEqual(payload["flipbookProfile"], "default")

        self.assertTrue(re.match(r"^\d{4}-\d{2}-\d{2}T", payload["triggeredAt"]))


if __name__ == "__main__":
    unittest.main()