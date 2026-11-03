import asyncio
import hashlib
import json
import subprocess
import sys
from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import httpx
import pytest

from app.integrations.storage import Storage
from ops import backup_assets, load_submissions, verify_assets

AGE_RECIPIENT = "age1" + "q" * 58


@pytest.fixture
def load_fixtures():
    return [
        {
            "team_id": str(uuid4()),
            "round_id": str(uuid4()),
            "access_token": "fixture-token",
            "idempotency_key": str(uuid4()),
            "body": {"file_keys": []},
        }
        for _ in range(100)
    ]


def test_load_harness_replays_each_team_without_duplicate_receipts(monkeypatch, load_fixtures):
    monkeypatch.setenv("SEAL_LOAD_ALLOWED_ORIGINS", "https://staging.example")
    requests = []

    def handle(request):
        requests.append((request.url.path, request.headers["Idempotency-Key"]))
        return httpx.Response(201, json={"id": request.url.path, "version": 1})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        load_submissions.httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle)),
    )
    rows = load_fixtures
    result = asyncio.run(load_submissions.run("https://staging.example", rows, 0))
    assert result["passed"] == result["distinct_receipts"] == 100
    assert len(requests) == 200
    assert len(set(requests)) == 100
    operation = load_submissions.run("https://staging.example", rows[:99], 0)
    with pytest.raises(ValueError):
        asyncio.run(operation)
    duplicate_rows = [{**r, "team_id": rows[0]["team_id"]} for r in rows]
    operation = load_submissions.run("https://staging.example", duplicate_rows, 0)
    with pytest.raises(ValueError):
        asyncio.run(operation)


def test_asset_backup_streams_manifest_and_restore_checks_hashes(tmp_path, monkeypatch):
    monkeypatch.setenv("SEAL_RESTORE_ROOT", str(tmp_path))
    identifier = uuid4()
    data = b"%PDF fixture"
    row = SimpleNamespace(
        id=identifier, storage_key="submissions/test.pdf", filename="Đề tài.pdf", size=len(data)
    )
    monkeypatch.setattr(
        backup_assets,
        "sync_session_factory",
        lambda: nullcontext(SimpleNamespace(scalars=lambda query: [row])),
    )
    storage = object.__new__(Storage)
    storage.download = lambda key, name: "https://storage.example/file"
    monkeypatch.setattr(backup_assets, "Storage", lambda settings: storage)
    original_client, original_popen = httpx.Client, subprocess.Popen
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(
            **kwargs,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=data)),
        ),
    )

    def encryption_stub(command, **kwargs):
        # Kiểm tra pipeline ZIP độc lập với CLI age thật, không xem stub là bằng chứng mã hóa.
        assert command[0] == "age"
        assert command[1] == f"--recipient={AGE_RECIPIENT}"
        assert command[2].startswith("--output=")
        return original_popen(
            [
                sys.executable,
                "-c",
                "import pathlib,sys; "
                "pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())",
                command[2].removeprefix("--output="),
            ],
            **kwargs,
        )

    monkeypatch.setattr(backup_assets.subprocess, "Popen", encryption_stub)
    output = tmp_path / "files.age"
    assert backup_assets.backup(output, AGE_RECIPIENT) == 1
    assert verify_assets.restore(output, tmp_path / "restore") == 1
    assert (tmp_path / "restore" / str(identifier)).read_bytes() == data
    with pytest.raises(ValueError):
        backup_assets.backup(output, AGE_RECIPIENT)
    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest[0]["sha256"] == hashlib.sha256(data).hexdigest()
        assert "https://" not in json.dumps(manifest)
    malicious = tmp_path / "malicious.zip"
    with ZipFile(malicious, "w") as archive:
        archive.writestr("manifest.json", json.dumps([{**manifest[0], "entry": "../../escape"}]))
    with pytest.raises(ValueError, match="Invalid manifest"):
        verify_assets.restore(malicious, tmp_path / "unsafe-restore")


@pytest.mark.parametrize("recipient", ["--help", "-o /tmp/leak", "age1bad", AGE_RECIPIENT + "\n"])
def test_backup_rejects_options_and_invalid_recipients_before_side_effects(
    tmp_path, monkeypatch, recipient
):
    from unittest.mock import Mock

    spawn = Mock()
    monkeypatch.setattr(backup_assets.subprocess, "Popen", spawn)
    output = tmp_path / "new" / "backup.age"
    with pytest.raises(ValueError, match="public recipient"):
        backup_assets.backup(output, recipient)
    spawn.assert_not_called()
    assert not output.parent.exists()


def test_restore_requires_isolated_root_and_rejects_target_escape(tmp_path, monkeypatch):
    archive = tmp_path / "unused.zip"
    target = tmp_path / "outside"
    monkeypatch.delenv("SEAL_RESTORE_ROOT", raising=False)
    with pytest.raises(ValueError, match="SEAL_RESTORE_ROOT"):
        verify_assets.restore(archive, target)
    root = tmp_path / "isolated"
    root.mkdir()
    monkeypatch.setenv("SEAL_RESTORE_ROOT", str(root))
    for destination in (target, root / ".." / "outside", root):
        with pytest.raises(ValueError, match="below SEAL_RESTORE_ROOT"):
            verify_assets.restore(archive, destination)
    assert not target.exists()


def test_restore_rejects_symlink_parent_outside_isolated_root(tmp_path, monkeypatch):
    root = tmp_path / "isolated"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating directory symlinks requires Windows privileges")
    monkeypatch.setenv("SEAL_RESTORE_ROOT", str(root))
    target = link / "restored"
    archive = tmp_path / "unused.zip"
    with pytest.raises(ValueError, match="below SEAL_RESTORE_ROOT"):
        verify_assets.restore(archive, target)
    assert not (outside / "restored").exists()


@pytest.mark.parametrize(
    "target",
    [
        "http://169.254.169.254",
        "http://127.0.0.1:8000",
        "https://untrusted.example",
        "https://staging.example@untrusted.example",
        "https://user:pass@staging.example",
        "https://staging.example/api",
        "https://staging.example?token=secret",
        "https://staging.example#fragment",
        "file:///etc/passwd",
    ],
)
def test_load_rejects_unapproved_origins_before_creating_client(monkeypatch, load_fixtures, target):
    from unittest.mock import Mock

    monkeypatch.setenv("SEAL_LOAD_ALLOWED_ORIGINS", "https://staging.example")
    client = Mock()
    monkeypatch.setattr(load_submissions.httpx, "AsyncClient", client)
    operation = load_submissions.run(target, load_fixtures, 0)
    with pytest.raises(ValueError):
        asyncio.run(operation)
    client.assert_not_called()


def test_load_requires_allowlist_and_canonical_ids(monkeypatch, load_fixtures):
    monkeypatch.delenv("SEAL_LOAD_ALLOWED_ORIGINS", raising=False)
    operation = load_submissions.run("https://staging.example", load_fixtures, 0)
    with pytest.raises(ValueError):
        asyncio.run(operation)
    monkeypatch.setenv("SEAL_LOAD_ALLOWED_ORIGINS", "https://staging.example")
    load_fixtures[0]["team_id"] = "../../another-resource"
    operation = load_submissions.run("https://staging.example", load_fixtures, 0)
    with pytest.raises(ValueError):
        asyncio.run(operation)


def test_load_does_not_follow_redirects_with_fixture_tokens(monkeypatch, load_fixtures):
    monkeypatch.setenv("SEAL_LOAD_ALLOWED_ORIGINS", "https://staging.example")
    requests = []

    def redirect(request):
        requests.append(request)
        return httpx.Response(307, headers={"Location": "http://169.254.169.254/metadata"})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        load_submissions.httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(redirect)),
    )
    result = asyncio.run(load_submissions.run("https://staging.example", load_fixtures, 0))
    assert result["passed"] == 0
    assert {request.url.host for request in requests} == {"staging.example"}
