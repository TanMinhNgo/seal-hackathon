import re
from collections.abc import Callable, Iterator
from datetime import datetime
from urllib.parse import quote

import httpx
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import Settings

MAX_FILES = 1000
MAX_PATCH_BYTES = 1024 * 1024
RATE_KEY = "seal:github:sync:rate-limit"
RATE_RESERVE = 500
COMMIT_SHA = r"[0-9a-f]{40}"


def budget_pause(settings: Settings) -> int:
    try:
        with Redis.from_url(
            str(settings.redis_url), socket_timeout=3, socket_connect_timeout=3
        ) as client:
            return max(0, client.ttl(RATE_KEY))
    except RedisError:
        raise GitHubSyncError("SYNC_COORDINATION_UNAVAILABLE") from None


class GitHubSyncError(Exception):
    def __init__(self, code: str, retry_after: int = 60) -> None:
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)


class GitHubSync:
    def __init__(self, settings: Settings, repo_url: str) -> None:
        match = re.fullmatch(r"https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)", repo_url)
        if not match or match[2] in {".", ".."}:
            raise GitHubSyncError("REPO_NOT_ACCESSIBLE")
        if not settings.github_token:
            raise GitHubSyncError("GITHUB_NOT_CONFIGURED")
        self.path = "/repos/" + "/".join(match.groups())
        self.url = repo_url
        self.settings = settings
        self.client = httpx.Client(
            base_url="https://api.github.com",
            timeout=15,
            follow_redirects=False,
            headers={
                "Authorization": f"Bearer {settings.github_token.get_secret_value()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def close(self) -> None:
        self.client.close()

    def get(self, suffix: str = "", **params: object) -> tuple[object, bool]:
        return self.request("GET", self.path + suffix, params=params)

    def request(self, method: str, path: str, **kwargs: object) -> tuple[object, bool]:
        try:
            if pause := budget_pause(self.settings):
                raise GitHubSyncError("GITHUB_RATE_LIMITED", pause)
            response = self.client.request(method, path, **kwargs)
            remaining = int(response.headers.get("x-ratelimit-remaining", "5000"))
            if (
                response.status_code == 429
                or remaining <= RATE_RESERVE
                or (response.status_code == 403 and "retry-after" in response.headers)
            ):
                reset = int(response.headers.get("x-ratelimit-reset", "0"))
                pause = max(
                    60,
                    reset - int(datetime.now().timestamp()),
                    int(response.headers.get("retry-after", "0")),
                )
                try:
                    with Redis.from_url(
                        str(self.settings.redis_url), socket_timeout=3, socket_connect_timeout=3
                    ) as client:
                        client.set(RATE_KEY, "1", ex=pause)
                except RedisError:
                    raise GitHubSyncError("SYNC_COORDINATION_UNAVAILABLE") from None
                raise GitHubSyncError("GITHUB_RATE_LIMITED", pause)
            if response.status_code in {404, 410, 301, 302}:
                raise GitHubSyncError("REPO_NOT_ACCESSIBLE")
            if response.status_code != 200:
                raise GitHubSyncError("GITHUB_UNAVAILABLE")
            return response.json(), "next" in response.links
        except (httpx.HTTPError, ValueError):
            raise GitHubSyncError("GITHUB_UNAVAILABLE") from None

    def baseline(self, shas: list[str], heartbeat: Callable[[], None]) -> Iterator[dict]:
        owner, name = self.path.removeprefix("/repos/").split("/")
        for start in range(0, len(shas), 100):
            batch = shas[start : start + 100]
            if any(not re.fullmatch(COMMIT_SHA, sha) for sha in batch):
                raise GitHubSyncError("GITHUB_UNAVAILABLE")
            heartbeat()
            fields = " ".join(
                f'c{i}: object(oid:"{sha}") {{ ... on Commit {{ '
                "oid message committedDate author { name } additions deletions } }"
                for i, sha in enumerate(batch)
            )
            data, _ = self.request(
                "POST",
                "/graphql",
                json={
                    "query": "query($owner:String!,$name:String!){"
                    "repository(owner:$owner,name:$name){isPrivate " + fields + "}}",
                    "variables": {"owner": owner, "name": name},
                },
            )
            yield from self.baseline_rows(data, batch)

    def baseline_rows(self, data: object, batch: list[str]) -> list[dict]:
        try:
            if not isinstance(data, dict) or data.get("errors"):
                raise ValueError("Incomplete metadata batch")
            repo = data["data"]["repository"]
            if repo["isPrivate"] is not False:
                raise GitHubSyncError("REPO_NOT_ACCESSIBLE")
            return [self.baseline_row(repo[f"c{i}"], sha) for i, sha in enumerate(batch)]
        except (KeyError, TypeError, ValueError, AttributeError):
            raise GitHubSyncError("GITHUB_UNAVAILABLE") from None

    def baseline_row(self, row: dict, sha: str) -> dict:
        if row["oid"] != sha or any(
            type(row[k]) is not int or row[k] < 0 for k in ("additions", "deletions")
        ):
            raise ValueError("Invalid commit metadata")
        if not isinstance(row["message"], str):
            raise ValueError("Invalid commit message")
        return {
            "sha": sha,
            "author": (row.get("author") or {}).get("name") or "Unknown",
            "message": row["message"],
            "committed_at": datetime.fromisoformat(row["committedDate"].replace("Z", "+00:00")),
            "additions": row["additions"],
            "deletions": row["deletions"],
            "url": f"{self.url}/commit/{sha}",
            "files": [],
            "diff_truncated": True,
        }

    def branch_head(self, branch: str | None) -> tuple[str, str]:
        meta, _ = self.get()
        if not isinstance(meta, dict) or meta.get("private") is not False or meta.get("disabled"):
            raise GitHubSyncError("REPO_NOT_ACCESSIBLE")
        branch = branch or meta["default_branch"]
        head, _ = self.get("/commits/" + quote(branch, safe=""))
        sha = head["sha"]
        if not re.fullmatch(COMMIT_SHA, sha):
            raise GitHubSyncError("GITHUB_UNAVAILABLE")
        return branch, sha

    def history(self, head: str, heartbeat: Callable[[], None]) -> tuple[list[str], bool]:
        shas = []
        parents = set()
        for page in range(1, 101):
            heartbeat()
            rows, more = self.get("/commits", sha=head, per_page=100, page=page)
            if not isinstance(rows, list) or (more and not rows):
                raise GitHubSyncError("GITHUB_INCOMPLETE_HISTORY")
            for row in rows:
                sha = row["sha"]
                if not re.fullmatch(COMMIT_SHA, sha):
                    raise GitHubSyncError("GITHUB_UNAVAILABLE")
                shas.append(sha)
                parents.update(parent["sha"] for parent in row["parents"])
            if not more:
                # An empty history for a resolved head cannot prove reachability.
                if not shas or head not in shas or len(set(shas)) != len(shas):
                    raise GitHubSyncError("GITHUB_INCOMPLETE_HISTORY")
                return shas, not (parents - set(shas))
        return shas, False

    def detail(self, sha: str, heartbeat: Callable[[], None]) -> dict:
        files = []
        budget = MAX_PATCH_BYTES
        truncated = False
        first = None
        for page in range(1, 11):
            heartbeat()
            data, more = self.get("/commits/" + sha, per_page=100, page=page)
            if first is None:
                first = data
            if data["sha"] != sha:
                raise GitHubSyncError("GITHUB_UNAVAILABLE")
            for file in data.get("files", []):
                if len(files) >= MAX_FILES:
                    truncated = True
                    break
                patch = file.get("patch")
                missing = patch is None
                encoded = patch.encode("utf-8") if patch is not None else b""
                cut = len(encoded) > budget
                patch = (
                    encoded[:budget].decode("utf-8", errors="ignore") if patch is not None else None
                )
                budget -= len(patch.encode("utf-8")) if patch is not None else 0
                files.append(
                    {
                        "path": file["filename"],
                        "previous_path": file.get("previous_filename"),
                        "status": file["status"],
                        "additions": file["additions"],
                        "deletions": file["deletions"],
                        "patch": patch,
                        "binary": None if missing else False,
                        "truncated": missing or cut,
                    }
                )
                truncated |= missing or cut
            if not more:
                break
            if len(files) >= MAX_FILES:
                truncated = True
                break
        else:
            truncated = True
        meta = first["commit"]
        return {
            "sha": sha,
            "author": (meta.get("author") or {}).get("name") or "Unknown",
            "message": meta["message"],
            "committed_at": datetime.fromisoformat(
                meta["committer"]["date"].replace("Z", "+00:00")
            ),
            "additions": first["stats"]["additions"],
            "deletions": first["stats"]["deletions"],
            "url": f"{self.url}/commit/{sha}",
            "files": files,
            "diff_truncated": truncated,
        }
