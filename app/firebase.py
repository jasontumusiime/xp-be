"""
Firebase Admin SDK initialisation and FCM push notification helper.
Initialised lazily on first use — app starts normally if the service
account file is missing (e.g. local dev without push notifications).
"""
from __future__ import annotations

import logging
from typing import Sequence

logger = logging.getLogger(__name__)
_initialised = False


def _init() -> bool:
    global _initialised
    if _initialised:
        return True
    try:
        import firebase_admin
        from firebase_admin import credentials
        from app.core.config import settings
        cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred)
        _initialised = True
        return True
    except Exception as exc:
        logger.warning("Firebase not initialised: %s", exc)
        return False


async def send_fcm_notification(tokens: Sequence[str], title: str, body: str) -> list[str]:
    """
    Send an FCM push notification to a list of device tokens.
    Returns a list of invalid tokens that should be removed from the DB.
    """
    if not tokens or not _init():
        return []
    try:
        from firebase_admin import messaging
        response = messaging.send_each_for_multicast(
            messaging.MulticastMessage(
                notification=messaging.Notification(title=title, body=body),
                android=messaging.AndroidConfig(priority="high"),
                tokens=list(tokens),
            )
        )
        invalid: list[str] = []
        for idx, result in enumerate(response.responses):
            if not result.success:
                code = getattr(result.exception, "code", None)
                if code in ("registration-token-not-registered", "invalid-registration-token"):
                    invalid.append(tokens[idx])
                else:
                    logger.warning("FCM failed for token %s: %s", tokens[idx], result.exception)
        return invalid
    except Exception as exc:
        logger.error("FCM multicast error: %s", exc)
        return []
