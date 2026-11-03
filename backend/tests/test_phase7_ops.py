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


def test_load_harness_replays_each_team_without_duplicate_receipts(monkeypatch):
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
    rows = [
        {
            "team_id": str(uuid4()),
            "round_id": str(uuid4()),
            "access_token": "fixture-token",
            "idempotency_key": str(uuid4()),
            "body": {"file_keys": []},
        }
        for _ in range(100)
    ]
    result = asyncio.run(load_submissions.run("https://staging.example", rows, 0))
    assert result["passed"] == result["distinct_receipts"] == 100
    assert len(requests) == 200 and len(set(requests)) == 100
    with pytest.raises(ValueError):
        asyncio.run(load_submissions.run("https://staging.example", rows[:99], 0))
    with pytest.raises(ValueError):
        asyncio.run(
            load_submissions.run(
                "https://staging.example", [{**r, "team_id": rows[0]["team_id"]} for r in rows], 0
            )
        )


def test_asset_backup_streams_manifest_and_restore_checks_hashes(tmp_path, monkeypatch):
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
        assert command[0] == "age" and command[1:3] == ["-r", "test-public-key"]
        return original_popen(
            [
                sys.executable,
                "-c",
                "import pathlib,sys; "
                "pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())",
                command[-1],
            ],
            **kwargs,
        )

    monkeypatch.setattr(backup_assets.subprocess, "Popen", encryption_stub)
    output = tmp_path / "files.age"
    assert backup_assets.backup(output, "test-public-key") == 1
    assert verify_assets.restore(output, tmp_path / "restore") == 1
    assert (tmp_path / "restore" / str(identifier)).read_bytes() == data
    with pytest.raises(ValueError):
        backup_assets.backup(output, "test-public-key")
    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest[0]["sha256"] == hashlib.sha256(data).hexdigest()
        assert "https://" not in json.dumps(manifest)
    malicious = tmp_path / "malicious.zip"
    with ZipFile(malicious, "w") as archive:
        archive.writestr("manifest.json", json.dumps([{**manifest[0], "entry": "../../escape"}]))
    with pytest.raises(ValueError, match="Invalid manifest"):
        verify_assets.restore(malicious, tmp_path / "unsafe-restore")
