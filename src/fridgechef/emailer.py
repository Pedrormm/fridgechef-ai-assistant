from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from src.fridgechef.security import is_valid_email


def send_email_if_enabled(subject: str, body: str, email_to: str, enabled: bool) -> bool:
    """Send an optional email without breaking the main flow when SMTP is unavailable."""
    if not enabled:
        return False
    if not is_valid_email(email_to):
        print(f"Skipping email because the destination address is not valid: {email_to}")
        return False

    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", user)

    if not host or not user or not password or not sender:
        print("Skipping email because SMTP is not fully configured.")
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = email_to
    message.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(message)
        return True
    except Exception as exc:
        print(f"Email could not be sent, continuing without blocking the process: {exc}")
        return False
