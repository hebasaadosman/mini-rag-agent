from .LLMEnum import LLMEnum
from stores.llm.providers.OpenAIProvider import OpenAIProvider
from stores.llm.providers.CohereProvider import CohereProvider
    

class LLMProviderFactory:
    def __init__(self, config: dict):
        self.config = config

    def create_provider(self, provider_name: str):
        if provider_name == LLMEnum.OPENAI.value:
            return OpenAIProvider(
                api_key=self.config.get("OPENAI_API_KEY"),
                api_url=self.config.get("OPENAI_API_URL"),
                default_input_max_characters=self.config.get("INPUT_DEFAULT_MAX_CHARACTERS"),
                default_generation_max_output_tokens=self.config.get("GENERATION_DEFAULT_MAX_TOKENS"),
                default_generation_temperature=self.config.get("GENERATION_DEFAULT_TEMPERATURE"),
                generation_model_id=self.config.get("GENEERATION_MODEL_ID")
            )
        elif provider_name == LLMEnum.COHERE.value:
            return CohereProvider(
                api_key=self.config.get("COHERE_API_KEY"),
                default_input_max_characters=self.config.get("INPUT_DEFAULT_MAX_CHARACTERS"),
                default_generation_max_output_tokens=self.config.get("GENERATION_DEFAULT_MAX_TOKENS"),
                default_generation_temperature=self.config.get("GENERATION_DEFAULT_TEMPERATURE"),
                generation_model_id=self.config.get("GENEERATION_MODEL_ID"),
            )
        else:
            raise ValueError(f"Unknown provider: {provider_name}")      

    def create_multi_agent_runtime(
        self,
        *,
        llm_provider,
        knowledge_agent_factory,
        send_email_tool=None,
        checkpointer=None,
        utility_tool_registry=None,
        max_memory_messages: int = 40,
    ):
        """Build the agent workflow around an OpenAI or Cohere provider."""

        from agents.multi_agent import (
            EmailAgent,
            GeneralAgent,
            KnowledgeSpecialistAdapter,
            MultiAgentGraph,
            MultiAgentRuntime,
            SupervisorAgent,
            UtilityAgent,
        )
        from agents.tools import SendEmailTool, ToolRegistry

        if llm_provider is None:
            raise TypeError("llm_provider is required.")
        if not callable(knowledge_agent_factory):
            raise TypeError("knowledge_agent_factory must be callable.")
        if send_email_tool is not None and not isinstance(
            send_email_tool,
            SendEmailTool,
        ):
            raise TypeError("send_email_tool must be a SendEmailTool.")
        if (
            utility_tool_registry is not None
            and not isinstance(utility_tool_registry, ToolRegistry)
        ):
            raise TypeError(
                "utility_tool_registry must be a ToolRegistry."
            )
        if max_memory_messages < 2:
            raise ValueError("max_memory_messages must be at least 2.")

        email_agent = (
            EmailAgent(
                llm_provider=llm_provider,
                send_email_tool=send_email_tool,
                max_memory_messages=max_memory_messages,
            )
            if send_email_tool is not None
            else _UnavailableEmailAgent()
        )
        graph = MultiAgentGraph(
            supervisor=SupervisorAgent(llm_provider=llm_provider),
            knowledge_agent=KnowledgeSpecialistAdapter(
                agent_factory=knowledge_agent_factory,
                max_memory_messages=max_memory_messages,
            ),
            utility_agent=UtilityAgent(
                llm_provider=llm_provider,
                tool_registry=utility_tool_registry,
                max_memory_messages=max_memory_messages,
            ),
            general_agent=GeneralAgent(
                llm_provider=llm_provider,
                max_memory_messages=max_memory_messages,
            ),
            email_agent=email_agent,
            checkpointer=checkpointer,
        )
        return MultiAgentRuntime(graph)


class _UnavailableEmailAgent:
    """Keep non-email agents available when SMTP is disabled."""

    async def __call__(self, state):
        return self._failure()

    async def resume(self, state):
        return self._failure()

    @staticmethod
    def _failure():
        return {
            "active_agent": "email",
            "resume_target": None,
            "task_status": "failed",
            "pending_interrupt": None,
            "pending_user_message": None,
            "final_response": None,
            "error": "Outbound email is not configured.",
        }
