import asyncio
import math
from datetime import UTC, datetime
from time import perf_counter, time

from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings
from app.integrations import system_monitor
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import DataCounts, ServiceStatus, SystemOverview, UserOutput
from app.modules.auth.service import AuthService
from worker.celery_app import celery_app
from worker.tasks.send_email import send_email


def elapsed_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))


class SystemService:
    def __init__(self, repository: AuthRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    async def overview(self, user: UserOutput) -> SystemOverview:
        AuthService.require_admin(user)
        database, redis, workers, beat = await asyncio.gather(
            self.database(), self.redis(), self.workers(), self.beat()
        )
        status, data = database
        return SystemOverview(
            server_time=datetime.now(UTC),
            services=[
                status,
                redis,
                *workers,
                beat,
                ServiceStatus(
                    name="storage",
                    status="not_configured",
                    detail="Storage provider is not configured",
                ),
            ],
            data=data,
        )

    async def database(self) -> tuple[ServiceStatus, DataCounts]:
        start = perf_counter()
        try:
            data = await asyncio.wait_for(self.repository.system_data(), timeout=2)
        except Exception:
            return ServiceStatus(
                name="database",
                status="down",
                latency_ms=elapsed_ms(start),
                detail="Database statistics unavailable; counts are unknown",
            ), DataCounts()
        return ServiceStatus(name="database", status="ok", latency_ms=elapsed_ms(start)), data

    async def redis(self) -> ServiceStatus:
        start = perf_counter()
        try:
            await asyncio.wait_for(
                system_monitor.ping_redis(str(self.settings.redis_url)), timeout=2
            )
        except Exception:
            return ServiceStatus(
                name="redis",
                status="down",
                latency_ms=elapsed_ms(start),
                detail="Redis probe failed",
            )
        return ServiceStatus(name="redis", status="ok", latency_ms=elapsed_ms(start))

    async def workers(self) -> tuple[ServiceStatus, ServiceStatus]:
        start = perf_counter()
        try:
            queues = await asyncio.wait_for(
                run_in_threadpool(system_monitor.worker_queues, str(self.settings.redis_url)),
                timeout=2,
            )
        except Exception:
            queues = None
        latency = elapsed_ms(start)
        worker = ServiceStatus(
            name="worker",
            status="ok" if queues is not None else "degraded",
            latency_ms=latency,
            detail=None
            if queues is not None
            else "No worker reply; worker may be busy or unavailable",
        )
        mail_queue = celery_app.amqp.router.route({}, send_email.name)["queue"].name
        email = ServiceStatus(
            name="email_queue",
            status="ok" if queues is not None and mail_queue in queues else "degraded",
            latency_ms=latency,
            detail="Queue consumer detected; SMTP and inbox delivery not checked"
            if queues is not None and mail_queue in queues
            else "Email queue consumer not confirmed",
        )
        return worker, email

    async def beat(self) -> ServiceStatus:
        start = perf_counter()
        try:
            timestamp = await asyncio.wait_for(
                system_monitor.beat_heartbeat(str(self.settings.redis_url)), timeout=2
            )
            if timestamp is None or time() - timestamp >= 90:
                return ServiceStatus(
                    name="beat",
                    status="down",
                    latency_ms=elapsed_ms(start),
                    detail="Beat heartbeat missing or stale",
                )
            if not math.isfinite(timestamp) or timestamp - time() > 30:
                raise ValueError("Invalid heartbeat timestamp")
        except Exception:
            return ServiceStatus(
                name="beat",
                status="degraded",
                latency_ms=elapsed_ms(start),
                detail="Beat heartbeat could not be verified",
            )
        return ServiceStatus(name="beat", status="ok", latency_ms=elapsed_ms(start))
