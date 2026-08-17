import unittest

from controllers import MultiAgentController


class _Runtime:
    def __init__(self, *, error=None, result=None):
        self.error = error
        self.result = result
        self.chat_calls = []
        self.resume_calls = []

    async def chat(self, **kwargs):
        self.chat_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if self.result is not None:
            return self.result
        return {
            "success": True,
            "status": "completed",
            "agent": "general",
            "answer": "Hello!",
        }

    async def resume(self, **kwargs):
        self.resume_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if self.result is not None:
            return self.result
        return {
            "success": True,
            "status": "completed",
            "agent": "utility",
            "answer": "Riyadh",
        }


class _ProjectModel:
    def __init__(self, project=None, error=None):
        self.project = {"project_id": 1} if project is None else project
        self.error = error
        self.calls = []

    async def get_project_by_id(self, project_id):
        self.calls.append(project_id)
        if self.error is not None:
            raise self.error
        return self.project


class MultiAgentControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_validates_project_and_maps_public_context(self):
        runtime = _Runtime()
        controller = MultiAgentController(
            runtime=runtime,
            project_model=_ProjectModel(),
        )

        result = await controller.chat(
            project_id=1,
            thread_id=" thread-001 ",
            message=" Hello ",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.project_id, 1)
        self.assertEqual(result.thread_id, "thread-001")
        self.assertEqual(runtime.chat_calls[0]["message"], "Hello")

    async def test_resume_passes_project_to_runtime(self):
        runtime = _Runtime()
        controller = MultiAgentController(
            runtime=runtime,
            project_model=_ProjectModel(),
        )

        result = await controller.resume(
            project_id=7,
            thread_id="thread-007",
            response="Riyadh",
        )

        self.assertEqual(result.agent, "utility")
        self.assertEqual(runtime.resume_calls[0]["project_id"], 7)

    async def test_missing_project_does_not_call_runtime(self):
        runtime = _Runtime()
        project_model = _ProjectModel()
        project_model.project = None
        controller = MultiAgentController(
            runtime=runtime,
            project_model=project_model,
        )

        result = await controller.chat(
            project_id=404,
            thread_id="thread-missing",
            message="Hello",
        )

        self.assertFalse(result.success)
        self.assertIn("was not found", result.error)
        self.assertEqual(runtime.chat_calls, [])

    async def test_runtime_errors_are_returned_safely(self):
        controller = MultiAgentController(
            runtime=_Runtime(error=RuntimeError("private detail")),
            project_model=_ProjectModel(),
        )

        result = await controller.chat(
            project_id=1,
            thread_id="thread-error",
            message="Hello",
        )

        self.assertFalse(result.success)
        self.assertNotIn("private detail", result.error)

    async def test_project_lookup_errors_are_returned_safely(self):
        controller = MultiAgentController(
            runtime=_Runtime(),
            project_model=_ProjectModel(
                error=RuntimeError("database secret"),
            ),
        )

        result = await controller.chat(
            project_id=1,
            thread_id="thread-project-error",
            message="Hello",
        )

        self.assertFalse(result.success)
        self.assertNotIn("database secret", result.error)

    async def test_contradictory_workflow_response_is_not_exposed(self):
        controller = MultiAgentController(
            runtime=_Runtime(
                result={
                    "success": True,
                    "status": "completed",
                    "agent": "general",
                    "answer": None,
                    "error": None,
                }
            ),
            project_model=_ProjectModel(),
        )

        result = await controller.chat(
            project_id=1,
            thread_id="thread-invalid-output",
            message="Hello",
        )

        self.assertFalse(result.success)
        self.assertEqual(result.status, "failed")
        self.assertEqual(
            result.error,
            "The Multi-Agent workflow returned an invalid response.",
        )


if __name__ == "__main__":
    unittest.main()
