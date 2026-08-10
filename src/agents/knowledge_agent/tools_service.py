from typing import Any

from controllers.NLPController import NLPController
from models.AssetModel import AssetModel
from models.ProjectModel import ProjectModel
from models.ChunkModel import ChunkModel
from models.enums import AssetStatus


class KnowledgeAgentToolsService:
    """
    Business-logic service used by the Knowledge Agent tools.

    This class:
    - keeps tool classes thin
    - validates project scope
    - communicates with models and NLPController
    - returns stable JSON-serializable dictionaries
    """

    def __init__(
        self,
        *,
        asset_model: AssetModel,
        project_model: ProjectModel,
        chunk_model: ChunkModel,
        nlp_controller: NLPController,
    ) -> None:
        self.asset_model = asset_model
        self.project_model = project_model
        self.chunk_model = chunk_model
        self.nlp_controller = nlp_controller

    async def list_project_assets(
        self,
        *,
        project_id: int,
        asset_type: str | None = None,
        extension: str | None = None,
    ) -> dict[str, Any]:
        """
        List all assets belonging to one project.

        Optional filters:
        - asset_type: general asset category, such as "file"
        - extension: file extension, such as "pdf" or "docx"
        """

        project = await self.project_model.get_project_by_id(
            project_id=project_id,
        )

        if project is None:
            return {
                "success": False,
                "project_id": project_id,
                "asset_type": asset_type,
                "extension": extension,
                "count": 0,
                "assets": [],
                "error": "Project was not found.",
            }

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

        assets = (
            await self.asset_model
            .get_all_projects_assets(
                asset_project_id=project_id,
                asset_type=normalized_asset_type,
            )
        )

        serialized_assets = [
            self._serialize_asset_summary(asset)
            for asset in assets
        ]

        if normalized_extension:
            expected_suffix = (
                f".{normalized_extension}"
            )

            serialized_assets = [
                asset
                for asset in serialized_assets
                if (
                    asset.get("asset_name", "")
                    .strip()
                    .lower()
                    .endswith(expected_suffix)
                )
            ]

        return {
            "success": True,
            "project_id": project_id,
            "asset_type": normalized_asset_type,
            "extension": normalized_extension,
            "count": len(serialized_assets),
            "assets": serialized_assets,
            "error": None,
        }

    async def search_assets_by_name(
        self,
        *,
        project_id: int,
        query: str,
        limit: int = 5,
    ) -> dict[str, Any]:
        """
        Search project assets using a full or partial name.

        The result explicitly identifies whether one unique
        exact-name match exists, allowing the Agent to use
        its asset_id in a following tool call.
        """

        normalized_query = query.strip().lower()

        if not normalized_query:
            return {
                "success": False,
                "project_id": project_id,
                "query": query,
                "count": 0,
                "matches_complete": False,
                "has_unique_exact_match": False,
                "exact_match": None,
                "assets": [],
                "error": (
                    "Asset name search query "
                    "cannot be empty."
                ),
            }

        normalized_limit = max(
            1,
            min(limit, 20),
        )

        project = await self.project_model.get_project_by_id(
            project_id=project_id,
        )

        if project is None:
            return {
                "success": False,
                "project_id": project_id,
                "query": query,
                "count": 0,
                "matches_complete": False,
                "has_unique_exact_match": False,
                "exact_match": None,
                "assets": [],
                "error": "Project was not found.",
            }

        assets = (
            await self.asset_model
            .get_all_projects_assets(
                asset_project_id=project_id,
            )
        )

        matched_assets: list[
            dict[str, Any]
        ] = []

        for asset in assets:
            asset_name = (
                asset.asset_name
                or ""
            ).strip()

            normalized_asset_name = (
                asset_name.lower()
            )

            if (
                normalized_query
                not in normalized_asset_name
            ):
                continue

            match_type = (
                "exact_name"
                if (
                    normalized_query
                    == normalized_asset_name
                )
                else "partial_name"
            )

            serialized_asset = (
                self._serialize_asset_summary(
                    asset
                )
            )

            serialized_asset["match_type"] = (
                match_type
            )

            matched_assets.append(
                serialized_asset
            )

            if (
                len(matched_assets)
                >= normalized_limit
            ):
                break

        exact_matches = [
            asset
            for asset in matched_assets
            if (
                asset.get("match_type")
                == "exact_name"
            )
        ]

        has_unique_exact_match = (
            len(exact_matches) == 1
        )

        exact_match = (
            exact_matches[0]
            if has_unique_exact_match
            else None
        )

        return {
            "success": True,
            "project_id": project_id,
            "query": query,
            "limit": normalized_limit,
            "count": len(matched_assets),
            "matches_complete": True,
            "has_unique_exact_match": (
                has_unique_exact_match
            ),
            "exact_match": exact_match,
            "assets": matched_assets,
            "message": (
                f"Found {len(matched_assets)} "
                f"assets matching the name "
                f"query '{query}'."
            ),
            "error": None,
        }

    async def get_asset_details(
        self,
        *,
        project_id: int,
        asset_id: int,
    ) -> dict[str, Any]:
        """
        Return detailed metadata for one asset.

        The query is scoped by both project_id and asset_id,
        preventing an asset from another project from being
        exposed.
        """

        if asset_id < 1:
            return {
                "success": False,
                "project_id": project_id,
                "asset_id": asset_id,
                "asset": None,
                "error": (
                    "asset_id must be a "
                    "positive integer."
                ),
            }

        project = await self.project_model.get_project_by_id(
            project_id=project_id,
        )

        if project is None:
            return {
                "success": False,
                "project_id": project_id,
                "asset_id": asset_id,
                "asset": None,
                "error": "Project was not found.",
            }

        asset = await self.asset_model.get_asset_by_id(
            asset_project_id=project_id,
            asset_id=asset_id,
        )

        if asset is None:
            return {
                "success": False,
                "project_id": project_id,
                "asset_id": asset_id,
                "asset": None,
                "error": (
                    "Asset was not found in "
                    "the specified project."
                ),
            }

        return {
            "success": True,
            "project_id": project_id,
            "asset_id": asset_id,
            "asset": self._serialize_asset_details(
                asset
            ),
            "message": (
                "Asset details were retrieved "
                "successfully. Use this result "
                "to answer the user's request."
            ),
            "error": None,
        }
    async def read_asset(
        self,
        *,
        project_id: int,
        asset_id: int,
        max_characters: int = 20_000,
    ) -> dict[str, Any]:
        """
        Reconstruct an asset's text from its stored chunks.

        The content is truncated when it exceeds the
        requested maximum number of characters.
        """

        if asset_id < 1:
            return {
                "success": False,
                "project_id": project_id,
                "asset_id": asset_id,
                "asset_name": None,
                "chunk_count": 0,
                "content": "",
                "total_characters": 0,
                "returned_characters": 0,
                "truncated": False,
                "error": (
                    "asset_id must be a positive integer."
                ),
            }

        normalized_max_characters = max(
            1_000,
            min(max_characters, 50_000),
        )

        asset = await self.asset_model.get_asset_by_id(
            asset_project_id=project_id,
            asset_id=asset_id,
        )

        if asset is None:
            return {
                "success": False,
                "project_id": project_id,
                "asset_id": asset_id,
                "asset_name": None,
                "chunk_count": 0,
                "content": "",
                "total_characters": 0,
                "returned_characters": 0,
                "truncated": False,
                "error": (
                    "Asset was not found in the "
                    "specified project."
                ),
            }

        chunks = await self.chunk_model.get_asset_content(
            project_id=project_id,
            asset_id=asset_id,
        )

        if not chunks:
            return {
                "success": False,
                "project_id": project_id,
                "asset_id": asset_id,
                "asset_name": asset.asset_name,
                "chunk_count": 0,
                "content": "",
                "total_characters": 0,
                "returned_characters": 0,
                "truncated": False,
                "error": (
                    "The asset has no processed text chunks. "
                    "It may need to be processed first."
                ),
            }

        chunk_texts = [
            (chunk.chunk_text or "").strip()
            for chunk in chunks
            if (chunk.chunk_text or "").strip()
        ]

        full_content = "\n\n".join(
            chunk_texts
        )

        total_characters = len(
            full_content
        )

        truncated = (
            total_characters
            > normalized_max_characters
        )

        content = (
            full_content[
                :normalized_max_characters
            ].rstrip()
            if truncated
            else full_content
        )

        return {
            "success": True,
            "project_id": project_id,
            "asset_id": asset_id,
            "asset_name": asset.asset_name,
            "chunk_count": len(chunks),
            "content": content,
            "total_characters": total_characters,
            "returned_characters": len(content),
            "truncated": truncated,
            "message": (
                "Asset text was reconstructed "
                "successfully from stored chunks."
            ),
            "error": None,
        }
                         
    async def get_asset_processing_status(
        self,
        *,
        project_id: int,
        asset_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Return processing status for one asset or all project
        assets.
        """

        project = await self.project_model.get_project_by_id(
            project_id=project_id,
        )

        if project is None:
            return {
                "success": False,
                "project_id": project_id,
                "asset_id": asset_id,
                "error": "Project was not found.",
            }

        if asset_id is not None:
            asset = await self.asset_model.get_asset_by_id(
                asset_project_id=project_id,
                asset_id=asset_id,
            )

            if asset is None:
                return {
                    "success": False,
                    "project_id": project_id,
                    "asset_id": asset_id,
                    "asset": None,
                    "error": (
                        "Asset was not found in "
                        "the specified project."
                    ),
                }

            return {
                "success": True,
                "project_id": project_id,
                "asset_id": asset.asset_id,
                "asset_name": asset.asset_name,
                "asset_status": (
                    asset.asset_status
                ),
                "asset_progress": (
                    asset.asset_progress
                ),
                "ready_for_search": (
                    self._is_searchable(asset)
                ),
                "error": None,
            }

        assets = (
            await self.asset_model
            .get_all_projects_assets(
                asset_project_id=project_id,
            )
        )

        return {
            "success": True,
            "project_id": project_id,
            "total_assets": len(assets),
            "assets": [
                {
                    "asset_id": asset.asset_id,
                    "asset_name": (
                        asset.asset_name
                    ),
                    "asset_status": (
                        asset.asset_status
                    ),
                    "asset_progress": (
                        asset.asset_progress
                    ),
                    "ready_for_search": (
                        self._is_searchable(
                            asset
                        )
                    ),
                }
                for asset in assets
            ],
            "error": None,
        }

    async def search_project_chunks(
        self,
        *,
        project_id: int,
        query: str,
        limit: int = 5,
    ) -> dict[str, Any]:
        """
        Search the vector collection of one project.

        This method reuses NLPController retrieval and returns
        stable JSON-serializable results.
        """

        normalized_query = query.strip()

        if not normalized_query:
            return {
                "success": False,
                "project_id": project_id,
                "query": query,
                "limit": limit,
                "result_count": 0,
                "results": [],
                "error": (
                    "Search query cannot be empty."
                ),
            }

        normalized_limit = max(
            1,
            min(limit, 20),
        )

        project = await self.project_model.get_project_by_id(
            project_id=project_id,
        )

        if project is None:
            return {
                "success": False,
                "project_id": project_id,
                "query": normalized_query,
                "limit": normalized_limit,
                "result_count": 0,
                "results": [],
                "error": "Project was not found.",
            }

        search_success, search_result = (
            await self.nlp_controller
            .search_in_vectordb(
                project=project,
                query=normalized_query,
                limit=normalized_limit,
            )
        )

        if not search_success:
            return {
                "success": False,
                "project_id": project_id,
                "query": normalized_query,
                "limit": normalized_limit,
                "result_count": 0,
                "results": [],
                "error": str(search_result),
            }

        serialized_results = [
            self._serialize_search_result(
                result
            )
            for result in search_result
        ]

        return {
            "success": True,
            "project_id": project_id,
            "query": normalized_query,
            "limit": normalized_limit,
            "result_count": (
                len(serialized_results)
            ),
            "results": serialized_results,
            "error": None,
        }

    @staticmethod
    def _serialize_asset_summary(
        asset,
    ) -> dict[str, Any]:
        """
        Serialize asset metadata suitable for list/search
        responses.
        """

        return {
            "asset_id": asset.asset_id,
            "asset_uuid": str(
                asset.asset_uuid
            ),
            "asset_name": asset.asset_name,
            "asset_type": asset.asset_type,
            "asset_size": asset.asset_size,
            "asset_status": asset.asset_status,
            "asset_progress": (
                asset.asset_progress
            ),
            "checksum_available": bool(
                asset.asset_checksum
            ),
            "created_at": (
                asset.created_at.isoformat()
                if asset.created_at
                else None
            ),
        }

    @staticmethod
    def _serialize_asset_details(
        asset,
    ) -> dict[str, Any]:
        """
        Serialize detailed asset metadata.
        """

        return {
            **KnowledgeAgentToolsService
            ._serialize_asset_summary(
                asset
            ),
            "asset_config": (
                asset.asset_config
            ),
            "updated_at": (
                asset.updated_at.isoformat()
                if asset.updated_at
                else None
            ),
        }

    @staticmethod
    def _serialize_search_result(
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Normalize one vector-search result.
        """

        return {
            "chunk_id": result.get(
                "chunk_id"
            ),
            "asset_id": result.get(
                "asset_id"
            ),
            "asset_name": result.get(
                "asset_name"
            ),
            "text": result.get(
                "text",
                "",
            ),
            "score": result.get("score"),
            "metadata": (
                result.get("metadata")
                or {}
            ),
        }

    @staticmethod
    def _is_searchable(
        asset,
    ) -> bool:
        """
        Check whether the asset completed processing and can
        be searched.
        """

        return (
            asset.asset_status
            == AssetStatus.COMPLETED.value
        )