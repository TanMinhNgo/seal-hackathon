import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import get_settings


def send_email(recipient: str, subject: str, body: str) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        raise RuntimeError("SMTP is not configured")
    message = EmailMessage()
    message["From"] = str(settings.smtp_from)
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()
    if settings.smtp_tls == "ssl":
        client = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=20, context=context
        )
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
    with client:
        if settings.smtp_tls == "starttls":
            client.starttls(context=context)
        if settings.smtp_username:
            if settings.smtp_tls == "none":
                raise RuntimeError("SMTP authentication requires TLS")
            if not settings.smtp_password or not settings.smtp_password.get_secret_value():
                raise RuntimeError("SMTP password is missing")
            client.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        refused = client.send_message(message)
        if refused:
            raise RuntimeError("SMTP recipient was rejected")
