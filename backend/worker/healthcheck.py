import json
import math
import socket
import sys
from time import time

from redis import Redis

from app.core.config import get_settings


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"worker", "beat"}:
        return 2
    try:
        with Redis.from_url(
            str(get_settings().redis_url), socket_timeout=2, socket_connect_timeout=2
        ) as redis:
            if sys.argv[1] == "beat":
                value = redis.get("seal:health:beat")
                timestamps = [float(value)] if value else []
            else:
                timestamps = []
                for key in redis.scan_iter(f"seal:health:worker:*@{socket.gethostname()}"):
                    raw = redis.get(key)
                    if raw:
                        timestamps.append(float(json.loads(raw)["at"]))
        return 0 if any(math.isfinite(at) and -30 <= time() - at < 90 for at in timestamps) else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
