# app/security/recaptcha.py
import os
import httpx
from fastapi import HTTPException, status

RECAPTCHA_SECRET = os.getenv("RECAPTCHA_SECRET", "")
RECAPTCHA_BYPASS = os.getenv("RECAPTCHA_BYPASS", "")

async def verify_recaptcha_or_400(token: str, remote_ip: str | None = None) -> None:
    """
    Verify Google reCAPTCHA v2 token. Raises HTTP 400 on failure.
    Set RECAPTCHA_BYPASS=true to skip in dev only (keep fail-closed in prod).
    """
    if RECAPTCHA_BYPASS:
        return

    if not RECAPTCHA_SECRET:
        raise HTTPException(status_code=400, detail="reCAPTCHA not configured")

    if not token:
        raise HTTPException(status_code=400, detail="Missing reCAPTCHA")

    data = {"secret": RECAPTCHA_SECRET, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post("https://www.google.com/recaptcha/api/siteverify", data=data)

    payload = r.json()
    if not payload.get("success"):
        # (Optional) You can also check error-codes: payload.get("error-codes")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reCAPTCHA")
