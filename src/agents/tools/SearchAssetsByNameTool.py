from typing import Any

from .BaseTool import BaseTool


class SearchAssetsByNameTool(BaseTool):
    """
    Search for project assets by human-readable name.

    The project scope is fixed by the backend.
    The LLM cannot provide or change project_id.
    """

    name = "search_assets_by_name"

    description = (
     "List all assets available in the current project, "
    "optionally filtered by general asset type or file "
    "extension. Use this tool only when the user asks for "
    "the complete asset list, total asset count, or assets "
    "of a specific type or extension. Do not use it to "
    "verify or re-check results already returned by "
    "search_assets_by_name."
)

    def __init__(
        self,
        *,
        tools_service,
        project_id: int,
    ) -> None:
        self._tools_service = tools_service
        self._project_id = project_id

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
                            "minLength": 1,
                            "description": (
                                "The full or partial asset name "
                                "to search for."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 20,
                            "default": 5,
                            "description": (
                                "Maximum number of matching "
                                "assets to return."
                            ),
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
    ) -> dict[str, Any]:
        normalized_query = query.strip()

        if not normalized_query:
            return {
                "success": False,
                "project_id": self._project_id,
                "query": query,
                "count": 0,
                "assets": [],
                "error": (
                    "The asset search query cannot be empty."
                ),
            }

        return await self._tools_service.search_assets_by_name(
            project_id=self._project_id,
            query=normalized_query,
            limit=limit,
        )