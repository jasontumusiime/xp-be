"""
Africa's Talking integration — SMS and voice call utilities.

Set AT_USERNAME and AT_API_KEY in .env to enable.
Use AT_USERNAME=sandbox and the sandbox API key for testing.
"""
from __future__ import annotations

import logging
from typing import Any

import africastalking as _at

from app.core.config import settings

logger = logging.getLogger(__name__)

_initialised = False


def _init() -> None:
    global _initialised
    if not _initialised:
        _at.initialize(settings.AT_USERNAME, settings.AT_API_KEY)
        _initialised = True


def send_sms(recipients: list[str], message: str) -> dict[str, Any]:
    """
    Send an SMS to one or more Ugandan phone numbers (+256…).
    Returns the Africa's Talking API response dict.
    Raises on failure.
    """
    _init()
    sms = _at.SMS
    kwargs: dict[str, Any] = {"message": message, "recipients": recipients}
    if settings.AT_SENDER_ID:
        kwargs["senderId"] = settings.AT_SENDER_ID
    try:
        response = sms.send(**kwargs)
        logger.info("AT SMS sent to %s: %s", recipients, response)
        return response  # type: ignore[return-value]
    except Exception as exc:
        logger.error("AT SMS failed: %s", exc)
        raise


def initiate_call(caller_id: str, destination: str) -> dict[str, Any]:
    """
    Initiate a click-to-call from caller_id to destination.
    Both numbers must be in international format (+256…).
    """
    _init()
    voice = _at.Voice
    try:
        response = voice.call(callFrom=caller_id, callTo=[destination])
        logger.info("AT call %s → %s: %s", caller_id, destination, response)
        return response  # type: ignore[return-value]
    except Exception as exc:
        logger.error("AT call failed: %s", exc)
        raise
