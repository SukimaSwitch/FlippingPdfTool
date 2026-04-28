import json
import tempfile
import unittest
from pathlib import Path

from src.worker.storage_client import S3StorageClient


class FakeS3Client:
    def __init__(self) -> None:
        self.downloads = []
        self.uploads = []
        self.objects = []

    def download_file(self, bucket: str, key: str, destination: str) -> None:
        self.downloads.append({"bucket": bucket, "key": key, "destination": destination})
        Path(destination).write_bytes(b"pdf-bytes")

    def upload_file(self, source_path: str, bucket: str, key: str) -> None:
        self.uploads.append({"source_path": source_path, "bucket": bucket, "key": key})

    def put_object(self, **kwargs) -> None:
        self.objects.append(kwargs)


class StorageClientTests(unittest.TestCase):
    def test_download_file_creates_parent_directory(self) -> None:
        client = S3StorageClient(s3_client=FakeS3Client())

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "nested" / "catalog.pdf"
            result = client.download_file(
                bucket="cmg-catalog-book",
                key="input/currentcatalog/catalog.pdf",
                destination_path=destination,
            )

            self.assertEqual(result, destination)
            self.assertTrue(destination.exists())

    def test_upload_file_uses_expected_bucket_and_key(self) -> None:
        fake_s3 = FakeS3Client()
        client = S3StorageClient(s3_client=fake_s3)

        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "linked.pdf"
            source_path.write_bytes(b"linked-pdf")

            client.upload_file(
                source_path=source_path,
                bucket="cmg-catalog-book",
                key="output/currentcatalog/catalog.pdf",
            )

            self.assertEqual(fake_s3.uploads[0]["bucket"], "cmg-catalog-book")
            self.assertEqual(fake_s3.uploads[0]["key"], "output/currentcatalog/catalog.pdf")

    def test_persist_artifact_metadata_writes_retention_manifest_under_artifact_prefix(self) -> None:
        fake_s3 = FakeS3Client()
        client = S3StorageClient(s3_client=fake_s3)

        client.persist_artifact_metadata(
            bucket="cmg-catalog-book",
            artifact_prefix="artifacts/job-123/",
            artifacts=[{"type": "linked-pdf", "key": "output/currentcatalog/catalog.pdf"}],
            retention_days=30,
        )

        self.assertEqual(fake_s3.objects[0]["Bucket"], "cmg-catalog-book")
        self.assertEqual(fake_s3.objects[0]["Key"], "artifacts/job-123/retention.json")
        manifest = json.loads(fake_s3.objects[0]["Body"].decode("utf-8"))
        self.assertEqual(manifest["artifactPrefix"], "artifacts/job-123/")
        self.assertEqual(manifest["retentionDays"], 30)
        self.assertEqual(manifest["artifacts"][0]["type"], "linked-pdf")


if __name__ == "__main__":
    unittest.main()