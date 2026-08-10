import asyncio
import unittest

from utils.async_keyed_lock import (
    AsyncKeyedLock,
    PostgresAdvisoryKeyedLock,
)


class AsyncKeyedLockTests(unittest.IsolatedAsyncioTestCase):
    def test_postgres_lock_id_is_stable_and_keyed(self):
        first = PostgresAdvisoryKeyedLock.lock_id("1:thread-a")
        repeated = PostgresAdvisoryKeyedLock.lock_id("1:thread-a")
        different = PostgresAdvisoryKeyedLock.lock_id("1:thread-b")

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, different)
        self.assertGreaterEqual(first, -(2**63))
        self.assertLess(first, 2**63)

    async def test_same_key_is_serialized_and_cleaned_up(self):
        manager = AsyncKeyedLock()
        active = 0
        maximum_active = 0

        async def worker():
            nonlocal active, maximum_active
            async with manager.acquire("project:thread"):
                active += 1
                maximum_active = max(maximum_active, active)
                await asyncio.sleep(0.01)
                active -= 1

        await asyncio.gather(*(worker() for _ in range(4)))

        self.assertEqual(maximum_active, 1)
        self.assertEqual(manager._entries, {})

    async def test_different_keys_can_run_in_parallel(self):
        manager = AsyncKeyedLock()
        both_entered = asyncio.Event()
        active = 0

        async def worker(key: str):
            nonlocal active
            async with manager.acquire(key):
                active += 1
                if active == 2:
                    both_entered.set()
                await asyncio.wait_for(both_entered.wait(), timeout=1)
                active -= 1

        await asyncio.gather(worker("thread-a"), worker("thread-b"))

        self.assertEqual(manager._entries, {})


if __name__ == "__main__":
    unittest.main()
