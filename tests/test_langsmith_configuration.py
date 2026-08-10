import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from observability.langsmith import (
    configure_langsmith,
    get_langsmith_project_name,
)


class LangSmithConfigurationTests(unittest.TestCase):
    def test_project_name_includes_environment(self):
        settings = SimpleNamespace(
            LANGSMITH_PROJECT="mini-rag-knowledge-agent",
            APP_ENV="production",
        )

        self.assertEqual(
            get_langsmith_project_name(settings),
            "mini-rag-knowledge-agent-production",
        )

    def test_project_name_does_not_duplicate_environment(self):
        settings = SimpleNamespace(
            LANGSMITH_PROJECT="mini-rag-knowledge-agent-local",
            APP_ENV="local",
        )

        self.assertEqual(
            get_langsmith_project_name(settings),
            "mini-rag-knowledge-agent-local",
        )

    def test_configure_overrides_raw_project_name(self):
        settings = SimpleNamespace(
            LANGSMITH_TRACING=True,
            LANGSMITH_API_KEY="test-key",
            LANGSMITH_PROJECT="mini-rag-knowledge-agent",
            APP_ENV="production",
        )

        with patch.dict(
            os.environ,
            {"LANGSMITH_PROJECT": "mini-rag-knowledge-agent"},
            clear=False,
        ):
            configure_langsmith(settings)
            self.assertEqual(
                os.environ["LANGSMITH_PROJECT"],
                "mini-rag-knowledge-agent-production",
            )
