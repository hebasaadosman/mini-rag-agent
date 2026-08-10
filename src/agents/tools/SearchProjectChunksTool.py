from typing import Any

from .BaseTool import BaseTool
from agents.knowledge_agent.tools_service import (
    KnowledgeAgentToolsService,
)


class SearchProjectChunksTool(BaseTool):
    name = "search_project_chunks"

    description = (
        "Search the indexed documents of the current project "
        "and return the most relevant text chunks."
    )

    def __init__(
        self,
        tools_service: KnowledgeAgentToolsService,
        project_id: int,
    ) -> None:
        self.tools_service = tools_service
        self.project_id = project_id

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "A focused semantic query for "
                                "searching the current project's "
                                "indexed documents."
                            ),
                            "minLength": 1,
                        },
                        "limit": {
                            "type": "integer",
                            "description": (
                                "Maximum number of chunks to retrieve."
                            ),
                            "minimum": 1,
                            "maximum": 20,
                            "default": 5,
                        },
                    },
                    "required": [
                        "query",
                    ],
                    "additionalProperties": False,
                },
            },
        }

    async def execute(
        self,
        *,
        query: str,
        limit: int = 5,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self.tools_service.search_project_chunks(
            project_id=self.project_id,
            query=query,
            limit=limit,
        )