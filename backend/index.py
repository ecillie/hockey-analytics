"""Vercel's explicit FastAPI entry point."""

from app.main import create_runtime_app

app = create_runtime_app()

__all__ = ("app",)
