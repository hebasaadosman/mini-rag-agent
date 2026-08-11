from agents.tools import SendEmailTool
from helpers.config import Settings

from .smtp_gateway import SMTPEmailGateway, SMTPEmailSettings


def create_send_email_tool(settings: Settings) -> SendEmailTool | None:
    """Build the real delivery tool only when outbound email is enabled."""
    if not settings.SMTP_ENABLED:
        return None

    gateway_settings = SMTPEmailSettings(
        host=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USERNAME,
        password=settings.SMTP_PASSWORD,
        from_address=settings.SMTP_FROM_ADDRESS,
        security=settings.SMTP_SECURITY,
        timeout_seconds=settings.SMTP_TIMEOUT_SECONDS,
    )
    return SendEmailTool(SMTPEmailGateway(gateway_settings))
