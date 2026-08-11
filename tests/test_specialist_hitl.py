import unittest

from agents.multi_agent import (
    AgentName,
    SpecialistResumeError,
    TaskStatus,
    build_initial_multi_agent_state,
    build_specialist_clarification_update,
    get_specialist_resume_message,
)


class SpecialistHITLTests(unittest.TestCase):
    def test_builds_a_waiting_checkpoint(self):
        state = build_initial_multi_agent_state("What is the weather?")

        update = build_specialist_clarification_update(
            state,
            from_agent=AgentName.UTILITY,
            input_message="What is the weather?",
            question="Which city?",
            options=["Riyadh", "Jeddah"],
            interrupt_id_factory=lambda: "utility-interrupt-1",
        )

        self.assertEqual(update["task_status"], TaskStatus.WAITING_FOR_USER)
        self.assertEqual(update["resume_target"], AgentName.UTILITY)
        self.assertEqual(
            update["pending_interrupt"],
            {
                "type": "clarification",
                "question": "Which city?",
                "options": ["Riyadh", "Jeddah"],
                "interrupt_id": "utility-interrupt-1",
            },
        )
        self.assertEqual(
            update["final_response"]["status"],
            "clarification_required",
        )

    def test_repeated_identical_clarification_keeps_interrupt_id(self):
        state = build_initial_multi_agent_state("Weather?")
        first = build_specialist_clarification_update(
            state,
            from_agent=AgentName.UTILITY,
            input_message="Weather?",
            question="Which city?",
            interrupt_id_factory=lambda: "stable-id",
        )
        state.update(first)
        state["pending_user_message"] = "I am not sure"

        second = build_specialist_clarification_update(
            state,
            from_agent=AgentName.UTILITY,
            input_message="I am not sure",
            question="Which city?",
            interrupt_id_factory=lambda: "must-not-replace",
        )

        self.assertEqual(
            second["pending_interrupt"]["interrupt_id"],
            "stable-id",
        )

    def test_gets_only_the_saved_specialists_resume_message(self):
        state = build_initial_multi_agent_state("Weather?")
        state.update(
            build_specialist_clarification_update(
                state,
                from_agent=AgentName.UTILITY,
                input_message="Weather?",
                question="Which city?",
                interrupt_id_factory=lambda: "id-1",
            )
        )
        state["pending_user_message"] = "  Riyadh  "

        response = get_specialist_resume_message(
            state,
            target_agent=AgentName.UTILITY,
        )

        self.assertEqual(response, "Riyadh")
        with self.assertRaises(SpecialistResumeError):
            get_specialist_resume_message(
                state,
                target_agent=AgentName.GENERAL,
            )

    def test_rejects_invalid_clarification_data(self):
        invalid_arguments = [
            {"input_message": " ", "question": "Which city?"},
            {"input_message": "Weather?", "question": " "},
            {
                "input_message": "Weather?",
                "question": "Which city?",
                "options": [""],
            },
        ]

        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    build_specialist_clarification_update(
                        build_initial_multi_agent_state("Weather?"),
                        from_agent=AgentName.UTILITY,
                        interrupt_id_factory=lambda: "id-1",
                        **arguments,
                    )

    def test_two_message_limit_retains_only_the_new_turn(self):
        state = build_initial_multi_agent_state("New question")
        state["messages"] = [
            {"role": "user", "content": "Old question"},
            {"role": "assistant", "content": "Old answer"},
        ]

        update = build_specialist_clarification_update(
            state,
            from_agent=AgentName.UTILITY,
            input_message="New question",
            question="Which city?",
            max_memory_messages=2,
            interrupt_id_factory=lambda: "id-1",
        )

        self.assertEqual(
            update["messages"],
            [
                {"role": "user", "content": "New question"},
                {"role": "assistant", "content": "Which city?"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
