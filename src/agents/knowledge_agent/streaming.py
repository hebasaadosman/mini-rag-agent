import asyncio
import json
import re
from collections.abc import AsyncIterator, Iterable
from contextlib import suppress
from typing import Any


class AnswerDeltaParser:
    """Extract decoded characters from a streamed JSON ``answer`` value."""

    _answer_prefix = re.compile(r'"answer"\s*:\s*"')

    def __init__(self) -> None:
        self._prefix_buffer = ""
        self._answer_started = False
        self._answer_finished = False
        self._escaped = False
        self._unicode_digits: str | None = None
        self._high_surrogate: int | None = None

    def feed(self, fragment: str) -> list[str]:
        if not fragment or self._answer_finished:
            return []

        if not self._answer_started:
            self._prefix_buffer += fragment
            match = self._answer_prefix.search(self._prefix_buffer)
            if match is None:
                # The prefix is tiny. Retaining a bounded suffix prevents a
                # malformed model response from growing this buffer forever.
                self._prefix_buffer = self._prefix_buffer[-256:]
                return []

            self._answer_started = True
            fragment = self._prefix_buffer[match.end():]
            self._prefix_buffer = ""

        return list(self._decode(fragment))

    def _decode(self, fragment: str) -> Iterable[str]:
        index = 0
        while index < len(fragment) and not self._answer_finished:
            character = fragment[index]
            index += 1

            if self._unicode_digits is not None:
                self._unicode_digits += character
                if len(self._unicode_digits) < 4:
                    continue

                try:
                    codepoint = int(self._unicode_digits, 16)
                except ValueError:
                    yield "\\u" + self._unicode_digits
                    self._unicode_digits = None
                    self._escaped = False
                    continue

                self._unicode_digits = None
                self._escaped = False

                if 0xD800 <= codepoint <= 0xDBFF:
                    self._high_surrogate = codepoint
                    continue

                if (
                    self._high_surrogate is not None
                    and 0xDC00 <= codepoint <= 0xDFFF
                ):
                    combined = (
                        0x10000
                        + ((self._high_surrogate - 0xD800) << 10)
                        + (codepoint - 0xDC00)
                    )
                    self._high_surrogate = None
                    yield chr(combined)
                    continue

                if self._high_surrogate is not None:
                    yield chr(self._high_surrogate)
                    self._high_surrogate = None

                yield chr(codepoint)
                continue

            if self._escaped:
                if character == "u":
                    self._unicode_digits = ""
                    continue

                escape_mapping = {
                    '"': '"',
                    "\\": "\\",
                    "/": "/",
                    "b": "\b",
                    "f": "\f",
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                }
                yield escape_mapping.get(character, character)
                self._escaped = False
                continue

            if character == "\\":
                self._escaped = True
                continue

            if character == '"':
                self._answer_finished = True
                continue

            yield character


def encode_sse(*, event: str, data: dict[str, Any]) -> str:
    """Serialize one named Server-Sent Event."""

    payload = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return f"event: {event}\ndata: {payload}\n\n"


async def with_heartbeat(
    events: AsyncIterator[dict[str, Any]],
    *,
    interval_seconds: float = 15.0,
) -> AsyncIterator[dict[str, Any]]:
    """Yield heartbeat events while waiting for the next agent event."""

    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than zero.")

    iterator = events.__aiter__()
    next_event = asyncio.create_task(anext(iterator))
    try:
        while True:
            done, _ = await asyncio.wait(
                {next_event},
                timeout=interval_seconds,
            )
            if not done:
                yield {"event": "heartbeat", "data": {}}
                continue

            try:
                event = next_event.result()
            except StopAsyncIteration:
                break

            yield event
            next_event = asyncio.create_task(anext(iterator))
    finally:
        if not next_event.done():
            next_event.cancel()
            with suppress(asyncio.CancelledError):
                await next_event

        close = getattr(iterator, "aclose", None)
        if callable(close):
            await close()
