from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    """Trusted application context supplied outside of the LLM payload."""

    project_id: int | None = None
    thread_id: str | None = None
    principal_id: str | None = None
    approval_id: str | None = None


class ToolExecutionDenied(PermissionError):
    """Raised when a server-side policy blocks a tool execution."""


class ToolExecutionGuard(Protocol):
    """Authorize a tool call before its implementation is invoked."""

    def authorize(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolExecutionContext | None,
    ) -> None: ...


class AllowlistToolExecutionGuard:
    """Small server-side policy for allowed and approval-gated tools.

    The LLM can request a tool, but it cannot grant itself access to one.
    Authentication and user permissions are intentionally not handled here;
    they will be supplied as trusted context by the Auth/AuthZ boundary.
    """

    def __init__(
        self,
        *,
        allowed_tools: set[str] | frozenset[str],
        approval_required_tools: set[str] | frozenset[str] = frozenset(),
    ) -> None:
        self._allowed_tools = frozenset(self._normalize_names(allowed_tools))
        self._approval_required_tools = frozenset(
            self._normalize_names(
                approval_required_tools,
                allow_empty=True,
            )
        )
        unsupported = (
            self._approval_required_tools - self._allowed_tools
        )
        if unsupported:
            raise ValueError(
                "approval_required_tools must also be allowed tools."
            )

    def authorize(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolExecutionContext | None,
    ) -> None:
        normalized_name = str(tool_name or "").strip()
        if normalized_name not in self._allowed_tools:
            raise ToolExecutionDenied(
                f"Tool '{normalized_name or 'unknown'}' is not allowed."
            )
        if not isinstance(arguments, dict):
            raise ToolExecutionDenied("Tool arguments must be an object.")
        if (
            normalized_name in self._approval_required_tools
            and not str((context or ToolExecutionContext()).approval_id or "").strip()
        ):
            raise ToolExecutionDenied(
                f"Tool '{normalized_name}' requires an approved action."
            )

    @staticmethod
    def _normalize_names(
        names: set[str] | frozenset[str],
        *,
        allow_empty: bool = False,
    ) -> set[str]:
        normalized = {str(name or "").strip() for name in names}
        if (not allow_empty and not normalized) or "" in normalized:
            raise ValueError("Tool policy names must be non-blank.")
        return normalized
