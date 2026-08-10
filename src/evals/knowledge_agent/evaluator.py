import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class EvaluationCheck:
    name: str
    passed: bool
    expected: Any = None
    actual: Any = None
    message: str | None = None


@dataclass
class EvaluationResult:
    case_id: str
    level: int
    title: str
    passed: bool
    checks: list[EvaluationCheck]
    answer: str
    tools: list[str]
    iterations: int
    used_chunk_ids: list[int]
    error: str | None

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return asdict(self)


class KnowledgeAgentEvaluator:
    """
    Deterministic evaluator for Knowledge Agent runs.

    It evaluates:
    - agent success
    - tool selection and ordering
    - unexpected tool calls
    - duplicate tool calls
    - iteration budget
    - answer content
    - numbered output structure
    - question count
    - chunk grounding
    """

    def load_cases(
        self,
        path: str | Path,
    ) -> list[dict[str, Any]]:
        cases_path = Path(path)

        with cases_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            cases = json.load(file)

        if not isinstance(cases, list):
            raise ValueError(
                "Evaluation cases must be "
                "a JSON list."
            )

        return cases

    def evaluate(
        self,
        *,
        case: dict[str, Any],
        agent_result: dict[str, Any],
    ) -> EvaluationResult:
        checks: list[EvaluationCheck] = []

        answer = str(
            agent_result.get("answer")
            or ""
        ).strip()

        iterations = int(
            agent_result.get("iterations")
            or 0
        )

        used_chunk_ids = (
            self._normalize_chunk_ids(
                agent_result.get(
                    "used_chunk_ids"
                )
                or []
            )
        )

        error = agent_result.get("error")

        tool_history = (
            agent_result.get("tool_history")
            or []
        )

        tools = [
            str(item.get("tool_name"))
            for item in tool_history
            if item.get("tool_name")
        ]

        self._check_success(
            checks=checks,
            agent_result=agent_result,
        )

        self._check_tools(
            checks=checks,
            case=case,
            actual_tools=tools,
        )

        self._check_duplicate_calls(
            checks=checks,
            tool_history=tool_history,
        )

        self._check_iterations(
            checks=checks,
            case=case,
            iterations=iterations,
        )

        self._check_answer_content(
            checks=checks,
            case=case,
            answer=answer,
        )

        self._check_numbered_items(
            checks=checks,
            case=case,
            answer=answer,
        )

        self._check_question_marks(
            checks=checks,
            case=case,
            answer=answer,
        )

        self._check_chunk_grounding(
            checks=checks,
            case=case,
            used_chunk_ids=used_chunk_ids,
        )

        passed = all(
            check.passed
            for check in checks
        )

        return EvaluationResult(
            case_id=str(case["id"]),
            level=int(case.get("level", 0)),
            title=str(case.get("title", "")),
            passed=passed,
            checks=checks,
            answer=answer,
            tools=tools,
            iterations=iterations,
            used_chunk_ids=used_chunk_ids,
            error=(
                str(error)
                if error is not None
                else None
            ),
        )

    @staticmethod
    def _normalize_chunk_ids(
        chunk_ids: list[Any],
    ) -> list[int]:
        normalized: list[int] = []

        for chunk_id in chunk_ids:
            try:
                normalized_chunk_id = int(
                    chunk_id
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

            if normalized_chunk_id < 1:
                continue

            if normalized_chunk_id in normalized:
                continue

            normalized.append(
                normalized_chunk_id
            )

        return normalized

    @staticmethod
    def _check_success(
        *,
        checks: list[EvaluationCheck],
        agent_result: dict[str, Any],
    ) -> None:
        actual_success = bool(
            agent_result.get("success")
        )

        checks.append(
            EvaluationCheck(
                name="agent_success",
                passed=actual_success,
                expected=True,
                actual=actual_success,
                message=(
                    None
                    if actual_success
                    else str(
                        agent_result.get("error")
                        or "Agent run failed."
                    )
                ),
            )
        )

    @staticmethod
    def _check_tools(
        *,
        checks: list[EvaluationCheck],
        case: dict[str, Any],
        actual_tools: list[str],
    ) -> None:
        expected_tools = [
            str(tool)
            for tool in (
                case.get("expected_tools")
                or []
            )
        ]

        allow_extra_tools = bool(
            case.get(
                "allow_extra_tools",
                False,
            )
        )

        if allow_extra_tools:
            expected_position = 0

            for tool_name in actual_tools:
                if (
                    expected_position
                    < len(expected_tools)
                    and tool_name
                    == expected_tools[
                        expected_position
                    ]
                ):
                    expected_position += 1

            tools_passed = (
                expected_position
                == len(expected_tools)
            )

        else:
            tools_passed = (
                actual_tools == expected_tools
            )

        checks.append(
            EvaluationCheck(
                name="tool_path",
                passed=tools_passed,
                expected=expected_tools,
                actual=actual_tools,
                message=(
                    None
                    if tools_passed
                    else (
                        "The agent used an "
                        "unexpected tool path."
                    )
                ),
            )
        )

    @staticmethod
    def _check_duplicate_calls(
        *,
        checks: list[EvaluationCheck],
        tool_history: list[
            dict[str, Any]
        ],
    ) -> None:
        signatures: list[str] = []

        for item in tool_history:
            tool_name = str(
                item.get("tool_name")
                or ""
            )

            arguments = (
                item.get("arguments")
                or {}
            )

            arguments_json = json.dumps(
                arguments,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )

            signatures.append(
                f"{tool_name}:{arguments_json}"
            )

        counts = Counter(signatures)

        duplicates = {
            signature: count
            for signature, count
            in counts.items()
            if count > 1
        }

        checks.append(
            EvaluationCheck(
                name="no_duplicate_tool_calls",
                passed=not duplicates,
                expected={},
                actual=duplicates,
                message=(
                    None
                    if not duplicates
                    else (
                        "The agent repeated one or "
                        "more identical tool calls."
                    )
                ),
            )
        )

    @staticmethod
    def _check_iterations(
        *,
        checks: list[EvaluationCheck],
        case: dict[str, Any],
        iterations: int,
    ) -> None:
        expected_max = int(
            case.get(
                "expected_iterations_max",
                5,
            )
        )

        passed = (
            0 < iterations <= expected_max
        )

        checks.append(
            EvaluationCheck(
                name="iteration_budget",
                passed=passed,
                expected=f"1..{expected_max}",
                actual=iterations,
                message=(
                    None
                    if passed
                    else (
                        "The agent exceeded the "
                        "expected iteration budget."
                    )
                ),
            )
        )

    @staticmethod
    def _check_answer_content(
        *,
        checks: list[EvaluationCheck],
        case: dict[str, Any],
        answer: str,
    ) -> None:
        normalized_answer = (
            answer.casefold()
        )

        expected_all = [
            str(value).casefold()
            for value in (
                case.get(
                    "expected_answer_contains_all"
                )
                or []
            )
        ]

        expected_any = [
            str(value).casefold()
            for value in (
                case.get(
                    "expected_answer_contains_any"
                )
                or []
            )
        ]

        missing_all = [
            value
            for value in expected_all
            if value not in normalized_answer
        ]

        all_passed = not missing_all

        checks.append(
            EvaluationCheck(
                name="answer_contains_all",
                passed=all_passed,
                expected=expected_all,
                actual=(
                    []
                    if all_passed
                    else missing_all
                ),
                message=(
                    None
                    if all_passed
                    else (
                        "The answer is missing "
                        "required content."
                    )
                ),
            )
        )

        any_passed = (
            not expected_any
            or any(
                value in normalized_answer
                for value in expected_any
            )
        )

        checks.append(
            EvaluationCheck(
                name="answer_contains_any",
                passed=any_passed,
                expected=expected_any,
                actual=answer[:500],
                message=(
                    None
                    if any_passed
                    else (
                        "The answer did not contain "
                        "any accepted expected value."
                    )
                ),
            )
        )

    @staticmethod
    def _check_numbered_items(
        *,
        checks: list[EvaluationCheck],
        case: dict[str, Any],
        answer: str,
    ) -> None:
        expected_count = case.get(
            "expected_numbered_items"
        )

        if expected_count is None:
            return

        expected_count = int(
            expected_count
        )

        numbered_items = re.findall(
            r"(?m)^\s*\d+[\.\-\)]\s+",
            answer,
        )

        actual_count = len(
            numbered_items
        )

        passed = (
            actual_count >= expected_count
        )

        checks.append(
            EvaluationCheck(
                name="numbered_items",
                passed=passed,
                expected=expected_count,
                actual=actual_count,
                message=(
                    None
                    if passed
                    else (
                        "The answer did not contain "
                        "the expected number of "
                        "numbered items."
                    )
                ),
            )
        )

    @staticmethod
    def _check_question_marks(
        *,
        checks: list[EvaluationCheck],
        case: dict[str, Any],
        answer: str,
    ) -> None:
        expected_count = case.get(
            "expected_question_marks"
        )

        if expected_count is None:
            return

        expected_count = int(
            expected_count
        )

        actual_count = (
            answer.count("؟")
            + answer.count("?")
        )

        passed = (
            actual_count >= expected_count
        )

        checks.append(
            EvaluationCheck(
                name="question_count",
                passed=passed,
                expected=expected_count,
                actual=actual_count,
                message=(
                    None
                    if passed
                    else (
                        "The answer did not contain "
                        "the expected number of "
                        "questions."
                    )
                ),
            )
        )

    @staticmethod
    def _check_chunk_grounding(
        *,
        checks: list[EvaluationCheck],
        case: dict[str, Any],
        used_chunk_ids: list[int],
    ) -> None:
        require_used_chunks = bool(
            case.get(
                "require_used_chunks",
                False,
            )
        )

        passed = (
            bool(used_chunk_ids)
            if require_used_chunks
            else True
        )

        checks.append(
            EvaluationCheck(
                name="chunk_grounding",
                passed=passed,
                expected=(
                    "one or more chunk IDs"
                    if require_used_chunks
                    else "not required"
                ),
                actual=used_chunk_ids,
                message=(
                    None
                    if passed
                    else (
                        "The answer required "
                        "document grounding but "
                        "returned no used_chunk_ids."
                    )
                ),
            )
        )