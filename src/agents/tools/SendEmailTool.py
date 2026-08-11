import asyncio
import re
from email.utils import parseaddr
from hashlib import sha256
from typing import Any, Protocol

from .BaseTool import BaseTool


class EmailDeliveryGateway(Protocol):
    async def send_email(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        idempotency_key: str,
    ) -> dict[str, Any]: ...


class SendEmailTool(BaseTool):
    name = "send_email"
    description = (
        "Backend-only email delivery tool. It must be called only after "
        "the user approves an exact saved draft."
    )
    _IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{8,255}$")

    def __init__(self, gateway: EmailDeliveryGateway) -> None:
        if gateway is None or not callable(
            getattr(gateway, "send_email", None)
        ):
            raise TypeError("gateway must implement send_email.")
        self._gateway = gateway
        self._completed: dict[
            str,
            tuple[str, dict[str, Any]],
        ] = {}
        self._lock = asyncio.Lock()

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "recipient": {
                            "type": "string",
                            "description": "One approved recipient address.",
                        },
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                        "idempotency_key": {
                            "type": "string",
                            "description": (
                                "Backend approval ID; never supplied by LLM."
                            ),
                        },
                    },
                    "required": [
                        "recipient",
                        "subject",
                        "body",
                        "idempotency_key",
                    ],
                    "additionalProperties": False,
                },
            },
        }

    async def execute(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        normalized_recipient = self._validate_recipient(recipient)
        normalized_subject = self._validate_text(
            subject,
            field_name="subject",
            max_length=200,
            allow_newlines=False,
        )
        normalized_body = self._validate_text(
            body,
            field_name="body",
            max_length=100_000,
            allow_newlines=True,
        )

        normalized_key = str(idempotency_key or "").strip()
        if not self._IDEMPOTENCY_KEY.fullmatch(normalized_key):
            raise ValueError("The email idempotency key is invalid.")

        payload_fingerprint = sha256(
            (
                normalized_recipient
                + "\0"
                + normalized_subject
                + "\0"
                + normalized_body
            ).encode("utf-8")
        ).hexdigest()

        async with self._lock:
            cached = self._completed.get(normalized_key)
            if cached is not None:
                cached_fingerprint, cached_result = cached
                if cached_fingerprint != payload_fingerprint:
                    raise ValueError(
                        "The email approval ID was reused for a different draft."
                    )
                return {**cached_result, "replayed": True}

            result = await self._gateway.send_email(
                recipient=normalized_recipient,
                subject=normalized_subject,
                body=normalized_body,
                idempotency_key=normalized_key,
            )
            if not isinstance(result, dict):
                raise RuntimeError(
                    "The email delivery gateway returned an invalid result."
                )

            message_id = str(result.get("message_id") or "").strip()
            if (
                not message_id
                or len(message_id) > 500
                or any(character in message_id for character in "\r\n")
            ):
                raise RuntimeError(
                    "The email delivery gateway returned no message ID."
                )

            safe_result = {
                "message_id": message_id,
                "recipient": normalized_recipient,
                "accepted": True,
                "replayed": False,
            }
            self._completed[normalized_key] = (
                payload_fingerprint,
                safe_result,
            )
            return safe_result

    @staticmethod
    def _validate_recipient(value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("The approved email recipient is invalid.")
        normalized = value.strip()
        if (
            len(normalized) < 3
            or len(normalized) > 320
            or any(character in normalized for character in "\r\n")
        ):
            raise ValueError("The approved email recipient is invalid.")

        display_name, address = parseaddr(normalized)
        local_part, separator, domain = address.rpartition("@")
        if (
            display_name
            or address != normalized
            or separator != "@"
            or not local_part
            or "." not in domain
            or domain.startswith(".")
            or domain.endswith(".")
        ):
            raise ValueError("The approved email recipient is invalid.")
        return normalized

    @staticmethod
    def _validate_text(
        value: Any,
        *,
        field_name: str,
        max_length: int,
        allow_newlines: bool,
    ) -> str:
        if not isinstance(value, str):
            raise ValueError(
                f"The approved email {field_name} is invalid."
            )
        normalized = value.strip()
        if (
            not normalized
            or len(normalized) > max_length
            or (
                not allow_newlines
                and any(character in normalized for character in "\r\n")
            )
        ):
            raise ValueError(
                f"The approved email {field_name} is invalid."
            )
        return normalized
