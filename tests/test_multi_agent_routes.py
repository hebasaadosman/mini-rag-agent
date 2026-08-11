import unittest
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.agents import agents_router


class _Controller:
    def __init__(self):
        self.chat_calls = []
        self.resume_calls = []

    async def chat(self, **kwargs):
        self.chat_calls.append(kwargs)
        return {
            "success": True,
            "status": "completed",
            "project_id": kwargs["project_id"],
            "thread_id": kwargs["thread_id"],
            "agent": "general",
            "answer": "Hello!",
            "sources": [],
        }

    async def resume(self, **kwargs):
        self.resume_calls.append(kwargs)
        return {
            "success": True,
            "status": "completed",
            "project_id": kwargs["project_id"],
            "thread_id": kwargs["thread_id"],
            "agent": "utility",
            "answer": "Riyadh",
            "sources": [],
        }


class _Locks:
    def __init__(self):
        self.keys = []

    @asynccontextmanager
    async def acquire(self, key):
        self.keys.append(key)
        yield


class MultiAgentRouteTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        self.controller = _Controller()
        self.locks = _Locks()
        app.multi_agent_controller = self.controller
        app.agent_thread_locks = self.locks
        app.include_router(agents_router)
        self.client = TestClient(app)

    def test_chat_endpoint_calls_controller_under_thread_lock(self):
        response = self.client.post(
            "/api/v1/agents/1/chat",
            json={"message": "Hello", "thread_id": "route-001"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["agent"], "general")
        self.assertEqual(
            self.locks.keys,
            ["multi-agent:1:route-001"],
        )

    def test_resume_endpoint_calls_controller(self):
        response = self.client.post(
            "/api/v1/agents/1/chat/resume",
            json={"response": "Riyadh", "thread_id": "route-002"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["agent"], "utility")
        self.assertEqual(
            self.controller.resume_calls[0]["response"],
            "Riyadh",
        )

    def test_blank_payload_is_rejected_before_controller(self):
        response = self.client.post(
            "/api/v1/agents/1/chat",
            json={"message": "   ", "thread_id": "route-003"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.controller.chat_calls, [])

    def test_openapi_documents_chat_and_resume_schemas(self):
        schema = self.client.app.openapi()
        paths = schema["paths"]

        self.assertIn("/api/v1/agents/{project_id}/chat", paths)
        self.assertIn(
            "/api/v1/agents/{project_id}/chat/resume",
            paths,
        )
        response_schema = paths[
            "/api/v1/agents/{project_id}/chat"
        ]["post"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        self.assertEqual(
            response_schema["$ref"],
            "#/components/schemas/MultiAgentResponse",
        )


if __name__ == "__main__":
    unittest.main()
