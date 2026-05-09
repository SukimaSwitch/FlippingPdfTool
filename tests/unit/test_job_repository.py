import unittest
from copy import deepcopy
from decimal import Decimal

from src.worker.job_repository import JobRepository
from src.worker.models import PersistedPageArtifacts, SourceDocument, WorkerResult
from src.worker.routing import RejectedRouting, build_worker_job


class FakeTable:
    def __init__(self) -> None:
        self.items = {}

    def get_item(self, *, Key):
        item = self.items.get(Key["jobId"])
        return {"Item": deepcopy(item)} if item is not None else {}

    def put_item(self, *, Item):
        self.items[Item["jobId"]] = deepcopy(Item)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}


class FakeDynamoResource:
    def __init__(self) -> None:
        self.table = FakeTable()

    def Table(self, table_name):
        return self.table


class JobRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resource = FakeDynamoResource()
        self.repository = JobRepository("ProcessingJobs", dynamodb_resource=self.resource)

    def test_create_job_persists_initial_state(self) -> None:
        job = build_worker_job(
            job_id="job-1",
            source_bucket="cmg-catalog-book",
            source_key="input/currentcatalog/spring.pdf",
            triggered_at="2026-04-27T12:00:00Z",
        )

        item = self.repository.create_job(job, dedupe_key="bucket:key:etag")

        self.assertEqual(item["jobId"], "job-1")
        self.assertEqual(item["status"], "queued")
        self.assertEqual(item["routingStatus"], "accepted")
        self.assertEqual(item["currentStage"], "ingest-routing")
        self.assertEqual(item["outputKey"], "output/currentcatalog/spring.pdf")
        self.assertEqual(item["dedupeKey"], "bucket:key:etag")

    def test_worker_job_exposes_shared_source_document_model(self) -> None:
        job = build_worker_job(
            job_id="job-source",
            source_bucket="cmg-catalog-book",
            source_key="input/currentcatalog/spring.pdf",
            triggered_at="2026-04-27T12:00:00Z",
        )

        self.assertIsInstance(job.source_document, SourceDocument)
        self.assertEqual(job.source_document.to_dict()["filename"], "spring.pdf")

    def test_record_processing_result_updates_job_state(self) -> None:
        job = build_worker_job(
            job_id="job-2",
            source_bucket="cmg-catalog-book",
            source_key="input/colorfulimages/summer.pdf",
            triggered_at="2026-04-27T12:00:00Z",
        )
        self.repository.create_job(job)
        self.repository.mark_processing_started(
            job_id="job-2",
            worker_run_id="run-2",
            started_at="2026-04-27T12:01:00Z",
        )

        result = WorkerResult(
            job_id="job-2",
            status="processed",
            site_prefix="colorfulimages",
            artifact_prefix="artifacts/job-2/",
            worker_run_id="run-2",
            output_bucket="cmg-catalog-book",
            output_key="output/colorfulimages/summer.pdf",
            page_count=12,
            matched_sku_count=18,
            unmatched_sku_count=2,
            link_count=36,
        )

        item = self.repository.record_processing_result(
            result,
            recorded_at="2026-04-27T12:05:00Z",
        )

        self.assertEqual(item["status"], "processed")
        self.assertEqual(item["currentStage"], "output-write")
        self.assertEqual(item["workerRunId"], "run-2")
        self.assertEqual(item["pageCount"], 12)
        self.assertNotIn("completedAt", item)

    def test_record_routing_rejection_persists_terminal_failure(self) -> None:
        item = self.repository.record_routing_rejection(
            job_id="job-3",
            source_bucket="cmg-catalog-book",
            source_key="input/unknown/summer.pdf",
            decision=RejectedRouting(
                job_id="job-3",
                failure_code="unknown-prefix",
                failure_message="Unsupported site prefix in key input/unknown/summer.pdf",
            ),
            triggered_at="2026-04-27T12:00:00Z",
        )

        self.assertEqual(item["status"], "failed")
        self.assertEqual(item["failureStage"], "ingest-routing")
        self.assertEqual(item["failureCode"], "unknown-prefix")
        self.assertEqual(item["completedAt"], "2026-04-27T12:00:00Z")

    def test_failed_processing_result_records_terminal_failure(self) -> None:
        job = build_worker_job(
            job_id="job-4",
            source_bucket="cmg-catalog-book",
            source_key="input/currentcatalog/fail.pdf",
            triggered_at="2026-04-27T12:00:00Z",
        )
        self.repository.create_job(job)

        item = self.repository.record_processing_result(
            WorkerResult(
                job_id="job-4",
                status="failed",
                site_prefix="currentcatalog",
                artifact_prefix="artifacts/job-4/",
                worker_run_id="run-4",
                failure_stage="processing",
                failure_code="invalid-pdf",
                failure_message="PDF could not be opened.",
            ),
            recorded_at="2026-04-27T12:03:00Z",
        )

        self.assertEqual(item["status"], "failed")
        self.assertEqual(item["currentStage"], "pdf-processing")
        self.assertEqual(item["failureCode"], "invalid-pdf")
        self.assertEqual(item["completedAt"], "2026-04-27T12:03:00Z")

    def test_record_page_results_persists_unmatched_and_unresolved_details(self) -> None:
        job = build_worker_job(
            job_id="job-5",
            source_bucket="cmg-catalog-book",
            source_key="input/currentcatalog/catalog.pdf",
            triggered_at="2026-04-27T12:00:00Z",
        )
        self.repository.create_job(job)

        item = self.repository.record_page_results(
            job_id="job-5",
            page_summaries=[
                {
                    "page": 2,
                    "status": "processed",
                    "figure_count": 2,
                    "description_candidate_count": 2,
                    "links_added": 1,
                    "matches": [
                        {
                            "sku": "55281",
                            "url": "https://www.currentcatalog.com/snowflake-tray.html",
                            "figure_bbox": {"Left": 0.1, "Top": 0.1, "Width": 0.2, "Height": 0.2},
                            "description_bbox": {"Left": 0.1, "Top": 0.4, "Width": 0.2, "Height": 0.1},
                            "description_text": "Snowflake Tray Item 55281 only $24.99",
                            "score": 1.0,
                            "sku_source": "pdf",
                        }
                    ],
                    "unmatched_skus": ["66773"],
                    "unresolved_matches": [
                        {
                            "sku": "88442",
                            "matched_sku": "88442",
                            "reason": "missing_url_key",
                            "figure_bbox": {"Left": 0.4, "Top": 0.1, "Width": 0.2, "Height": 0.2},
                            "description_bbox": {"Left": 0.4, "Top": 0.4, "Width": 0.2, "Height": 0.1},
                            "description_text": "Holiday Bowl Item 88442 only $29.99",
                            "sku_source": "pdf",
                        }
                    ],
                }
            ],
        )

        self.assertEqual(item["pageResults"][0]["pageNumber"], 2)
        self.assertEqual(item["pageResults"][0]["unmatchedSkuCount"], 1)
        self.assertEqual(item["pageResults"][0]["unresolvedMatchCount"], 1)
        self.assertEqual(item["productMatches"][0]["status"], "linked")
        self.assertEqual(item["unmatchedSkus"][0]["sku"], "66773")
        self.assertEqual(item["unresolvedMatches"][0]["matchedSku"], "88442")
        self.assertEqual(item["unresolvedMatches"][0]["reason"], "missing_url_key")
        self.assertIsInstance(item["productMatches"][0]["figureBbox"]["Left"], Decimal)
        self.assertIsInstance(item["unresolvedMatches"][0]["figureBbox"]["Top"], Decimal)

    def test_persisted_page_artifacts_model_normalizes_page_summaries(self) -> None:
        artifacts = PersistedPageArtifacts.from_page_summaries(
            [
                {
                    "page": 1,
                    "status": "processed",
                    "figure_count": 0,
                    "description_candidate_count": 0,
                    "links_added": 0,
                    "matches": [],
                    "unmatched_skus": ["10001"],
                    "unresolved_matches": [
                        {
                            "sku": "20002",
                            "matched_sku": "20002",
                            "reason": "missing_url_key",
                        }
                    ],
                }
            ]
        )

        payload = artifacts.to_dict()
        self.assertEqual(payload["pageResults"][0]["unmatchedSkuCount"], 1)
        self.assertEqual(payload["unmatchedSkus"][0]["status"], "unmatched")
        self.assertEqual(payload["unresolvedMatches"][0]["status"], "unresolved")

    def test_record_terminal_summary_persists_partial_success_outcome(self) -> None:
        job = build_worker_job(
            job_id="job-6",
            source_bucket="cmg-catalog-book",
            source_key="input/currentcatalog/catalog.pdf",
            triggered_at="2026-04-27T12:00:00Z",
        )
        self.repository.create_job(job, dedupe_key="bucket:key:etag")

        item = self.repository.record_terminal_summary(
            job_id="job-6",
            final_status="partial-success",
            failure_stage="notification",
            failure_code="notification-failed",
            failure_message="Notification delivery failed.",
            dedupe_key="bucket:key:etag",
            recorded_at="2026-04-27T12:05:00Z",
        )

        self.assertEqual(item["status"], "partial-success")
        self.assertEqual(item["finalStatus"], "partial-success")
        self.assertEqual(item["failureStage"], "notification")
        self.assertEqual(item["failureCode"], "notification-failed")
        self.assertEqual(item["dedupeKey"], "bucket:key:etag")
        self.assertEqual(item["completedAt"], "2026-04-27T12:05:00Z")


if __name__ == "__main__":
    unittest.main()