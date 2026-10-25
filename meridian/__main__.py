"""`python -m meridian` runs the server (reads PORT and HOST from the environment)."""

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "meridian.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        log_level="info",
        # Open dashboard streams would otherwise hold shutdown forever.
        timeout_graceful_shutdown=3,
    )


if __name__ == "__main__":
    main()
