import asyncio
from pprint import pprint

from agents.knowledge_agent.service import KnowledgeAgent
from agents.tools import (
    SearchProjectChunksTool,
    ToolRegistry,
)
from helpers.config import get_settings
from main import app, startup_db_client
from stores.llm.LLMProviderFactory import LLMProviderFactory


PROJECT_ID = 1


async def main() -> None:
    settings = get_settings()

    await startup_db_client()

    try:
        factory = LLMProviderFactory(
            config=settings.model_dump(),
        )

        llm = factory.create_provider(
            settings.GENERATION_BACKEND,
        )

        llm.set_generation_model(
            settings.GENEERATION_MODEL_ID,
        )

        search_tool = SearchProjectChunksTool(
            tools_service=(
                app.knowledge_agent_tools_service
            ),
            project_id=PROJECT_ID,
        )

        registry = ToolRegistry()

        registry.register_tool(
            search_tool
        )

        print("\nRegistered tools:")
        pprint(
            registry.list_tool_names()
        )

        print("\nTool schemas sent to the LLM:")
        pprint(
            registry.get_schemas()
        )

        agent = KnowledgeAgent(
            llm_provider=llm,
            tool_registry=registry,
            max_iterations=5,
        )

        result = await agent.run(
            user_message=(
                "What is the maximum number "
                "of remote-work days?"
            ),
            system_prompt=(
                "You are a project knowledge assistant. "
                "Use the available tools when an answer "
                "depends on project documents. "
                "Base your answer only on tool results."
            ),
        )

        print("\n" + "=" * 60)
        print("KNOWLEDGE AGENT RESULT")
        print("=" * 60)

        pprint(result)

    finally:
        await app.vectordb_client.disconnect()
        await app.pg_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())