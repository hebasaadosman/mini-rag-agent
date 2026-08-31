import unittest

from authentication.demo_limits import DemoAgentRateLimiter, DemoRateLimitExceeded
from stores.llm.LLMProviderFactory import _UnavailableEmailAgent


class _Redis:
    def __init__(self): self.values, self.ttls = {}, {}
    async def incr(self, key):
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]
    async def expire(self, key, value): self.ttls[key] = value


class DemoRateLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_demo_limit_is_per_principal_and_fails_closed(self):
        redis = _Redis()
        limiter = DemoAgentRateLimiter(redis, limit=2)
        await limiter.require_capacity("demo-a")
        await limiter.require_capacity("demo-a")
        with self.assertRaises(DemoRateLimitExceeded):
            await limiter.require_capacity("demo-a")
        await limiter.require_capacity("demo-b")
        self.assertTrue(redis.ttls)

    async def test_demo_runtime_email_specialist_fails_closed_without_delivery_tool(self):
        result = await _UnavailableEmailAgent()({})
        self.assertFalse(result["final_response"])
        self.assertEqual(result["error"], "Outbound email is not configured.")


if __name__ == "__main__":
    unittest.main()
