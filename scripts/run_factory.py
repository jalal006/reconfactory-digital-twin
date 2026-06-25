"""Run the ReConFactory FastAPI dashboard."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    parser = argparse.ArgumentParser(description="Run ReConFactory Digital Twin")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    public_url = os.environ.get("RECONFACTORY_PUBLIC_URL")
    if not public_url:
        browser_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
        public_url = f"http://{browser_host}:{args.port}"
    print(f"Open this in your browser: {public_url}", flush=True)
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
