import json
import unittest
from unittest.mock import patch

from routes.data import process_endpoint
from routes.schemes.data import ProcessRequest


class _QueuedTask:
    id = "file-task-001"


class FileProcessingRouteTests(unittest.IsolatedAsyncioTestCase):
    @patch("routes.data.process_project_files.delay", return_value=_QueuedTask())
    async def test_process_endpoint_reports_accepted_and_queued(self, delay):
        response = await process_endpoint(
            request=None,
            project_id=7,
            process_request=ProcessRequest(
                asset_id=12,
                chunk_size=500,
                overlap_size=100,
                do_reset=1,
            ),
            app_settings=None,
            _=None,
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            json.loads(response.body),
            {
                "signal": "File processing task queued",
                "task_id": "file-task-001",
            },
        )
        delay.assert_called_once()
        kwargs = delay.call_args.kwargs
        self.assertEqual(kwargs["project_id"], 7)
        self.assertEqual(kwargs["asset_id"], 12)
        self.assertEqual(kwargs["chunk_size"], 500)
        self.assertEqual(kwargs["overlap_size"], 100)
        self.assertEqual(kwargs["do_reset"], 1)
        self.assertIsNone(kwargs["principal_id"])
        self.assertTrue(kwargs["correlation_id"])
        self.assertEqual(
            kwargs["request_metadata"],
            {
                "source": "api",
                "route": "POST /api/v1/data/process/{project_id}",
            },
        )
