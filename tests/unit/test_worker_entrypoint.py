import unittest

from src.worker.entrypoint import _build_catalog_client_from_env, _build_job_payload_from_env, _build_job_repository_from_env, _build_notify_client_from_env, _build_publish_client_from_env


class FakeSecretsClient:
    def __init__(self, secrets):
        self.secrets = secrets
        self.requests = []

    def get_secret_value(self, *, SecretId: str):
        self.requests.append(SecretId)
        return {"SecretString": self.secrets[SecretId]}


class FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeDynamoResource:
    def Table(self, table_name: str):
        return FakeTable(table_name)


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


class WorkerEntrypointBootstrapTests(unittest.TestCase):
    def test_build_job_payload_reads_notification_target_from_secret(self) -> None:
        env = {
            "JOB_ID": "job-001",
            "SOURCE_BUCKET": "cmg-catalog-book",
            "SOURCE_KEY": "input/currentcatalog/catalog.pdf",
            "NOTIFICATION_SECRET_NAME": "flipping-pdf/notifications",
        }
        secrets_client = FakeSecretsClient(
            {
                "flipping-pdf/notifications": '{"recipient": "catalog-ops@example.com"}',
            }
        )

        payload = _build_job_payload_from_env(
            env,
            secrets_client=secrets_client,
            now_fn=lambda: "2026-04-28T12:00:00+00:00",
        )

        self.assertEqual(payload["jobId"], "job-001")
        self.assertEqual(payload["notificationGroup"], "catalog-ops@example.com")
        self.assertEqual(payload["triggeredAt"], "2026-04-28T12:00:00+00:00")

    def test_build_job_payload_normalizes_url_encoded_source_key(self) -> None:
        env = {
            "JOB_ID": "job-encoded-001",
            "SOURCE_BUCKET": "cmg-catalog-book",
            "SOURCE_KEY": "input/currentcatalog/Current+Spring+2026+Sale.pdf",
        }

        payload = _build_job_payload_from_env(
            env,
            secrets_client=FakeSecretsClient({}),
            now_fn=lambda: "2026-04-28T12:00:00+00:00",
        )

        self.assertEqual(payload["sourceKey"], "input/currentcatalog/Current Spring 2026 Sale.pdf")

    def test_build_catalog_client_uses_secret_host_override(self) -> None:
        env = {
            "MAGENTO_SECRET_NAME": "flipping-pdf/magento",
        }
        secrets_client = FakeSecretsClient(
            {
                "flipping-pdf/magento": '{"host": "api.cmgdev.com", "username": "user", "password": "pass"}',
            }
        )
        client = _build_catalog_client_from_env(env, secrets_client=secrets_client)

        site_configuration = type(
            "SiteConfiguration",
            (),
            {
                "public_domain": "https://www.currentcatalog.com",
                "magento_product_lookup_route": "/rest/currentcatalog/V1/products?searchCriteria[filterGroups][0][filters][0][field]=sku&searchCriteria[filterGroups][0][filters][0][value]={sku}&searchCriteria[filterGroups][0][filters][0][conditionType]=like",
            },
        )()

        self.assertEqual(
            client.build_search_url(site_configuration, "123456"),
            "https://api.cmgdev.com/rest/currentcatalog/V1/products?searchCriteria[filterGroups][0][filters][0][field]=sku&searchCriteria[filterGroups][0][filters][0][value]=123456&searchCriteria[filterGroups][0][filters][0][conditionType]=like",
        )

    def test_build_catalog_client_prefers_explicit_bearer_token_secret(self) -> None:
        env = {
            "MAGENTO_SECRET_NAME": "flipping-pdf/magento",
        }
        secrets_client = FakeSecretsClient(
            {
                "flipping-pdf/magento": '{"host": "api.cmgdev.com", "bearer_token": "secret-token", "username": "user", "password": "pass"}',
            }
        )

        client = _build_catalog_client_from_env(env, secrets_client=secrets_client)

        self.assertEqual(client._session.headers["Authorization"], "Bearer secret-token")
        self.assertIsNone(client._token_provider)

    def test_build_publish_client_returns_none_when_flipbook_secret_is_blank(self) -> None:
        env = {
            "FLIPBOOK_SECRET_NAME": "flipping-pdf/flipbook",
        }
        secrets_client = FakeSecretsClient(
            {
                "flipping-pdf/flipbook": '{"url": "", "api_key": ""}',
            }
        )

        client = _build_publish_client_from_env(env, secrets_client=secrets_client)

        self.assertIsNone(client)

    def test_build_job_repository_uses_configured_table_name(self) -> None:
        repository = _build_job_repository_from_env(
            {"DYNAMODB_TABLE_NAME": "FlippingPdfJobs-Staging"},
            dynamodb_resource=FakeDynamoResource(),
        )

        self.assertEqual(repository._table.name, "FlippingPdfJobs-Staging")

    def test_build_notify_client_uses_secret_recipient_and_ses_source(self) -> None:
        env = {
            "NOTIFICATION_MODE": "ses",
            "NOTIFICATION_SECRET_NAME": "flipping-pdf/notifications",
        }
        secrets_client = FakeSecretsClient(
            {
                "flipping-pdf/notifications": '{"recipient": "catalog-ops@example.com", "source": "noreply@example.com"}',
            }
        )
        ses_client = FakeSesClient()

        client = _build_notify_client_from_env(env, secrets_client=secrets_client, ses_client=ses_client)
        client.send_success_notification(
            job_id="job-001",
            recipient_group="catalog-ops@example.com",
            site_prefix="currentcatalog",
            filename="catalog.pdf",
            flipbook_url="https://flipbook.example.com/books/12345",
            output_pdf_url="https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/catalog.pdf",
        )

        self.assertEqual(ses_client.requests[0]["Source"], "noreply@example.com")

    def test_build_notify_client_sends_to_multiple_secret_recipients_for_ses(self) -> None:
        env = {
            "NOTIFICATION_MODE": "ses",
            "NOTIFICATION_SECRET_NAME": "flipping-pdf/notifications",
        }
        secrets_client = FakeSecretsClient(
            {
                "flipping-pdf/notifications": '{"recipient": "catalog-ops@example.com; merch-ops@example.com", "source": "noreply@example.com"}',
            }
        )
        ses_client = FakeSesClient()

        client = _build_notify_client_from_env(env, secrets_client=secrets_client, ses_client=ses_client)
        client.send_success_notification(
            job_id="job-001",
            recipient_group="catalog-ops@example.com; merch-ops@example.com",
            site_prefix="currentcatalog",
            filename="catalog.pdf",
            flipbook_url="https://flipbook.example.com/books/12345",
            output_pdf_url="https://us-east-1.console.aws.amazon.com/s3/object/cmg-catalog-book?region=us-east-1&prefix=output/currentcatalog/catalog.pdf",
        )

        self.assertEqual(
            ses_client.requests[0]["Destination"]["ToAddresses"],
            ["catalog-ops@example.com", "merch-ops@example.com"],
        )

    def test_build_notify_client_uses_sns_topic_from_secret(self) -> None:
        env = {
            "NOTIFICATION_MODE": "sns",
            "NOTIFICATION_SECRET_NAME": "flipping-pdf/notifications",
        }
        secrets_client = FakeSecretsClient(
            {
                "flipping-pdf/notifications": '{"topic_arn": "arn:aws:sns:us-east-1:123456789012:catalog-notifications"}',
            }
        )
        sns_client = FakeSnsClient()

        client = _build_notify_client_from_env(env, secrets_client=secrets_client, sns_client=sns_client)
        client.send_failure_notification(
            job_id="job-002",
            recipient_group="catalog-ops@example.com",
            site_prefix="currentcatalog",
            filename="catalog.pdf",
            final_status="partial-success",
            failure_stage="publication",
            failure_message="Flipbook service rejected the PDF.",
            flipbook_url=None,
        )

        self.assertEqual(
            sns_client.requests[0]["TopicArn"],
            "arn:aws:sns:us-east-1:123456789012:catalog-notifications",
        )

    def test_build_notify_client_requires_source_for_ses_mode(self) -> None:
        env = {
            "NOTIFICATION_MODE": "ses",
            "NOTIFICATION_SECRET_NAME": "flipping-pdf/notifications",
        }
        secrets_client = FakeSecretsClient(
            {
                "flipping-pdf/notifications": '{"recipient": "catalog-ops@example.com"}',
            }
        )

        with self.assertRaisesRegex(ValueError, "NOTIFICATION_MODE=ses requires NOTIFICATION_SOURCE"):
            _build_notify_client_from_env(env, secrets_client=secrets_client)


if __name__ == "__main__":
    unittest.main()