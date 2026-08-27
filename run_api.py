"""Launcher for the AFRICA RESQ backend.

Usage (from the project root):

    python run_api.py

The FastAPI server will start on http://127.0.0.1:8000 and the dashboard
lives at http://127.0.0.1:8000/map
"""

import os

import uvicorn


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")

    uvicorn.run(
        "src.api:app",
        host=host,
        port=port,
        reload=False
    )