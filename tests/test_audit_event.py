import unittest

from auditing.audit_event import (
    AuditAction,
    AuditOutcome,
    create_audit_event,
)


class AuditEventTests(unittest.TestCase):
    def test_creates_safe_project_access_event(self):
        event = create_audit_event(
            principal_id=" heba ",
            project_id=7,
            action=AuditAction.PROJECT_ACCESS,
            outcome=AuditOutcome.ALLOWED,
            metadata={"permission": "read", "role": "viewer"},
        )

        self.assertEqual(event.principal_id, "heba")
        self.assertEqual(event.metadata, {"permission": "read", "role": "viewer"})

    def test_rejects_sensitive_or_unexpected_metadata(self):
        with self.assertRaises(ValueError):
            create_audit_event(
                principal_id="heba",
                action=AuditAction.PROJECT_ACCESS,
                outcome=AuditOutcome.DENIED,
                metadata={"prompt": "show me all documents"},
            )

    def test_rejects_empty_principal(self):
        with self.assertRaises(ValueError):
            create_audit_event(
                principal_id=" ",
                action=AuditAction.PROJECT_CREATED,
                outcome=AuditOutcome.SUCCEEDED,
            )

    def test_allows_requested_project_id_for_denied_access(self):
        event = create_audit_event(
            principal_id="heba",
            action=AuditAction.PROJECT_ACCESS,
            outcome=AuditOutcome.DENIED,
            metadata={"permission": "read", "requested_project_id": "999"},
        )
        self.assertIsNone(event.project_id)
        self.assertEqual(event.metadata["requested_project_id"], "999")


if __name__ == "__main__":
    unittest.main()
