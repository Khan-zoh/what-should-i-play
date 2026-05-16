from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, library
from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(library.router)
    return app


app = create_app()
