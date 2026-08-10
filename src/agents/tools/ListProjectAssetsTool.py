from typing import Any

from .BaseTool import BaseTool


class ListProjectAssetsTool(BaseTool):
    """
    List the assets available in the current project.

    The project scope is fixed by the backend.
    The LLM cannot provide or change project_id.
    """

    name = "list_project_assets"

    description = (
        "List the files and assets available in the current "
        "project. Use this tool when the user asks about file "
        "names, the number of files, available documents, or "
        "files of a specific type. Do not use it to search "
        "inside document contents."
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
                        "asset_type": {
                            "type": ["string", "null"],
                            "description": (
                                "General asset category, such as "
                                "file, image, audio, or video."
                            ),
                        },
                        "extension": {
                            "type": ["string", "null"],
                            "description": (
                                "Optional file extension filter, "
                                "such as pdf, docx, txt, or xlsx. "
                                "Do not include the leading dot."
                            ),
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }

    async def execute(
        self,
        *,
        asset_type: str | None = None,
        extension: str | None = None,
    ) -> dict[str, Any]:
        normalized_asset_type = (
            asset_type.strip().lower()
            if isinstance(asset_type, str)
            and asset_type.strip()
            else None
        )

        normalized_extension = (
            extension.strip().lower().lstrip(".")
            if isinstance(extension, str)
            and extension.strip()
            else None
        )

        return await self._tools_service.list_project_assets(
            project_id=self._project_id,
            asset_type=normalized_asset_type,
            extension=normalized_extension,
        )