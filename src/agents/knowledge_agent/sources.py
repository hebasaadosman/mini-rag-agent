"""Source extraction shared by direct and routed knowledge-agent responses."""

from typing import Any

from .schemas import KnowledgeAgentSource


def extract_grounded_sources(
    *,
    tool_history: list[dict[str, Any]],
    used_chunk_ids: list[int],
) -> list[KnowledgeAgentSource]:
    """Return only sources supported by successful retrieval tool calls."""
    source_by_chunk_id: dict[int, KnowledgeAgentSource] = {}
    read_asset_sources: list[KnowledgeAgentSource] = []
    seen_read_assets: set[tuple[int | None, str]] = set()

    for history_item in tool_history:
        execution_result = history_item.get("execution_result") or {}
        if not execution_result.get("success"):
            continue
        tool_result = execution_result.get("result") or {}
        if not tool_result.get("success"):
            continue

        if history_item.get("tool_name") == "read_asset":
            asset_name = str(tool_result.get("asset_name") or "").strip()
            asset_id = tool_result.get("asset_id")
            if not asset_name:
                continue
            normalized_asset_id = asset_id if isinstance(asset_id, int) else None
            source_key = (normalized_asset_id, asset_name)
            if source_key in seen_read_assets:
                continue
            seen_read_assets.add(source_key)
            read_asset_sources.append(
                KnowledgeAgentSource(
                    asset_id=normalized_asset_id,
                    asset_name=asset_name,
                )
            )
            continue

        if history_item.get("tool_name") != "search_project_chunks":
            continue
        for item in tool_result.get("results") or []:
            chunk_id = item.get("chunk_id")
            if not isinstance(chunk_id, int):
                continue
            source_by_chunk_id[chunk_id] = KnowledgeAgentSource(
                asset_id=item.get("asset_id"),
                asset_name=item.get("asset_name"),
                chunk_id=chunk_id,
                score=item.get("score"),
            )

    selected_sources = list(read_asset_sources)
    seen_chunk_ids: set[int] = set()
    for chunk_id in used_chunk_ids:
        if chunk_id in seen_chunk_ids:
            continue
        source = source_by_chunk_id.get(chunk_id)
        if source is None:
            continue
        seen_chunk_ids.add(chunk_id)
        selected_sources.append(source)
    return selected_sources
