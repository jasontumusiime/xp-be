from fastapi import APIRouter

from app.api.routes import (
    alerts, analytics, audit, categories, checkin, comms, devices,
    geographical, gps, items, login, mock_pdm, notifications, pdm,
    pdm_sync, private, register, reports, tasks, users, utils, websocket,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(items.router)
api_router.include_router(geographical.router)
api_router.include_router(categories.router)
api_router.include_router(reports.router)
api_router.include_router(tasks.router)
api_router.include_router(gps.router)
api_router.include_router(devices.router)
api_router.include_router(analytics.router)
api_router.include_router(audit.router)
api_router.include_router(pdm.router)
api_router.include_router(checkin.router)
api_router.include_router(comms.router)
api_router.include_router(notifications.router)
api_router.include_router(websocket.router)
api_router.include_router(alerts.router)
api_router.include_router(register.router)
api_router.include_router(mock_pdm.router)
api_router.include_router(pdm_sync.router)

if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
