import asyncio
from datetime import timedelta
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from contextlib import asynccontextmanager

from app.api.main import api_router
from app.core.config import settings
from app.core.db import engine

# Devices are considered offline after 2 missed pings (mobile pings every 20 s)
OFFLINE_AFTER_SECONDS = 60


async def _sweep_offline_devices() -> None:
    """Background task: mark devices OFFLINE if last_seen is stale."""
    from sqlmodel import Session, select
    from app.models import Device, DeviceStatus, get_datetime_utc

    while True:
        await asyncio.sleep(30)
        try:
            cutoff = get_datetime_utc() - timedelta(seconds=OFFLINE_AFTER_SECONDS)
            with Session(engine) as session:
                stale = session.exec(
                    select(Device).where(
                        Device.status == DeviceStatus.ONLINE,
                        Device.last_seen < cutoff,
                    )
                ).all()
                for device in stale:
                    device.status = DeviceStatus.OFFLINE
                    session.add(device)
                if stale:
                    session.commit()
        except Exception:
            pass  # never crash the sweep loop


async def _run_alert_engine_job() -> None:
    """Background task: run alert engine every 5 minutes."""
    from sqlmodel import Session
    from app.alert_engine import run_alert_engine

    while True:
        await asyncio.sleep(300)
        try:
            with Session(engine) as session:
                await run_alert_engine(session)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    sweep_task = asyncio.create_task(_sweep_offline_devices())
    engine_task = asyncio.create_task(_run_alert_engine_job())
    yield
    sweep_task.cancel()
    engine_task.cancel()



def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)

# Serve uploaded media files
media_dir = Path(settings.MEDIA_PATH)
media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")
