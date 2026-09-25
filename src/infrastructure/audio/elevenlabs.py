"""Server-side ElevenLabs speech client.

The API key is intentionally retained here, never in the Angular application.
"""

from __future__ import annotations

import httpx


class SpeechSynthesisError(RuntimeError):
    """Raised when ElevenLabs cannot provide usable audio."""


class SpeechTranscriptionError(RuntimeError):
    """Raised when ElevenLabs cannot provide a usable transcript."""


class ElevenLabsSpeechService:
    _BASE_URL = "https://api.elevenlabs.io/v1/text-to-speech"
    _TRANSCRIPTION_URL = "https://api.elevenlabs.io/v1/speech-to-text"

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str,
        model_id: str,
        max_characters: int,
        timeout_seconds: float,
    ) -> None:
        if not api_key.strip() or not voice_id.strip():
            raise ValueError("ElevenLabs API key and voice ID are required.")
        if max_characters < 1:
            raise ValueError("ElevenLabs maximum text length must be positive.")
        self._api_key = api_key
        self._voice_id = voice_id
        self._model_id = model_id
        self._max_characters = max_characters
        self._timeout_seconds = timeout_seconds

    async def synthesize(self, text: str) -> bytes:
        normalized = text.strip()
        if not normalized:
            raise SpeechSynthesisError("Speech text cannot be blank.")
        if len(normalized) > self._max_characters:
            raise SpeechSynthesisError("Speech text exceeds the configured limit.")

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    f"{self._BASE_URL}/{self._voice_id}/stream",
                    params={"output_format": "mp3_44100_128"},
                    headers={
                        "xi-api-key": self._api_key,
                        "accept": "audio/mpeg",
                    },
                    json={"text": normalized, "model_id": self._model_id},
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise SpeechSynthesisError("ElevenLabs speech synthesis failed.") from error

        if not response.content:
            raise SpeechSynthesisError("ElevenLabs returned empty audio.")
        return response.content

    async def transcribe(
        self,
        *,
        audio: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        if not audio:
            raise SpeechTranscriptionError("Audio cannot be blank.")

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    self._TRANSCRIPTION_URL,
                    headers={"xi-api-key": self._api_key},
                    data={"model_id": "scribe_v2"},
                    files={
                        "file": (
                            filename or "question.webm",
                            audio,
                            content_type or "audio/webm",
                        )
                    },
                )
                response.raise_for_status()
                transcript = response.json().get("text", "").strip()
        except (httpx.HTTPError, ValueError) as error:
            raise SpeechTranscriptionError("ElevenLabs speech transcription failed.") from error

        if not transcript:
            raise SpeechTranscriptionError("ElevenLabs returned an empty transcript.")
        return transcript
