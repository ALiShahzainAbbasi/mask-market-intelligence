"""Application composition root. Feature behavior belongs in its owning module."""

import logging

from fastapi import FastAPI

from mask_api.config import Settings, get_settings
from mask_api.modules.health.router import router as health_router
from mask_api.modules.smoke.router import create_smoke_router
from mask_api.transport.errors import install_error_handlers
from mask_api.transport.middleware import install_http_middleware


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level, format="%(message)s")
    app = FastAPI(
        title="MASK Infrastructure API",
        version="0.1.0",
        docs_url="/docs" if settings.environment in {"development", "test"} else None,
        redoc_url=None,
    )
    install_error_handlers(app)
    install_http_middleware(app)
    app.include_router(health_router)
    if settings.enable_dev_routes:
        app.include_router(create_smoke_router(settings))
    return app
