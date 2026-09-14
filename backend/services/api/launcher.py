import os

import uvicorn

from .config import PROJECT_DIR, boolean_environment, required_environment


def main() -> None:
    required_environment("DATABASE_URL")

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    workers = int(os.getenv("API_WORKERS", "1"))
    reload_enabled = boolean_environment("API_RELOAD")

    if port < 1 or port > 65535:
        raise RuntimeError("API_PORT must be between 1 and 65535")
    if workers < 1:
        raise RuntimeError("API_WORKERS must be at least 1")
    if reload_enabled and workers != 1:
        raise RuntimeError("API_RELOAD=true requires API_WORKERS=1")

    uvicorn.run(
        "backend.services.api.main:app",
        app_dir=str(PROJECT_DIR),
        host=host,
        port=port,
        workers=workers,
        reload=reload_enabled,
    )


if __name__ == "__main__":
    main()
