from typing import Any

from .BaseTool import BaseTool


class GetAssetDetailsTool(BaseTool):
    """
    Retrieve metadata for one project asset by its ID.

    The project scope is controlled by the backend.
    The LLM cannot provide or change project_id.
    """

    name = "get_asset_details"

    description = (
        "Get metadata and details for one specific asset "
        "in the current project using its asset_id. "
        "Use this tool after another tool has resolved "
        "a human-readable file name to a specific asset_id. "
        "It returns information such as the asset name, "
        "type, size, status, and creation date. "
        "Do not use this tool to search inside document "
        "content or to retrieve the full file content."
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
                        "asset_id": {
                            "type": "integer",
                            "minimum": 1,
                            "description": (
                                "The unique ID of the asset "
                                "returned by an asset search "
                                "or listing tool."
                            ),
                        },
                    },
                    "required": [
                        "asset_id",
                    ],
                    "additionalProperties": False,
                },
            },
        }

    async def execute(
        self,
        *,
        asset_id: int,
    ) -> dict[str, Any]:
        if asset_id < 1:
            return {
                "success": False,
                "project_id": self._project_id,
                "asset_id": asset_id,
                "asset": None,
                "error": (
                    "asset_id must be a positive integer."
                ),
            }

        return await self._tools_service.get_asset_details(
            project_id=self._project_id,
            asset_id=asset_id,
        )