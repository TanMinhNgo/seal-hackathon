from worker.celery_app import celery_app
from worker.tasks.ping import ping


def test_ping_task():
    assert ping.apply().get() == "pong"


def test_realtime_and_email_are_routed_away_from_sync():
    for name, queue in {
        "seal.notifications": "realtime",
        "seal.notification_emails": "email",
        "seal.send_email": "email",
        "seal.result_emails": "email",
        "seal.sync_team": "celery",
    }.items():
        assert celery_app.amqp.router.route({}, name)["queue"].name == queue


def test_realtime_dispatch_does_not_wait_for_email(monkeypatch):
    from contextlib import nullcontext
    from unittest.mock import Mock

    from worker.tasks import notifications as tasks

    jobs = Mock()
    jobs.realtime.return_value, jobs.deliver.return_value = 2, 1
    monkeypatch.setattr(tasks, "sync_session_factory", lambda: nullcontext(object()))
    monkeypatch.setattr(tasks, "NotificationJobs", Mock(return_value=jobs))
    assert tasks.notifications.run() == {"realtime": 2, "deliveries": 1}
    jobs.deliver.assert_called_once_with(channel="in_app")
    assert jobs.method_calls[0][0] == "realtime"
    jobs.reset_mock()
    tasks.notification_emails.run()
    jobs.deliver.assert_called_once_with(channel="email")
