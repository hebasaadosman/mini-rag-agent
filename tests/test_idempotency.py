import unittest

from utils.idempotency import generate_idempotency_key


class IdempotencyKeyTests(unittest.TestCase):
    def test_key_is_stable_for_equivalent_values(self):
        first = generate_idempotency_key(
            operation="PROCESS_ASSET",
            project_id=1,
            asset_id=2,
        )
        second = generate_idempotency_key(
            operation="PROCESS_ASSET",
            asset_id=2,
            project_id=1,
        )

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_key_changes_when_input_changes(self):
        first = generate_idempotency_key(
            operation="PROCESS_ASSET",
            project_id=1,
            asset_id=2,
        )
        second = generate_idempotency_key(
            operation="PROCESS_ASSET",
            project_id=1,
            asset_id=3,
        )

        self.assertNotEqual(first, second)
