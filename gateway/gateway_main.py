"""
Legacy entry that exposes `app` for uvicorn and imports the factory.
"""
from .app import create_app
app = create_app()
