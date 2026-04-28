import unittest

from src.worker.routing import build_worker_job, route_source_object


class SiteRoutingTests(unittest.TestCase):
    def test_supported_prefix_routes_to_matching_output(self) -> None:
        decision = route_source_object(
            job_id="job-accepted",
            source_bucket="cmg-catalog-book",
            source_key="input/lillianvernon/fall-catalog.pdf",
        )

        payload = decision.to_dict()

        self.assertEqual(payload["routingStatus"], "accepted")
        self.assertEqual(payload["siteConfiguration"]["sitePrefix"], "lillianvernon")
        self.assertEqual(
            payload["siteConfiguration"]["outputKey"],
            "output/lillianvernon/fall-catalog.pdf",
        )

    def test_unknown_prefix_is_rejected(self) -> None:
        decision = route_source_object(
            job_id="job-rejected",
            source_bucket="cmg-catalog-book",
            source_key="input/unknown/fall-catalog.pdf",
        )

        payload = decision.to_dict()

        self.assertEqual(payload["routingStatus"], "rejected")
        self.assertEqual(payload["failureStage"], "ingest-routing")
        self.assertEqual(payload["failureCode"], "unknown-prefix")

    def test_worker_job_uses_routed_output(self) -> None:
        job = build_worker_job(
            job_id="job-build",
            source_bucket="cmg-catalog-book",
            source_key="input/colorfulimages/winter-catalog.pdf",
            triggered_at="2026-04-27T12:00:00Z",
            notification_group="catalog-ops@example.com",
        )

        self.assertEqual(job.output_key, "output/colorfulimages/winter-catalog.pdf")
        self.assertEqual(job.site_configuration.magento_store_code, "colorfulimages")
        self.assertEqual(job.notification_group, "catalog-ops@example.com")


if __name__ == "__main__":
    unittest.main()