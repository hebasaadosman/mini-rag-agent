from typing import Any

from .BaseTool import BaseTool


class ReadAssetTool(BaseTool):
    """
    Read the processed textual content of one
    project asset.

    project_id is fixed by the backend.
    asset_id is selected by the LLM from prior
    tool results or supplied by the user.
    """

    name = "read_asset"

    description = (
        "Read the processed textual content of one "
        "specific asset in the current project. "
        "Use this tool when the user asks to open, "
        "read, display, summarize, extract information "
        "from, or analyze a specific file. "
        "A valid asset_id must already be known. "
        "If only a file name is known, first use "
        "search_assets_by_name to resolve it to an "
        "asset_id. Do not use this tool to search "
        "across multiple documents or retrieve file "
        "metadata."
    )

    def __init__(
        self,
        *,
        tools_service,
        project_id: int,
        asset_id: int,
    ) -> None:
        self._tools_service = tools_service
        self._project_id = project_id
        self._asset_id = asset_id

    @property
    def schema(
        self,
    ) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    self.description
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "asset_id": {
                            "type": "integer",
                            "minimum": 1,
                            "description": (
                                "The unique asset ID "
                                "returned by an asset "
                                "search or listing tool."
                            ),
                        },
                        "max_characters": {
                            "type": "integer",
                            "minimum": 1_000,
                            "maximum": 50_000,
                            "default": 20_000,
                            "description": (
                                "Maximum number of "
                                "document characters "
                                "to return."
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
        max_characters: int = 20_000,
    ) -> dict[str, Any]:
        """
        Read one project asset using its resolved ID.
        """

        return await self._tools_service.read_asset(
            project_id=self._project_id,
            asset_id=asset_id,
            max_characters=max_characters,
        )