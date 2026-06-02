"""`python -m agent` entry — starts the FastAPI control-plane server (P6 §1b)."""

import sys


def main() -> int:
    import uvicorn

    uvicorn.run("agent.server:app", host="127.0.0.1", port=8767, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
