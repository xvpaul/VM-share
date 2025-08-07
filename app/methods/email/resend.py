import httpx
import os
import logging



async def send_verification_email(email: str, token: str):
    RESEND_API_KEY = os.getenv("RESEND_API_KEY")
    verify_url = f"http://83.69.248.229:8000/verify-email?token={token}"
    logging.info(f"Sending verification email to {email} with token: {token}")

    payload = {
        "from": "you@yourdomain.com",  # must be verified in Resend
        "to": email,
        "subject": "Verify your email",
        "html": f"<p>Click <a href='{verify_url}'>here</a> to verify your account.</p>"
    }

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post("https://api.resend.com/emails", json=payload, headers=headers)
            response.raise_for_status()
        logging.info(f"Verification email successfully sent to {email}")
    except httpx.HTTPError as e:
        logging.error(f"Failed to send verification email to {email}: {e}")
        raise
