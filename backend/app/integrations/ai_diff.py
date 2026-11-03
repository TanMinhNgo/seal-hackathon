import base64
import re
from pathlib import PurePosixPath

from app.integrations.github_sync import GitHubSync, GitHubSyncError

MAX_DIFF_BYTES = 24000
CODE_SUFFIXES = set(
    ".py .js .ts .tsx .jsx .go .java .c .h .cpp .hpp .cs .rb .rs .php .swift .kt "
    ".dart .sql .sh .ps1 .vue .svelte .html .css .scss .ex .exs .scala .r .jl .lua .m .mm".split()
)
IGNORED = {"node_modules", "build", "dist", "vendor", "coverage", ".next", ".git", "__pycache__"}
SECRETS = re.compile(
    r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----"
    r"|\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|sk-[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16}"
    r"|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b"
    r"|(?i:(?:password|passwd|secret|api[_-]?key|access[_-]?token)\s*[\"']?\s*[:=]\s*"
    r"[\"']?[^\s\"',;]{4,})"
)


def redact(text: str) -> str:
    return SECRETS.sub("[REDACTED]", text)


def bounded(text: str, size: int) -> str:
    return text.encode("utf-8")[:size].decode("utf-8", errors="ignore")


def code_file(path: str) -> bool:
    name = PurePosixPath(path)
    return (
        name.suffix.lower() in CODE_SUFFIXES
        and not (set(name.parts) & IGNORED)
        and not any(marker in name.name.lower() for marker in (".min.", ".generated.", ".g."))
        and not name.is_absolute()
        and ".." not in name.parts
    )


def prepare(data: dict) -> tuple[dict, dict, dict[str, set[int]], int]:
    files = []
    locations = {}
    remaining = MAX_DIFF_BYTES
    weight = 0
    omitted = 0
    truncated = data.get("truncated", False)
    for row in data["files"]:
        path = row["filename"]
        patch = row.get("patch")
        if not code_file(path) or not patch or remaining <= 0:
            omitted += 1
            truncated |= not patch or remaining <= 0
            continue
        patch = redact(patch)
        size = len(patch.encode("utf-8"))
        if size > remaining:
            # Giữ dòng nguyên vẹn để không xác nhận vị trí trên phần patch bị cắt.
            patch = bounded(patch, remaining).rsplit("\n", 1)[0]
            truncated = True
        if not patch or not any(line.startswith(("+", "-")) for line in patch.splitlines()):
            omitted += 1
            continue
        remaining -= len(patch.encode("utf-8"))
        line_number = None
        allowed = set()
        for line in patch.splitlines():
            if match := re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line):
                line_number = int(match[1])
            elif line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                weight += 1
                if line.startswith("+") and line_number is not None:
                    allowed.add(line_number)
                    line_number += 1
            elif line.startswith(" ") and line_number is not None:
                allowed.add(line_number)
                line_number += 1
        locations[redact(path)] = allowed
        files.append({"path": redact(path), "patch": patch})
    payload = {
        "files": files,
        "readme": bounded(redact(data.get("readme", "")), 2000),
        "tree": [bounded(redact(p), 500) for p in data.get("tree", [])[:100]],
        "messages": [bounded(redact(m), 500) for m in data.get("messages", [])[:100]],
    }
    return (
        payload,
        {"reviewed_files": len(files), "omitted_files": omitted, "truncated": bool(truncated)},
        locations,
        weight,
    )


class GitHubReview(GitHubSync):
    def compare(self, base: str, head: str, heartbeat: object) -> dict:
        heartbeat()
        meta, _ = self.get()
        if meta.get("private") is not False or meta.get("disabled"):
            raise GitHubSyncError("REPO_NOT_ACCESSIBLE")
        data, more = self.get(f"/compare/{base}...{head}", per_page=100, page=1)
        commits = list(data.get("commits", []))
        for page in range(2, 101):
            if not more:
                break
            heartbeat()
            batch, more = self.get(f"/compare/{base}...{head}", per_page=100, page=page)
            rows = batch.get("commits", [])
            if not rows:
                break
            commits.extend(rows)
        files = data.get("files", [])
        result = {
            "files": files,
            "shas": [c["sha"] for c in commits if len(c.get("parents", [])) <= 1],
            "messages": [c["commit"]["message"] for c in commits if len(c.get("parents", [])) <= 1],
            "complete": not more
            and len(commits) == data.get("total_commits")
            and len({c["sha"] for c in commits}) == len(commits)
            and data.get("status") in {"ahead", "identical"}
            and data.get("merge_base_commit", {}).get("sha") == base,
            "truncated": len(files) >= 300,
        }
        if not result["complete"]:
            return result
        heartbeat()
        meta, _ = self.get("/git/commits/" + head)
        tree, _ = self.get("/git/trees/" + meta["tree"]["sha"], recursive=1)
        result["tree"] = [r["path"] for r in tree.get("tree", [])[:100]]
        result["truncated"] |= tree.get("truncated", False) or len(tree.get("tree", [])) > 100
        readme = next(
            (
                r
                for r in tree.get("tree", [])
                if r["path"].lower() in {"readme", "readme.md", "readme.rst", "readme.txt"}
                and r.get("type") == "blob"
            ),
            None,
        )
        if readme and readme.get("size", 0) <= 65536:
            heartbeat()
            blob, _ = self.get("/git/blobs/" + readme["sha"])
            content = base64.b64decode(blob["content"]).decode("utf-8", errors="replace")
            result["readme"] = bounded(content, 2000)
            result["truncated"] |= len(content.encode("utf-8")) > 2000
        else:
            result["truncated"] = True
        return result
