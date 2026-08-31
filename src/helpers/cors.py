"""Explicit credentialed CORS configuration for browser BFF clients."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings


def configure_browser_cors(app: FastAPI, settings: Settings) -> None:
    """Enable credentialed CORS only for the configured trusted SPA origins."""
    origins = tuple(
        origin.strip().rstrip("/")
        for origin in settings.CORS_ALLOWED_ORIGINS
        if origin.strip()
    )
    if not origins:
        return
    if "*" in origins:
        raise RuntimeError("CORS_ALLOWED_ORIGINS cannot contain '*' when BFF credentials are enabled.")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-CSRF-Token"],
    )
