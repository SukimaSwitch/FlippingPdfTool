import json
import logging
import unittest

from src.worker.logging_utils import build_log_payload, log_page_progress


class RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class LoggingUtilsTests(unittest.TestCase):
    def test_build_log_payload_omits_none_fields(self) -> None:
        payload = build_log_payload("workflow.stage", jobId="job-1", workerRunId=None)

        self.assertEqual(payload, {"event": "workflow.stage", "jobId": "job-1"})

    def test_log_page_progress_includes_unresolved_match_count(self) -> None:
        logger = logging.getLogger("tests.worker.logging")
        logger.handlers = []
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = RecordingHandler()
        logger.addHandler(handler)

        payload = log_page_progress(
            logger,
            job_id="job-1",
            page_number=3,
            status="processed",
            worker_run_id="run-1",
            match_count=4,
            unmatched_sku_count=1,
            unresolved_match_count=2,
        )

        self.assertEqual(payload["unresolvedMatchCount"], 2)
        self.assertEqual(len(handler.messages), 1)
        logged_payload = json.loads(handler.messages[0])
        self.assertEqual(logged_payload["pageNumber"], 3)
        self.assertEqual(logged_payload["unmatchedSkuCount"], 1)
        self.assertEqual(logged_payload["unresolvedMatchCount"], 2)


if __name__ == "__main__":
    unittest.main()