from typing import Any

from .state import KnowledgeAgentState


def __getattr__(name: str) -> Any:
    if name != "KnowledgeAgent":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from .service import KnowledgeAgent

    globals()[name] = KnowledgeAgent
    return KnowledgeAgent

__all__ = [
    "KnowledgeAgent",
    "KnowledgeAgentState",
]
