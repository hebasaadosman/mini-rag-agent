import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from pprint import pprint
from typing import Any

from agents.knowledge_agent.prompts import (
    KNOWLEDGE_AGENT_SYSTEM_PROMPT,
)
from agents.knowledge_agent.service import (
    KnowledgeAgent,
)
from controllers.KnowledgeAgentController import (
    KnowledgeAgentController,
)
from evals.knowledge_agent.evaluator import (
    EvaluationResult,
    KnowledgeAgentEvaluator,
)
from main import (
    app,
    startup_db_client,
)
from models.ProjectModel import ProjectModel


PROJECT_ID = 1

CURRENT_DIRECTORY = Path(__file__).parent

CASES_PATH = (
    CURRENT_DIRECTORY
    / "cases.json"
)

REPORTS_DIRECTORY = (
    CURRENT_DIRECTORY
    / "reports"
)


async def run_case(
    *,
    case: dict[str, Any],
    controller: KnowledgeAgentController,
    evaluator: KnowledgeAgentEvaluator,
) -> EvaluationResult:
    """
    Run one case directly against the Agent.

    This bypasses the HTTP route so the evaluator can
    inspect internal tool_history.
    """

    registry = controller._build_tool_registry(
        project_id=PROJECT_ID,
    )

    agent = KnowledgeAgent(
        llm_provider=(
            controller.generation_client
        ),
        tool_registry=registry,
        max_iterations=5,
    )

    raw_result = await agent.run(
        user_message=str(case["message"]),
        system_prompt=(
            KNOWLEDGE_AGENT_SYSTEM_PROMPT
        ),
    )

    return evaluator.evaluate(
        case=case,
        agent_result=raw_result,
    )


def print_case_result(
    result: EvaluationResult,
) -> None:
    icon = "✅" if result.passed else "❌"

    print(
        "\n"
        + "=" * 72
    )

    print(
        f"{icon} "
        f"LEVEL {result.level} | "
        f"{result.case_id}"
    )

    print(
        result.title
    )

    print(
        "-" * 72
    )

    print(
        "Tools:",
        result.tools,
    )

    print(
        "Iterations:",
        result.iterations,
    )

    print(
        "Used chunk IDs:",
        result.used_chunk_ids,
    )

    print(
        "Answer preview:",
        result.answer[:300],
    )

    failed_checks = [
        check
        for check in result.checks
        if not check.passed
    ]

    if failed_checks:
        print("\nFailed checks:")

        for check in failed_checks:
            print(
                f"  ❌ {check.name}"
            )

            print(
                "     Expected:",
                check.expected,
            )

            print(
                "     Actual:",
                check.actual,
            )

            if check.message:
                print(
                    "     Reason:",
                    check.message,
                )


def build_summary(
    results: list[EvaluationResult],
) -> dict[str, Any]:
    total = len(results)

    passed = sum(
        1
        for result in results
        if result.passed
    )

    failed = total - passed

    total_iterations = sum(
        result.iterations
        for result in results
    )

    average_iterations = (
        round(
            total_iterations / total,
            2,
        )
        if total
        else 0
    )

    check_totals: dict[str, dict[str, int]] = {}

    for result in results:
        for check in result.checks:
            stats = check_totals.setdefault(
                check.name,
                {
                    "passed": 0,
                    "failed": 0,
                },
            )

            if check.passed:
                stats["passed"] += 1
            else:
                stats["failed"] += 1

    return {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": failed,
        "pass_rate": (
            round(
                passed / total * 100,
                2,
            )
            if total
            else 0
        ),
        "average_iterations": average_iterations,
        "checks": check_totals,
    }


def save_report(
    *,
    results: list[EvaluationResult],
    summary: dict[str, Any],
) -> Path:
    REPORTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    report_path = (
        REPORTS_DIRECTORY
        / f"knowledge_agent_eval_{timestamp}.json"
    )

    report = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "project_id": PROJECT_ID,
        "summary": summary,
        "results": [
            result.to_dict()
            for result in results
        ],
    }

    report_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return report_path


async def main() -> None:
    evaluator = KnowledgeAgentEvaluator()

    cases = evaluator.load_cases(
        CASES_PATH
    )

    await startup_db_client()

    try:
        project_model = (
            await ProjectModel.create_instance(
                db_client=app.db_client,
            )
        )

        controller = KnowledgeAgentController(
            generation_client=(
                app.generation_client
            ),
            tools_service=(
                app.knowledge_agent_tools_service
            ),
            project_model=project_model,
            checkpointer=app.checkpointer,
        )

        results: list[
            EvaluationResult
        ] = []

        for case in cases:
            print(
                "\nRunning:",
                case["id"],
            )

            try:
                result = await run_case(
                    case=case,
                    controller=controller,
                    evaluator=evaluator,
                )

            except Exception as exc:
                result = EvaluationResult(
                    case_id=str(case["id"]),
                    level=int(
                        case.get("level", 0)
                    ),
                    title=str(
                        case.get("title", "")
                    ),
                    passed=False,
                    checks=[],
                    answer="",
                    tools=[],
                    iterations=0,
                    used_chunk_ids=[],
                    error=str(exc),
                )

            results.append(
                result
            )

            print_case_result(
                result
            )

        summary = build_summary(
            results
        )

        print(
            "\n"
            + "=" * 72
        )

        print(
            "KNOWLEDGE AGENT EVALUATION SUMMARY"
        )

        print(
            "=" * 72
        )

        pprint(summary)

        report_path = save_report(
            results=results,
            summary=summary,
        )

        print(
            "\nReport saved to:"
        )

        print(
            report_path
        )

        if summary["failed_cases"]:
            raise SystemExit(1)

    finally:
        if getattr(
            app,
            "vectordb_client",
            None,
        ):
            await app.vectordb_client.disconnect()

        if getattr(
            app,
            "pg_engine",
            None,
        ):
            await app.pg_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())