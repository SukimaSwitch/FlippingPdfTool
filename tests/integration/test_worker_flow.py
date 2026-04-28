import tempfile
import unittest
from pathlib import Path

import fitz

from src.worker.entrypoint import process_worker_job
from src.worker.routing import build_worker_job


class InMemoryStorageClient:
    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self.uploads = []

    def download_file(self, *, bucket: str, key: str, destination_path: Path) -> Path:
        destination_path.write_bytes(self.pdf_path.read_bytes())
        return destination_path

    def upload_file(self, *, source_path: Path, bucket: str, key: str) -> None:
        self.uploads.append({"source_path": source_path, "bucket": bucket, "key": key})


class StubCatalogClient:
    def build_url_template(self, site_configuration):
        return f"{site_configuration.public_domain}/sku/{{sku}}"


class InMemoryJobRepository:
    def __init__(self):
        self.created = None
        self.started = None
        self.results = []
        self.page_results = None

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


def stub_pipeline_runner(*, job, source_pdf_path, workspace_dir, url_template):
    output_path = workspace_dir / "linked_sample.pdf"
    output_path.write_bytes(source_pdf_path.read_bytes())
    return {
        "run_id": "run-integration-001",
        "output_pdf": str(output_path),
        "pages_processed": 1,
        "links_added": 2,
        "matches": 1,
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
                        "url": f"{job.site_configuration.public_domain}/sku/55281",
                        "figure_bbox": {"Left": 0.1, "Top": 0.1, "Width": 0.2, "Height": 0.2},
                        "description_bbox": {"Left": 0.1, "Top": 0.4, "Width": 0.2, "Height": 0.1},
                        "description_text": "Snowflake Tray Item 55281 only $24.99",
                        "score": 1.0,
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
            self.assertEqual(len(storage_client.uploads), 1)
            self.assertEqual(storage_client.uploads[0]["bucket"], "cmg-catalog-book")
            self.assertEqual(storage_client.uploads[0]["key"], "output/currentcatalog/sample.pdf")
            self.assertEqual(repository.created["job"].job_id, "job-integration-001")
            self.assertEqual(repository.results[-1]["result"].output_key, "output/currentcatalog/sample.pdf")
            self.assertEqual(repository.page_results["job_id"], "job-integration-001")


if __name__ == "__main__":
    unittest.main()