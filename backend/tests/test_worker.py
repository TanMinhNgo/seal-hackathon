from worker.tasks.ping import ping


def test_ping_task():
    assert ping.apply().get() == "pong"
