import asyncio
import json
from typing import Any

from .general_prompts import (
    build_general_agent_system_prompt,
    build_general_semantic_review_prompt,
)
from .general_schemas import GeneralSemanticReview
from .handoff import build_handoff_update
from .specialist_parser import (
    SpecialistResponseParseError,
    SpecialistResponseParser,
)
from .specialist_hitl import (
    ClarificationIdFactory,
    SpecialistResumeError,
    build_specialist_clarification_update,
    get_specialist_resume_message,
)
from .specialist_schemas import SpecialistAction, SpecialistResponse
from .state import AgentName, MultiAgentState, TaskStatus


class GeneralAgent:
    def __init__(
        self,
        *,
        llm_provider,
        max_tokens: int = 500,
        temperature: float = 0.2,
        max_memory_messages: int = 40,
        interrupt_id_factory: ClarificationIdFactory | None = None,
    ) -> None:
        if max_memory_messages < 2:
            raise ValueError("max_memory_messages must be at least 2.")

        self._llm_provider = llm_provider
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._max_memory_messages = max_memory_messages
        self._interrupt_id_factory = interrupt_id_factory

    async def __call__(
        self,
        state: MultiAgentState,
    ) -> dict[str, Any]:
        user_message = str(state.get("user_message") or "").strip()
        if not user_message:
            return self._failure("user_message cannot be blank.")

        return await self._run(state, user_message=user_message)

    async def resume(
        self,
        state: MultiAgentState,
    ) -> dict[str, Any]:
        try:
            response = get_specialist_resume_message(
                state,
                target_agent=AgentName.GENERAL,
            )
        except SpecialistResumeError as exc:
            return self._failure(str(exc))

        return await self._run(state, user_message=response)

    async def _run(
        self,
        state: MultiAgentState,
        *,
        user_message: str,
    ) -> dict[str, Any]:

        canonical_history = self._normalize_history(
            state.get("messages") or []
        )

        try:
            chat_history = self._build_provider_history(
                canonical_history
            )
            content = await asyncio.to_thread(
                self._llm_provider.generate_text,
                user_message,
                chat_history=chat_history,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
        except Exception:
            return self._failure("Failed to call the general agent LLM.")

        try:
            response = SpecialistResponseParser.parse(content)
        except SpecialistResponseParseError:
            response = await self._repair_response(
                user_message=user_message,
                chat_history=chat_history,
            )
            if response is None:
                return self._failure(
                    "The general agent returned an invalid response."
                )

        response = await self._review_decision(
            user_message=user_message,
            canonical_history=canonical_history,
        )
        if response is None:
            return self._failure(
                "The general agent decision could not be verified."
            )

        if response.action == SpecialistAction.HANDOFF:
            return build_handoff_update(
                state,
                from_agent=AgentName.GENERAL,
                reason=response.handoff_reason,
            )

        if response.action == SpecialistAction.CLARIFICATION:
            try:
                return build_specialist_clarification_update(
                    state,
                    from_agent=AgentName.GENERAL,
                    input_message=user_message,
                    question=response.question,
                    options=response.options,
                    max_memory_messages=self._max_memory_messages,
                    interrupt_id_factory=self._interrupt_id_factory,
                )
            except ValueError:
                return self._failure(
                    "The general agent returned invalid clarification."
                )

        normalized_answer = response.answer

        retained_limit = self._max_memory_messages - 2
        retained_history = (
            canonical_history[-retained_limit:]
            if retained_limit
            else []
        )
        while (
            retained_history
            and retained_history[0]["role"] != "user"
        ):
            retained_history.pop(0)

        messages = [
            *retained_history,
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": normalized_answer},
        ]

        return {
            "messages": messages,
            "active_agent": AgentName.GENERAL.value,
            "resume_target": None,
            "task_status": TaskStatus.COMPLETED.value,
            "pending_interrupt": None,
            "pending_user_message": None,
            "handoff_reason": None,
            "final_response": {
                "success": True,
                "status": TaskStatus.COMPLETED.value,
                "agent": AgentName.GENERAL.value,
                "answer": normalized_answer,
            },
            "error": None,
        }

    async def _repair_response(
        self,
        *,
        user_message: str,
        chat_history: list[dict[str, Any]],
    ):
        repair_prompt = (
            "Your previous response did not match the required JSON "
            "contract. Re-evaluate the original user request below and "
            "return exactly one valid JSON object using one of the answer, "
            "clarification, or handoff shapes from the system prompt. Do "
            "not use Markdown or add commentary.\n\nOriginal user request:\n"
            f"{user_message}"
        )
        try:
            repaired_content = await asyncio.to_thread(
                self._llm_provider.generate_text,
                repair_prompt,
                chat_history=chat_history,
                max_tokens=self._max_tokens,
                temperature=0,
            )
            return SpecialistResponseParser.parse(repaired_content)
        except Exception:
            return None

    async def _review_decision(
        self,
        *,
        user_message: str,
        canonical_history: list[dict[str, str]],
    ) -> SpecialistResponse | None:
        """Resolve a General decision independently before publishing it."""

        review_input = json.dumps(
            {
                "task_instruction": (
                    "original_request is the current user turn. Use "
                    "conversation_context only to resolve references; answer "
                    "the current request and do not repeat the last assistant "
                    "answer unless the current turn asks for it."
                ),
                "conversation_context": canonical_history,
                "original_request": user_message,
                "current_request_focus": sorted(
                    self._informative_terms(user_message)
                ),
            },
            ensure_ascii=False,
        )
        focus_terms = self._informative_terms(user_message)
        if canonical_history and focus_terms:
            focused_request = (
                "Answer this follow-up using the conversation context below. "
                "The CURRENT REQUEST is the final line; answer it rather than "
                "repeating the previous answer.\n\nConversation context:\n"
                f"{self._format_history(canonical_history)}\n\n"
                f"CURRENT REQUEST: {user_message}"
            )
            try:
                system_message = self._llm_provider.construct_prompt(
                    prompt=build_general_agent_system_prompt(),
                    role=self._llm_provider.enums.SYSTEM.value,
                )
                focused_content = await asyncio.to_thread(
                    self._llm_provider.generate_text,
                    focused_request,
                    chat_history=[system_message],
                    max_tokens=self._max_tokens,
                    temperature=0,
                )
                focused_response = SpecialistResponseParser.parse(
                    focused_content
                )
                if (
                    focused_response.action == SpecialistAction.ANSWER
                    and self._answer_addresses_focus(
                        focused_response.answer or "",
                        focus_terms,
                    )
                ):
                    return focused_response
            except Exception:
                pass
        try:
            system_message = self._llm_provider.construct_prompt(
                prompt=build_general_semantic_review_prompt(),
                role=self._llm_provider.enums.SYSTEM.value,
            )
            reviewed_content = await asyncio.to_thread(
                self._llm_provider.generate_text,
                review_input,
                chat_history=[system_message],
                max_tokens=self._max_tokens,
                temperature=0,
            )
            raw_review = json.loads(reviewed_content)
            review = GeneralSemanticReview.model_validate(raw_review)
        except Exception:
            return None

        if not self._review_addresses_current_request(
            review,
            user_message=user_message,
        ):
            review = await self._repair_review(
                review_input=review_input,
            )
            if review is None:
                return None

        payload = {
            "action": review.action.value,
            "answer": review.answer,
            "handoff_reason": (
                review.handoff_reason.value
                if review.handoff_reason is not None
                else None
            ),
            "question": review.question,
            "options": review.options,
        }
        try:
            return SpecialistResponseParser.parse(
                json.dumps(payload, ensure_ascii=False)
            )
        except SpecialistResponseParseError:
            return None

    async def _repair_review(
        self,
        *,
        review_input: str,
    ) -> GeneralSemanticReview | None:
        try:
            system_message = self._llm_provider.construct_prompt(
                prompt=(
                    f"{build_general_semantic_review_prompt()}\n\n"
                    "The previous review did not answer the current request. "
                    "Resolve follow-up pronouns and omitted entities from "
                    "conversation_context, then answer the attribute requested "
                    "by original_request. Do not repeat an earlier answer for a "
                    "different attribute."
                ),
                role=self._llm_provider.enums.SYSTEM.value,
            )
            repaired_content = await asyncio.to_thread(
                self._llm_provider.generate_text,
                review_input,
                chat_history=[system_message],
                max_tokens=self._max_tokens,
                temperature=0,
            )
            return GeneralSemanticReview.model_validate_json(
                repaired_content
            )
        except Exception:
            return None

    @staticmethod
    def _review_addresses_current_request(
        review: GeneralSemanticReview,
        *,
        user_message: str,
    ) -> bool:
        if review.action != SpecialistAction.ANSWER:
            return True
        requested_terms = GeneralAgent._informative_terms(user_message)
        if not requested_terms:
            return True
        evidence = GeneralAgent._normalize_arabic_text(
            " ".join(
                [
                    review.verdict,
                    review.answer or "",
                    *review.entity_types,
                ]
            ).casefold()
        )
        return any(term in evidence for term in requested_terms)

    @staticmethod
    def _answer_addresses_focus(
        answer: str,
        focus_terms: set[str],
    ) -> bool:
        evidence = GeneralAgent._normalize_arabic_text(
            answer.casefold()
        )
        return any(term in evidence for term in focus_terms)

    @staticmethod
    def _informative_terms(user_message: str) -> set[str]:
        stop_words = GeneralAgent._normalize_arabic_terms({
            "and", "the", "what", "which", "this", "that", "its", "his", "her",
            "their", "official", "و", "ما", "ماذا", "هي", "هو",
            "وما", "له", "لها", "التي", "الذي", "الرسمية", "رسمي",
        })
        normalized = GeneralAgent._normalize_arabic_text("".join(
            character if character.isalnum() else " "
            for character in user_message.casefold()
        ))
        terms: set[str] = set()
        for raw_term in normalized.split():
            term = raw_term
            if term.startswith("و") and len(term) > 4:
                term = term[1:]
            if term.endswith("ها") and len(term) > 4:
                term = term[:-2]
                if term.endswith("ت"):
                    term = f"{term[:-1]}ة"
            elif term.endswith("ي") and len(term) > 3:
                term = term[:-1]
            if len(term) > 2 and term not in stop_words:
                terms.add(term)
        return terms

    @staticmethod
    def _normalize_arabic_text(value: str) -> str:
        return value.translate(
            str.maketrans(
                {
                    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
                    "ى": "ي", "ؤ": "و", "ئ": "ي", "ـ": "",
                }
            )
        )

    @staticmethod
    def _normalize_arabic_terms(values: set[str]) -> set[str]:
        return {
            GeneralAgent._normalize_arabic_text(value)
            for value in values
        }

    @staticmethod
    def _format_history(messages: list[dict[str, str]]) -> str:
        return "\n".join(
            f"{message['role']}: {message['content']}"
            for message in messages
        )

    def _build_provider_history(
        self,
        canonical_history: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        role_map = {
            "user": self._llm_provider.enums.USER.value,
            "assistant": self._llm_provider.enums.ASSISTANT.value,
        }
        history = [
            self._llm_provider.construct_prompt(
                prompt=build_general_agent_system_prompt(),
                role=self._llm_provider.enums.SYSTEM.value,
            )
        ]

        for message in canonical_history:
            history.append(
                self._llm_provider.construct_prompt(
                    prompt=message["content"],
                    role=role_map[message["role"]],
                )
            )

        return history

    @staticmethod
    def _normalize_history(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for message in messages:
            if isinstance(message, dict):
                role = message.get("role")
                raw_content = message.get("content")
            else:
                role = getattr(message, "type", None)
                raw_content = getattr(message, "content", None)
                if raw_content is None:
                    model_dump = getattr(message, "model_dump", None)
                    if callable(model_dump):
                        dumped = model_dump()
                        role = dumped.get("type", role)
                        raw_content = dumped.get("content")
            role = {
                "human": "user",
                "ai": "assistant",
            }.get(role, role)
            content = str(raw_content or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            normalized.append({"role": role, "content": content})
        return normalized

    @staticmethod
    def _failure(message: str) -> dict[str, Any]:
        return {
            "active_agent": AgentName.GENERAL.value,
            "resume_target": None,
            "task_status": TaskStatus.FAILED.value,
            "pending_interrupt": None,
            "pending_user_message": None,
            "final_response": None,
            "error": message,
        }
