"""Vercel entrypoint for the FastAPI application."""

from backend.app.main import app

__all__ = ["app"]
