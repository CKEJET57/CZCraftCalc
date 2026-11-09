"""Точка входа для uvicorn: `python server.py`."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "server.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )