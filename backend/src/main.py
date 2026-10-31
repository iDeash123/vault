from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from core.clock import ClockPort, SystemClock
from core.config import get_settings
from core.exceptions import DomainError
from domains.auth.dependencies import get_clock
from domains.auth.router import router as auth_router
from domains.bidding.router import router as bidding_router
from domains.bidding.ws_router import router as ws_router
from domains.lots.router import router as lots_router
from domains.wallet.router import router as wallet_router
from shared.db.session import dispose_engine, get_engine

clock = SystemClock()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="OBSOLETE Auction Engine API",
        version="1.0.0",
        lifespan=lifespan,
    )

    def resolve_clock() -> ClockPort:
        override = app.dependency_overrides.get(get_clock)
        if override is not None:
            resolved: ClockPort = override()
            return resolved
        return clock

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_problem_details(server_time=resolve_clock().now()),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": {"errors": jsonable_encoder(exc.errors())},
                "server_time": resolve_clock().now().isoformat(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected server error occurred",
                "details": {},
                "server_time": resolve_clock().now().isoformat(),
            },
        )

    @app.get("/api/v1/health")
    async def healthcheck() -> JSONResponse:
        now_iso = resolve_clock().now().isoformat()
        try:
            engine = get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return JSONResponse(
                status_code=200,
                content={
                    "status": "ok",
                    "database": "connected",
                    "server_time": now_iso,
                    "version": "1.0.0",
                },
            )
        except Exception:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "database": "disconnected",
                    "server_time": now_iso,
                    "version": "1.0.0",
                },
            )

    app.include_router(auth_router)
    app.include_router(wallet_router)
    app.include_router(lots_router)
    app.include_router(bidding_router)
    app.include_router(ws_router)

    return app


app = create_app()
