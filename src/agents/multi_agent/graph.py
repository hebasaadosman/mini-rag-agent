from functools import partial
from typing import Any

from langgraph.graph import END, START, StateGraph

from .conversation_gate_router import (
    ConversationGateDestination,
    ConversationGateRouter,
)
from .nodes import (
    ConversationGateNode,
    FailureNode,
    GateRejectionNode,
    GateSwitchConfirmationNode,
    SupervisorClarificationNode,
)
from .specialist_result_router import (
    SpecialistResultDestination,
    SpecialistResultRouter,
)
from .state import AgentName, MultiAgentState
from .supervisor_router import (
    SupervisorDestination,
    SupervisorRouter,
)


class MultiAgentGraph:
    """Assemble the already-independent agents into one LangGraph workflow."""

    def __init__(
        self,
        *,
        supervisor: Any,
        knowledge_agent: Any,
        utility_agent: Any,
        general_agent: Any,
        email_agent: Any,
        checkpointer: Any = None,
    ) -> None:
        self._supervisor = self._require_resumable(
            "supervisor",
            supervisor,
        )
        self._knowledge_agent = self._require_specialist(
            "knowledge_agent",
            knowledge_agent,
        )
        self._utility_agent = self._require_specialist(
            "utility_agent",
            utility_agent,
        )
        self._general_agent = self._require_specialist(
            "general_agent",
            general_agent,
        )
        self._email_agent = self._require_specialist(
            "email_agent",
            email_agent,
        )
        self._checkpointer = checkpointer
        self._conversation_gate_node = ConversationGateNode()
        self._switch_confirmation_node = GateSwitchConfirmationNode()
        self._rejection_node = GateRejectionNode()
        self._failure_node = FailureNode()
        self._supervisor_clarification_node = SupervisorClarificationNode()
        self._builder = self._build_builder()
        self._graph = self._builder.compile(
            checkpointer=self._checkpointer,
        )

    @property
    def compiled_graph(self) -> Any:
        """Return the compiled workflow used by the runtime boundary."""

        return self._graph

    @property
    def has_checkpointer(self) -> bool:
        """Report whether conversation state can persist between calls."""

        return self._checkpointer is not None

    def _build_builder(self) -> StateGraph:
        builder = self._create_builder()
        builder.add_node(
            "conversation_gate",
            self._conversation_gate_node,
        )
        self._register_execution_nodes(builder)
        builder.add_edge(
            START,
            "conversation_gate",
        )
        builder.add_conditional_edges(
            "conversation_gate",
            ConversationGateRouter.route,
            {
                ConversationGateDestination.SUPERVISOR: "supervisor",
                ConversationGateDestination.RESUME_SUPERVISOR: (
                    "resume_supervisor"
                ),
                ConversationGateDestination.RESUME_KNOWLEDGE: (
                    "resume_knowledge"
                ),
                ConversationGateDestination.RESUME_UTILITY: (
                    "resume_utility"
                ),
                ConversationGateDestination.RESUME_GENERAL: (
                    "resume_general"
                ),
                ConversationGateDestination.RESUME_EMAIL: "resume_email",
                ConversationGateDestination.REQUEST_SWITCH_CONFIRMATION: (
                    "request_switch_confirmation"
                ),
                ConversationGateDestination.REJECTION: "rejection",
                ConversationGateDestination.FAILURE: "failure",
            },
        )
        self._add_supervisor_routes(builder, "supervisor")
        self._add_supervisor_routes(builder, "resume_supervisor")
        self._add_specialist_routes(
            builder,
            "knowledge",
            AgentName.KNOWLEDGE,
        )
        self._add_specialist_routes(
            builder,
            "resume_knowledge",
            AgentName.KNOWLEDGE,
        )
        self._add_specialist_routes(
            builder,
            "utility",
            AgentName.UTILITY,
        )
        self._add_specialist_routes(
            builder,
            "resume_utility",
            AgentName.UTILITY,
        )
        self._add_specialist_routes(
            builder,
            "general",
            AgentName.GENERAL,
        )
        self._add_specialist_routes(
            builder,
            "resume_general",
            AgentName.GENERAL,
        )
        self._add_specialist_routes(
            builder,
            "email",
            AgentName.EMAIL,
        )
        self._add_specialist_routes(
            builder,
            "resume_email",
            AgentName.EMAIL,
        )
        for terminal_node in (
            "supervisor_clarification",
            "request_switch_confirmation",
            "rejection",
            "failure",
        ):
            builder.add_edge(terminal_node, END)
        return builder

    @staticmethod
    def _add_supervisor_routes(
        builder: StateGraph,
        source_node: str,
    ) -> None:
        builder.add_conditional_edges(
            source_node,
            SupervisorRouter.route,
            {
                SupervisorDestination.KNOWLEDGE: "knowledge",
                SupervisorDestination.UTILITY: "utility",
                SupervisorDestination.GENERAL: "general",
                SupervisorDestination.EMAIL: "email",
                SupervisorDestination.CLARIFICATION: (
                    "supervisor_clarification"
                ),
                SupervisorDestination.FAILURE: "failure",
            },
        )

    @staticmethod
    def _add_specialist_routes(
        builder: StateGraph,
        source_node: str,
        expected_agent: AgentName,
    ) -> None:
        builder.add_conditional_edges(
            source_node,
            partial(
                SpecialistResultRouter.route,
                expected_agent=expected_agent,
            ),
            {
                SpecialistResultDestination.SUPERVISOR: "supervisor",
                SpecialistResultDestination.END: END,
                SpecialistResultDestination.FAILURE: "failure",
            },
        )

    def _register_execution_nodes(self, builder: StateGraph) -> None:
        builder.add_node(
            "supervisor",
            self._supervisor,
        )
        builder.add_node(
            "resume_supervisor",
            self._supervisor.resume,
        )
        builder.add_node(
            "supervisor_clarification",
            self._supervisor_clarification_node,
        )

        builder.add_node(
            "knowledge",
            self._knowledge_agent,
        )
        builder.add_node(
            "utility",
            self._utility_agent,
        )
        builder.add_node(
            "general",
            self._general_agent,
        )
        builder.add_node(
            "email",
            self._email_agent,
        )

        builder.add_node(
            "resume_knowledge",
            self._knowledge_agent.resume,
        )
        builder.add_node(
            "resume_utility",
            self._utility_agent.resume,
        )
        builder.add_node(
            "resume_general",
            self._general_agent.resume,
        )
        builder.add_node(
            "resume_email",
            self._email_agent.resume,
        )

        builder.add_node(
            "request_switch_confirmation",
            self._switch_confirmation_node,
        )
        builder.add_node(
            "rejection",
            self._rejection_node,
        )
        builder.add_node(
            "failure",
            self._failure_node,
        )

    @staticmethod
    def _create_builder() -> StateGraph:
        return StateGraph(MultiAgentState)

    @staticmethod
    def _require_callable(name: str, dependency: Any) -> Any:
        if not callable(dependency):
            raise TypeError(f"{name} must be callable.")
        return dependency

    @classmethod
    def _require_specialist(cls, name: str, dependency: Any) -> Any:
        return cls._require_resumable(name, dependency)

    @classmethod
    def _require_resumable(cls, name: str, dependency: Any) -> Any:
        resumable = cls._require_callable(name, dependency)
        if not callable(getattr(resumable, "resume", None)):
            raise TypeError(f"{name} must provide an async resume method.")
        return resumable
