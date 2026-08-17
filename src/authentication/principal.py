"""Trusted request identity after a token has been verified."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CurrentPrincipal:
    """Identity claims that later authorization policies can evaluate."""

    subject: str
    roles: tuple[str, ...] = ()
