from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    name: str
    description: str

    @property
    @abstractmethod
    def schema(self) -> dict[str, Any]:
        """JSON schema sent to the LLM."""
        pass

    @abstractmethod
    async def execute(
        self,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute the tool and return JSON-safe data."""
        pass