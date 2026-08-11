import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr
from enum import Enum
from typing import Any


class SMTPSecurity(str, Enum):
    STARTTLS = "starttls"
    SSL = "ssl"
    NONE = "none"


@dataclass(frozen=True)
class SMTPEmailSettings:
    host: str
    port: int
    from_address: str
    security: SMTPSecurity = SMTPSecurity.STARTTLS
    username: str | None = None
    password: str | None = None
    timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        host = str(self.host or "").strip()
        from_address = str(self.from_address or "").strip()
        username = self._normalize_optional(self.username)
        password = self._normalize_optional(self.password)

        if not host or any(character in host for character in "\r\n"):
            raise ValueError("SMTP_HOST is required and must be valid.")
        if not 1 <= int(self.port) <= 65535:
            raise ValueError("SMTP_PORT must be between 1 and 65535.")
        if not self._is_plain_email_address(from_address):
            raise ValueError("SMTP_FROM_ADDRESS must be a plain email address.")
        if (username is None) != (password is None):
            raise ValueError(
                "SMTP_USERNAME and SMTP_PASSWORD must be configured together."
            )
        if float(self.timeout_seconds) <= 0:
            raise ValueError("SMTP_TIMEOUT_SECONDS must be greater than zero.")

        raw_security = (
            self.security.value
            if isinstance(self.security, SMTPSecurity)
            else str(self.security).lower()
        )
        try:
            security = SMTPSecurity(raw_security)
        except ValueError as exc:
            raise ValueError(
                "SMTP_SECURITY must be starttls, ssl, or none."
            ) from exc
        if security is SMTPSecurity.NONE and username is not None:
            raise ValueError(
                "SMTP credentials require starttls or ssl security."
            )

        object.__setattr__(self, "host", host)
        object.__setattr__(self, "port", int(self.port))
        object.__setattr__(self, "from_address", from_address)
        object.__setattr__(self, "username", username)
        object.__setattr__(self, "password", password)
        object.__setattr__(self, "timeout_seconds", float(self.timeout_seconds))
        object.__setattr__(self, "security", security)

    @staticmethod
    def _normalize_optional(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @staticmethod
    def _is_plain_email_address(value: str) -> bool:
        if not value or any(character in value for character in "\r\n"):
            return False
        display_name, parsed = parseaddr(value)
        local_part, separator, domain = parsed.rpartition("@")
        return bool(
            not display_name
            and parsed == value
            and separator
            and local_part
            and "." in domain
            and not domain.startswith(".")
            and not domain.endswith(".")
        )


class SMTPEmailGateway:
    """Deliver approved messages through SMTP outside the agent layer."""

    def __init__(self, settings: SMTPEmailSettings) -> None:
        if not isinstance(settings, SMTPEmailSettings):
            raise TypeError("settings must be SMTPEmailSettings.")
        self._settings = settings

    async def send_email(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._send_sync,
            recipient=recipient,
            subject=subject,
            body=body,
            idempotency_key=idempotency_key,
        )

    def _send_sync(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        message = EmailMessage()
        message["From"] = self._settings.from_address
        message["To"] = recipient
        message["Subject"] = subject
        message["Message-ID"] = make_msgid(
            idstring=idempotency_key,
            domain=self._settings.from_address.rsplit("@", 1)[1],
        )
        message.set_content(body)

        if self._settings.security is SMTPSecurity.SSL:
            client = smtplib.SMTP_SSL(
                self._settings.host,
                self._settings.port,
                timeout=self._settings.timeout_seconds,
                context=ssl.create_default_context(),
            )
        else:
            client = smtplib.SMTP(
                self._settings.host,
                self._settings.port,
                timeout=self._settings.timeout_seconds,
            )

        with client as smtp_client:
            smtp_client.ehlo()
            if self._settings.security is SMTPSecurity.STARTTLS:
                smtp_client.starttls(context=ssl.create_default_context())
                smtp_client.ehlo()
            if self._settings.username is not None:
                smtp_client.login(
                    self._settings.username,
                    self._settings.password,
                )
            refused = smtp_client.send_message(message)

        if refused:
            raise RuntimeError("The SMTP server refused one or more recipients.")

        return {
            "message_id": str(message["Message-ID"]),
            "accepted": True,
        }
