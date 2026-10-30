import re

import httpx

from app.core.config import Settings
from app.core.errors import ApiError


async def verify_public_repo(repo_url: str, settings: Settings) -> str:
    match = re.fullmatch(
        r"https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)/?", repo_url.strip()
    )
    if not match:
        raise ApiError(422, "REPO_NOT_ACCESSIBLE", "Expected https://github.com/owner/repo")
    owner, repo = match.groups()
    repo = repo.removesuffix(".git")
    if repo in ("", ".", ".."):
        raise ApiError(422, "REPO_NOT_ACCESSIBLE", "Invalid repository name")
    if not settings.github_token or not settings.github_token.get_secret_value():
        raise ApiError(503, "GITHUB_NOT_CONFIGURED", "GitHub access is not configured")
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers={
                    "Authorization": f"Bearer {settings.github_token.get_secret_value()}",
                    "Accept": "application/vnd.github+json",
                },
            )
        if response.status_code == 429 or (
            response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0"
        ):
            raise ApiError(503, "GITHUB_UNAVAILABLE", "GitHub rate limit exceeded")
        if response.status_code >= 500 or response.status_code == 401:
            raise ApiError(503, "GITHUB_UNAVAILABLE", "GitHub access is unavailable")
        payload = response.json() if response.status_code == 200 else {}
        if not isinstance(payload, dict):
            raise ApiError(503, "GITHUB_UNAVAILABLE", "Invalid response from GitHub")
        if (
            response.status_code != 200
            or payload.get("private") is not False
            or payload.get("disabled", False)
        ):
            raise ApiError(422, "REPO_NOT_ACCESSIBLE", "Repository must be public and accessible")
    except (httpx.HTTPError, ValueError):
        raise ApiError(503, "GITHUB_UNAVAILABLE", "GitHub access is unavailable") from None
    return f"https://github.com/{owner}/{repo}"
