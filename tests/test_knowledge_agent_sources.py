import unittest

from controllers.KnowledgeAgentController import (
    KnowledgeAgentController,
)


def _tool_history_item(
    *,
    tool_name: str,
    result: dict,
    execution_success: bool = True,
) -> dict:
    return {
        "tool_name": tool_name,
        "execution_result": {
            "success": execution_success,
            "result": result,
        },
    }


class KnowledgeAgentSourceTests(unittest.TestCase):
    def test_successful_read_asset_returns_the_file_source(self):
        sources = KnowledgeAgentController._extract_sources(
            tool_history=[
                _tool_history_item(
                    tool_name="read_asset",
                    result={
                        "success": True,
                        "asset_id": 17,
                        "asset_name": "report.pdf",
                        "content": "document content",
                    },
                )
            ],
            used_chunk_ids=[],
        )

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].asset_id, 17)
        self.assertEqual(sources[0].asset_name, "report.pdf")
        self.assertIsNone(sources[0].chunk_id)
        self.assertIsNone(sources[0].score)

    def test_repeated_read_asset_source_is_deduplicated(self):
        read_result = {
            "success": True,
            "asset_id": 17,
            "asset_name": "report.pdf",
        }

        sources = KnowledgeAgentController._extract_sources(
            tool_history=[
                _tool_history_item(
                    tool_name="read_asset",
                    result=read_result,
                ),
                _tool_history_item(
                    tool_name="read_asset",
                    result=read_result,
                ),
            ],
            used_chunk_ids=[],
        )

        self.assertEqual(len(sources), 1)

    def test_failed_read_asset_is_not_returned_as_a_source(self):
        sources = KnowledgeAgentController._extract_sources(
            tool_history=[
                _tool_history_item(
                    tool_name="read_asset",
                    result={
                        "success": False,
                        "asset_id": 17,
                        "asset_name": "report.pdf",
                    },
                )
            ],
            used_chunk_ids=[],
        )

        self.assertEqual(sources, [])

    def test_chunk_citations_still_require_real_search_results(self):
        sources = KnowledgeAgentController._extract_sources(
            tool_history=[
                _tool_history_item(
                    tool_name="search_project_chunks",
                    result={
                        "success": True,
                        "results": [
                            {
                                "asset_id": 4,
                                "asset_name": "policy.pdf",
                                "chunk_id": 31,
                                "score": 0.91,
                            }
                        ],
                    },
                )
            ],
            used_chunk_ids=[31, 999],
        )

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].chunk_id, 31)
        self.assertEqual(sources[0].asset_name, "policy.pdf")


if __name__ == "__main__":
    unittest.main()
