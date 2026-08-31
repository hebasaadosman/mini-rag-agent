"""Trusted request identity after a token has been verified."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CurrentPrincipal:
    """Identity claims that later authorization policies can evaluate."""

    subject: str
    roles: tuple[str, ...] = ()
    kind: str = "user"
    demo_project_id: int | None = None

    @property
    def is_demo(self) -> bool:
        return self.kind == "demo"
