"""Gửi fixture 100 đội vào staging; không tạo tài khoản hoặc in access token."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from statistics import quantiles
from time import perf_counter
from uuid import UUID

import httpx


def load_origin(base_url: str) -> str:
    url = httpx.URL(base_url)
    allowed = os.environ.get("SEAL_LOAD_ALLOWED_ORIGINS", "").split(",")
    if (
        url.scheme not in {"http", "https"}
        or not url.host
        or url.userinfo
        or url.query
        or url.fragment
        or url.path != "/"
        or str(url).rstrip("/") not in {origin.strip().rstrip("/") for origin in allowed}
    ):
        raise ValueError("Load target must match SEAL_LOAD_ALLOWED_ORIGINS without a path")
    return str(url)


async def run(base_url: str, fixtures: list[dict], seconds: float) -> dict:
    base_url = load_origin(base_url)
    fixtures = [
        {**row, "team_id": str(UUID(row["team_id"])), "round_id": str(UUID(row["round_id"]))}
        for row in fixtures
    ]
    if len(fixtures) != 100 or len({r["team_id"] for r in fixtures}) != 100:
        raise ValueError("Exactly 100 distinct team/round fixtures are required")
    started = perf_counter()
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=45,
        limits=httpx.Limits(max_connections=100),
        follow_redirects=False,
        trust_env=False,
    ) as client:

        async def submit(index: int, row: dict) -> tuple:
            await asyncio.sleep(max(0, started + index * seconds / 100 - perf_counter()))
            path = f"/api/v1/teams/{row['team_id']}/rounds/{row['round_id']}/submissions"
            headers = {
                "Authorization": f"Bearer {row['access_token']}",
                "Idempotency-Key": row["idempotency_key"],
            }
            before = perf_counter()
            try:
                first = await client.post(path, headers=headers, json=row["body"])
                replay = await client.post(path, headers=headers, json=row["body"])
                ok = (
                    first.status_code == replay.status_code == 201
                    and first.json()["id"] == replay.json()["id"]
                    and first.json()["version"] == replay.json()["version"]
                )
                return ok, perf_counter() - before, first.json().get("id") if ok else None
            except (httpx.HTTPError, ValueError, KeyError):
                return False, perf_counter() - before, None

        results = await asyncio.gather(*(submit(i, row) for i, row in enumerate(fixtures)))
    accepted = [r[2] for r in results if r[0]]
    return {
        "teams": 100,
        "passed": len(accepted),
        "distinct_receipts": len(set(accepted)),
        "elapsed_seconds": round(perf_counter() - started, 2),
        "p95_with_replay_seconds": round(quantiles([r[1] for r in results], n=100)[94], 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("fixtures", type=Path)
    args = parser.parse_args()
    result = asyncio.run(
        run(args.base_url, json.loads(args.fixtures.read_text(encoding="utf-8")), 60)
    )
    sys.stdout.write(json.dumps(result) + "\n")
    raise SystemExit(0 if result["passed"] == result["distinct_receipts"] == 100 else 1)


if __name__ == "__main__":
    main()
