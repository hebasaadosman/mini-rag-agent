from typing import Any

from agents.multi_agent.api_schemas import MultiAgentResponse
from pydantic import ValidationError
from validation import MultiAgentOutputContractError, MultiAgentOutputValidator


class MultiAgentController:
    """Validate API context around the provider-agnostic runtime."""

    def __init__(self, *, runtime, project_model) -> None:
        if runtime is None or not callable(getattr(runtime, "chat", None)):
            raise TypeError("runtime must provide chat.")
        if not callable(getattr(runtime, "resume", None)):
            raise TypeError("runtime must provide resume.")
        if project_model is None or not callable(
            getattr(project_model, "get_project_by_id", None)
        ):
            raise TypeError("project_model must provide get_project_by_id.")
        self._runtime = runtime
        self._project_model = project_model

    async def chat(
        self,
        *,
        project_id: int,
        thread_id: str,
        message: str,
    ) -> MultiAgentResponse:
        validation = await self._validate_request(
            project_id=project_id,
            thread_id=thread_id,
            value=message,
            value_name="message",
        )
        if validation is not None:
            return validation

        try:
            result = await self._runtime.chat(
                project_id=project_id,
                thread_id=thread_id.strip(),
                message=message.strip(),
            )
        except ValueError as exc:
            return self._failure(project_id, thread_id, str(exc))
        except RuntimeError:
            return self._failure(
                project_id,
                thread_id,
                "The Multi-Agent workflow could not complete.",
            )
        return self._response(project_id, thread_id, result)

    async def resume(
        self,
        *,
        project_id: int,
        thread_id: str,
        response: str,
    ) -> MultiAgentResponse:
        validation = await self._validate_request(
            project_id=project_id,
            thread_id=thread_id,
            value=response,
            value_name="response",
        )
        if validation is not None:
            return validation

        try:
            result = await self._runtime.resume(
                project_id=project_id,
                thread_id=thread_id.strip(),
                response=response.strip(),
            )
        except ValueError as exc:
            return self._failure(project_id, thread_id, str(exc))
        except RuntimeError:
            return self._failure(
                project_id,
                thread_id,
                "The Multi-Agent workflow could not resume.",
            )
        return self._response(project_id, thread_id, result)

    async def _validate_request(
        self,
        *,
        project_id: int,
        thread_id: str,
        value: str,
        value_name: str,
    ) -> MultiAgentResponse | None:
        normalized_thread_id = str(thread_id or "").strip()
        normalized_value = str(value or "").strip()
        if not normalized_thread_id:
            return self._failure(
                project_id,
                normalized_thread_id,
                "thread_id cannot be blank.",
            )
        if not normalized_value:
            return self._failure(
                project_id,
                normalized_thread_id,
                f"{value_name} cannot be blank.",
            )
        try:
            project = await self._project_model.get_project_by_id(project_id)
        except Exception:
            return self._failure(
                project_id,
                normalized_thread_id,
                "The project could not be validated.",
            )
        if project is None:
            return self._failure(
                project_id,
                normalized_thread_id,
                f"Project with ID {project_id} was not found.",
            )
        return None

    @staticmethod
    def _response(
        project_id: int,
        thread_id: str,
        result: Any,
    ) -> MultiAgentResponse:
        if not isinstance(result, dict):
            return MultiAgentController._failure(
                project_id,
                thread_id,
                "The Multi-Agent workflow returned an invalid response.",
            )
        try:
            payload = {
                **result,
                "project_id": project_id,
                "thread_id": thread_id.strip(),
            }
            MultiAgentOutputValidator.validate(payload)
            return MultiAgentResponse.model_validate(
                payload
            )
        except (MultiAgentOutputContractError, ValidationError):
            return MultiAgentController._failure(
                project_id,
                thread_id,
                "The Multi-Agent workflow returned an invalid response.",
            )

    @staticmethod
    def _failure(
        project_id: int,
        thread_id: str,
        error: str,
    ) -> MultiAgentResponse:
        return MultiAgentResponse(
            success=False,
            status="failed",
            project_id=project_id,
            thread_id=str(thread_id or "").strip(),
            agent=None,
            answer=None,
            error=error,
        )
