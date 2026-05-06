import tempfile
import unittest
from pathlib import Path

import fitz

from src.worker.entrypoint import process_worker_job
from src.worker.entrypoint import process_worker_request
from src.worker.routing import build_worker_job


class InMemoryStorageClient:
    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self.uploads = []
        self.artifacts = []

    def download_file(self, *, bucket: str, key: str, destination_path: Path) -> Path:
        destination_path.write_bytes(self.pdf_path.read_bytes())
        return destination_path

    def upload_file(self, *, source_path: Path, bucket: str, key: str) -> None:
        self.uploads.append({"source_path": source_path, "bucket": bucket, "key": key})

    def persist_artifact_metadata(self, *, bucket: str, artifact_prefix: str, artifacts, retention_days: int) -> None:
        self.artifacts.append(
            {
                "bucket": bucket,
                "artifact_prefix": artifact_prefix,
                "artifacts": artifacts,
                "retention_days": retention_days,
            }
        )


class StubCatalogLookupResult:
    def __init__(self, *, status: str, product_url: str = None, matched_sku: str = None, unresolved_reason: str = None):
        self.status = status
        self.product_url = product_url
        self.matched_sku = matched_sku
        self.unresolved_reason = unresolved_reason


class StubCatalogClient:
    def build_url_template(self, site_configuration):
        return f"{site_configuration.public_domain}/{{url_key}}.html"

    def lookup_product_match(self, site_configuration, sku: str):
        if sku == "55281":
            return StubCatalogLookupResult(
                status="matched",
                matched_sku=sku,
                product_url=f"{site_configuration.public_domain}/snowflake-tray.html",
            )
        if sku == "88442":
            return StubCatalogLookupResult(
                status="unresolved",
                matched_sku=sku,
                unresolved_reason="missing_url_key",
            )
        return StubCatalogLookupResult(status="unmatched")


class InMemoryJobRepository:
    def __init__(self):
        self.created = None
        self.started = None
        self.results = []
        self.page_results = None
        self.publications = []
        self.notifications = []
        self.final_states = []
        self.rejections = []

    def create_job(self, job, *, dedupe_key=None):
        self.created = {"job": job, "dedupe_key": dedupe_key}
        return {"jobId": job.job_id}

    def mark_processing_started(self, *, job_id: str, worker_run_id: str, started_at: str):
        self.started = {"job_id": job_id, "worker_run_id": worker_run_id, "started_at": started_at}
        return {"jobId": job_id, "workerRunId": worker_run_id}

    def record_processing_result(self, result, *, recorded_at: str):
        self.results.append({"result": result, "recorded_at": recorded_at})
        return result.to_dict()

    def record_page_results(self, *, job_id: str, page_summaries):
        self.page_results = {"job_id": job_id, "page_summaries": page_summaries}
        return self.page_results

    def record_publication_result(self, *, job_id: str, flipbook_url: str, recorded_at: str):
        payload = {"job_id": job_id, "flipbook_url": flipbook_url, "recorded_at": recorded_at}
        self.publications.append(payload)
        return payload

    def record_notification_result(self, *, job_id: str, notification_payload, recorded_at: str):
        payload = {"job_id": job_id, "notification_payload": notification_payload, "recorded_at": recorded_at}
        self.notifications.append(payload)
        return payload

    def record_routing_rejection(
        self,
        *,
        job_id: str,
        source_bucket: str,
        source_key: str,
        decision,
        triggered_at: str,
        dedupe_key: str = None,
    ):
        payload = {
            "job_id": job_id,
            "source_bucket": source_bucket,
            "source_key": source_key,
            "decision": decision.to_dict(),
            "triggered_at": triggered_at,
            "dedupe_key": dedupe_key,
        }
        self.rejections.append(payload)
        return payload

    def record_terminal_summary(
        self,
        *,
        job_id: str,
        final_status: str,
        failure_stage: str = None,
        failure_code: str = None,
        failure_message: str = None,
        dedupe_key: str = None,
        recorded_at: str,
    ):
        payload = {
            "job_id": job_id,
            "final_status": final_status,
            "failure_stage": failure_stage,
            "failure_code": failure_code,
            "failure_message": failure_message,
            "dedupe_key": dedupe_key,
            "recorded_at": recorded_at,
        }
        self.final_states.append(payload)
        return payload


def stub_pipeline_runner(*, job, source_pdf_path, workspace_dir, url_template, url_resolver=None):
    output_path = workspace_dir / "linked_sample.pdf"
    output_path.write_bytes(source_pdf_path.read_bytes())
    linked_url = url_resolver("55281").product_url if url_resolver else f"{job.site_configuration.public_domain}/sku/55281"
    return {
        "run_id": "run-integration-001",
        "output_pdf": str(output_path),
        "pages_processed": 1,
        "links_added": 2,
        "matches": 1,
        "unmatched_sku_count": 1,
        "unresolved_match_count": 1,
        "page_summaries": [
            {
                "page": 1,
                "status": "processed",
                "figure_count": 1,
                "description_candidate_count": 1,
                "links_added": 2,
                "matches": [
                    {
                        "sku": "55281",
                        "url": linked_url,
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
    }


class WorkerFlowIntegrationTests(unittest.TestCase):
    def test_accepted_route_writes_linked_output_to_matching_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_pdf = temp_path / "input.pdf"

            doc = fitz.open()
            doc.new_page(width=300, height=400)
            doc.save(input_pdf)
            doc.close()

            storage_client = InMemoryStorageClient(input_pdf)
            repository = InMemoryJobRepository()
            job = build_worker_job(
                job_id="job-integration-001",
                source_bucket="cmg-catalog-book",
                source_key="input/currentcatalog/sample.pdf",
                triggered_at="2026-04-28T12:00:00Z",
            )

            result = process_worker_job(
                job,
                storage_client=storage_client,
                catalog_client=StubCatalogClient(),
                job_repository=repository,
                workspace_dir=temp_path,
                pipeline_runner=stub_pipeline_runner,
            )

            self.assertEqual(result.status, "processed")
            self.assertEqual(result.output_bucket, "cmg-catalog-book")
            self.assertEqual(result.output_key, "output/currentcatalog/sample.pdf")
            self.assertEqual(result.unmatched_sku_count, 1)
            self.assertEqual(result.unresolved_match_count, 1)
            self.assertEqual(len(storage_client.uploads), 1)
            self.assertEqual(storage_client.uploads[0]["bucket"], "cmg-catalog-book")
            self.assertEqual(storage_client.uploads[0]["key"], "output/currentcatalog/sample.pdf")
            self.assertEqual(repository.created["job"].job_id, "job-integration-001")
            self.assertEqual(repository.results[-1]["result"].output_key, "output/currentcatalog/sample.pdf")
            self.assertEqual(repository.page_results["job_id"], "job-integration-001")
            self.assertEqual(repository.page_results["page_summaries"][0]["unmatched_skus"], ["66773"])
            self.assertEqual(repository.page_results["page_summaries"][0]["unresolved_matches"][0]["sku"], "88442")

    def test_success_flow_publishes_flipbook_and_sends_notification(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_pdf = temp_path / "input.pdf"

            doc = fitz.open()
            doc.new_page(width=300, height=400)
            doc.save(input_pdf)
            doc.close()

            storage_client = InMemoryStorageClient(input_pdf)
            repository = InMemoryJobRepository()
            publish_client = StubPublishClient()
            notify_client = StubNotifyClient()
            job = build_worker_job(
                job_id="job-integration-002",
                source_bucket="cmg-catalog-book",
                source_key="input/currentcatalog/sample.pdf",
                triggered_at="2026-04-28T12:00:00Z",
                notification_group="catalog-ops@example.com",
            )

            result = process_worker_job(
                job,
                storage_client=storage_client,
                catalog_client=StubCatalogClient(),
                publish_client=publish_client,
                notify_client=notify_client,
                job_repository=repository,
                workspace_dir=temp_path,
                pipeline_runner=stub_pipeline_runner,
            )

            self.assertEqual(result.status, "processed")
            self.assertEqual(publish_client.requests[0]["pdfKey"], "output/currentcatalog/sample.pdf")
            self.assertEqual(repository.publications[0]["flipbook_url"], "https://flipbook.example.com/books/12345")
            self.assertEqual(notify_client.payloads[0]["notificationType"], "success")
            self.assertEqual(notify_client.payloads[0]["flipbookUrl"], "https://flipbook.example.com/books/12345")
            self.assertEqual(
                notify_client.payloads[0]["outputPdfUrl"],
                "https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/sample.pdf",
            )
            self.assertEqual(repository.notifications[0]["notification_payload"]["finalStatus"], "completed")

    def test_rejected_prefix_fails_before_processing(self) -> None:
        repository = InMemoryJobRepository()
        notify_client = StubNotifyClient()

        result = process_worker_request(
            {
                "jobId": "job-rejected-001",
                "sourceBucket": "cmg-catalog-book",
                "sourceKey": "input/unknown/sample.pdf",
                "triggeredAt": "2026-04-28T12:00:00Z",
                "notificationGroup": "catalog-ops@example.com",
            },
            job_repository=repository,
            notify_client=notify_client,
        )

        self.assertEqual(result["routingStatus"], "rejected")
        self.assertEqual(result["failureStage"], "ingest-routing")
        self.assertEqual(len(repository.results), 0)
        self.assertEqual(notify_client.payloads[0]["notificationType"], "failure")
        self.assertEqual(notify_client.payloads[0]["failureStage"], "ingest-routing")

    def test_invalid_pdf_records_processing_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_pdf = temp_path / "input.pdf"
            input_pdf.write_bytes(b"not-a-pdf")

            storage_client = InMemoryStorageClient(input_pdf)
            repository = InMemoryJobRepository()
            notify_client = StubNotifyClient()
            job = build_worker_job(
                job_id="job-invalid-001",
                source_bucket="cmg-catalog-book",
                source_key="input/currentcatalog/bad.pdf",
                triggered_at="2026-04-28T12:00:00Z",
                notification_group="catalog-ops@example.com",
            )

            result = process_worker_job(
                job,
                storage_client=storage_client,
                catalog_client=StubCatalogClient(),
                notify_client=notify_client,
                job_repository=repository,
                workspace_dir=temp_path,
            )

            self.assertEqual(result.status, "failed")
            self.assertEqual(result.failure_stage, "processing")
            self.assertEqual(notify_client.payloads[0]["notificationType"], "failure")
            self.assertEqual(notify_client.payloads[0]["finalStatus"], "failed")
            self.assertEqual(notify_client.payloads[0]["failureStage"], "processing")

    def test_publication_failure_preserves_output_and_records_partial_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_pdf = temp_path / "input.pdf"

            doc = fitz.open()
            doc.new_page(width=300, height=400)
            doc.save(input_pdf)
            doc.close()

            storage_client = InMemoryStorageClient(input_pdf)
            repository = InMemoryJobRepository()
            notify_client = StubNotifyClient()
            job = build_worker_job(
                job_id="job-publish-fail-001",
                source_bucket="cmg-catalog-book",
                source_key="input/currentcatalog/sample.pdf",
                triggered_at="2026-04-28T12:00:00Z",
                notification_group="catalog-ops@example.com",
            )

            result = process_worker_job(
                job,
                storage_client=storage_client,
                catalog_client=StubCatalogClient(),
                publish_client=FailingPublishClient(),
                notify_client=notify_client,
                job_repository=repository,
                workspace_dir=temp_path,
                pipeline_runner=stub_pipeline_runner,
            )

            self.assertEqual(result.status, "processed")
            self.assertEqual(storage_client.uploads[0]["key"], "output/currentcatalog/sample.pdf")
            self.assertEqual(repository.final_states[-1]["final_status"], "partial-success")
            self.assertEqual(repository.final_states[-1]["failure_stage"], "publication")
            self.assertEqual(notify_client.payloads[-1]["finalStatus"], "partial-success")
            self.assertEqual(
                notify_client.payloads[-1]["outputPdfUrl"],
                "https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/sample.pdf",
            )

    def test_missing_publication_configuration_records_expected_partial_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_pdf = temp_path / "input.pdf"

            doc = fitz.open()
            doc.new_page(width=300, height=400)
            doc.save(input_pdf)
            doc.close()

            storage_client = InMemoryStorageClient(input_pdf)
            repository = InMemoryJobRepository()
            notify_client = StubNotifyClient()
            job = build_worker_job(
                job_id="job-publish-missing-001",
                source_bucket="cmg-catalog-book",
                source_key="input/currentcatalog/sample.pdf",
                triggered_at="2026-04-28T12:00:00Z",
                notification_group="catalog-ops@example.com",
            )

            result = process_worker_job(
                job,
                storage_client=storage_client,
                catalog_client=StubCatalogClient(),
                notify_client=notify_client,
                job_repository=repository,
                workspace_dir=temp_path,
                pipeline_runner=stub_pipeline_runner,
            )

            self.assertEqual(result.status, "processed")
            self.assertEqual(storage_client.uploads[0]["key"], "output/currentcatalog/sample.pdf")
            self.assertEqual(repository.final_states[-1]["final_status"], "partial-success")
            self.assertEqual(repository.final_states[-1]["failure_stage"], "publication")
            self.assertEqual(repository.final_states[-1]["failure_code"], "publication-not-configured")
            self.assertEqual(notify_client.payloads[-1]["notificationType"], "failure")
            self.assertEqual(notify_client.payloads[-1]["failureStage"], "publication")
            self.assertEqual(
                notify_client.payloads[-1]["outputPdfUrl"],
                "https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/sample.pdf",
            )

    def test_notification_failure_preserves_flipbook_and_records_partial_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_pdf = temp_path / "input.pdf"

            doc = fitz.open()
            doc.new_page(width=300, height=400)
            doc.save(input_pdf)
            doc.close()

            storage_client = InMemoryStorageClient(input_pdf)
            repository = InMemoryJobRepository()
            job = build_worker_job(
                job_id="job-notify-fail-001",
                source_bucket="cmg-catalog-book",
                source_key="input/currentcatalog/sample.pdf",
                triggered_at="2026-04-28T12:00:00Z",
                notification_group="catalog-ops@example.com",
            )

            result = process_worker_job(
                job,
                storage_client=storage_client,
                catalog_client=StubCatalogClient(),
                publish_client=StubPublishClient(),
                notify_client=FailingNotifyClient(),
                job_repository=repository,
                workspace_dir=temp_path,
                pipeline_runner=stub_pipeline_runner,
            )

            self.assertEqual(result.status, "processed")
            self.assertEqual(repository.publications[-1]["flipbook_url"], "https://flipbook.example.com/books/12345")
            self.assertEqual(repository.final_states[-1]["final_status"], "partial-success")
            self.assertEqual(repository.final_states[-1]["failure_stage"], "notification")


class StubPublishClient:
    def __init__(self):
        self.requests = []

    def publish_pdf(self, *, job_id: str, site_prefix: str, pdf_bucket: str, pdf_key: str, filename: str):
        request = {
            "jobId": job_id,
            "sitePrefix": site_prefix,
            "pdfBucket": pdf_bucket,
            "pdfKey": pdf_key,
            "filename": filename,
        }
        self.requests.append(request)
        return {"jobId": job_id, "publicationStatus": "published", "flipbookUrl": "https://flipbook.example.com/books/12345"}


class StubNotifyClient:
    def __init__(self):
        self.payloads = []

    def send_success_notification(
        self,
        *,
        job_id: str,
        recipient_group: str,
        site_prefix: str,
        filename: str,
        flipbook_url: str,
        output_pdf_url: str = None,
    ):
        payload = {
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
        self.payloads.append(payload)
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
        flipbook_url: str = None,
        output_pdf_url: str = None,
    ):
        payload = {
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
        self.payloads.append(payload)
        return payload


class FailingPublishClient:
    def publish_pdf(self, **kwargs):
        raise RuntimeError("Flipbook service rejected the PDF.")


class FailingNotifyClient:
    def send_success_notification(self, **kwargs):
        raise RuntimeError("Notification delivery failed.")


if __name__ == "__main__":
    unittest.main()