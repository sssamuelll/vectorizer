"""python -m server → uvicorn en loopback (Spec B1)."""
import uvicorn

uvicorn.run("server.app:app", host="127.0.0.1", port=8000)
