from unittest.mock import MagicMock

import pytest

from app.integrations import mailer
from worker.tasks import send_email


@pytest.mark.parametrize("tls", ["starttls", "ssl"])
def test_smtp_tls_authentication_and_message(monkeypatch, auth_settings, tls):
    auth_settings.smtp_tls = tls
    auth_settings.smtp_port = 465 if tls == "ssl" else 587
    monkeypatch.setattr(mailer, "get_settings", lambda: auth_settings)
    constructor = MagicMock()
    client = constructor.return_value
    client.__enter__.return_value = client
    client.send_message.return_value = {}
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL" if tls == "ssl" else "SMTP", constructor)
    mailer.send_email("recipient@example.com", "Verify email", "Verification link")
    if tls == "starttls":
        client.starttls.assert_called_once()
    else:
        client.starttls.assert_not_called()
    client.login.assert_called_once_with("sender@example.com", "test-smtp-password")
    message = client.send_message.call_args.args[0]
    assert message["To"] == "recipient@example.com" and "Verification link" in message.get_content()


def test_task_suppresses_provider_error_details(monkeypatch):
    def reject(*args):
        raise RuntimeError("provider details that must not appear in task error")

    monkeypatch.setattr(send_email, "deliver_email", reject)
    with pytest.raises(RuntimeError) as error:
        send_email.send_email.run("recipient@example.com", "Subject", "Body")
    assert "provider details" not in str(error.value)
    assert error.value.__suppress_context__
