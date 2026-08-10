import unittest
from types import SimpleNamespace

from stores.llm.providers.CohereProvider import CohereProvider
from stores.llm.providers.OpenAIProvider import OpenAIProvider


def _namespace(**kwargs):
    return SimpleNamespace(**kwargs)


class _AsyncChunks:
    def __init__(self, chunks):
        self._iterator = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeOpenAICompletions:
    def __init__(self, chunks):
        self._chunks = chunks

    async def create(self, **kwargs):
        if kwargs.get("stream") is not True:
            raise AssertionError("OpenAI streaming must set stream=True.")
        return _AsyncChunks(self._chunks)


class _FakeCohereClient:
    def __init__(self, events):
        self._events = events

    def chat_stream(self, **kwargs):
        return iter(self._events)


class LLMProviderStreamingContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_accumulates_content_and_tool_arguments(self):
        chunks = [
            _namespace(
                choices=[
                    _namespace(
                        finish_reason=None,
                        delta=_namespace(
                            content="Hello ",
                            tool_calls=[],
                        ),
                    )
                ]
            ),
            _namespace(
                choices=[
                    _namespace(
                        finish_reason=None,
                        delta=_namespace(
                            content="world",
                            tool_calls=[
                                _namespace(
                                    index=0,
                                    id="call-1",
                                    type="function",
                                    function=_namespace(
                                        name="search_project_chunks",
                                        arguments='{"query":"pol',
                                    ),
                                )
                            ],
                        ),
                    )
                ]
            ),
            _namespace(
                choices=[
                    _namespace(
                        finish_reason="tool_calls",
                        delta=_namespace(
                            content=None,
                            tool_calls=[
                                _namespace(
                                    index=0,
                                    id=None,
                                    type=None,
                                    function=_namespace(
                                        name=None,
                                        arguments='icy"}',
                                    ),
                                )
                            ],
                        ),
                    )
                ]
            ),
        ]
        provider = OpenAIProvider(
            api_key="test-key",
            generation_model_id="test-model",
        )
        provider.async_client = _namespace(
            chat=_namespace(
                completions=_FakeOpenAICompletions(chunks)
            )
        )
        deltas = []

        result = await provider.generate_tool_response_stream(
            messages=[],
            tools=[],
            on_content_delta=deltas.append,
        )

        self.assertEqual(result["content"], "Hello world")
        self.assertEqual(deltas, ["Hello ", "world"])
        self.assertEqual(result["finish_reason"], "tool_calls")
        self.assertEqual(
            result["tool_calls"],
            [
                {
                    "id": "call-1",
                    "type": "function",
                    "name": "search_project_chunks",
                    "arguments": '{"query":"policy"}',
                }
            ],
        )

    async def test_cohere_matches_the_normalized_stream_contract(self):
        events = [
            _namespace(
                type="content-delta",
                delta=_namespace(
                    message=_namespace(
                        content=_namespace(text="Hello ")
                    )
                ),
            ),
            _namespace(
                type="content-delta",
                delta=_namespace(
                    message=_namespace(
                        content=_namespace(text="Cohere")
                    )
                ),
            ),
            _namespace(
                type="tool-call-start",
                index=0,
                delta=_namespace(
                    message=_namespace(
                        tool_calls=_namespace(
                            id="call-2",
                            type="function",
                            function=_namespace(
                                name="list_project_assets",
                                arguments="",
                            ),
                        )
                    )
                ),
            ),
            _namespace(
                type="tool-call-delta",
                index=0,
                delta=_namespace(
                    message=_namespace(
                        tool_calls=_namespace(
                            function=_namespace(arguments="{}")
                        )
                    )
                ),
            ),
            _namespace(
                type="message-end",
                delta=_namespace(finish_reason="TOOL_CALL"),
            ),
        ]
        provider = CohereProvider(
            api_key="test-key",
            generation_model_id="test-model",
        )
        provider.client = _FakeCohereClient(events)
        deltas = []

        result = await provider.generate_tool_response_stream(
            messages=[],
            tools=[],
            on_content_delta=deltas.append,
        )

        self.assertEqual(result["content"], "Hello Cohere")
        self.assertEqual(deltas, ["Hello ", "Cohere"])
        self.assertEqual(result["finish_reason"], "TOOL_CALL")
        self.assertEqual(
            result["tool_calls"],
            [
                {
                    "id": "call-2",
                    "type": "function",
                    "name": "list_project_assets",
                    "arguments": "{}",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
