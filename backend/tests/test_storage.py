from io import BytesIO
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit
from zipfile import ZipFile

import cloudinary.api
import cloudinary.uploader
import cloudinary.utils
import httpx
import pytest
from cloudinary.exceptions import Error, NotFound
from pydantic import SecretStr

from app.core.config import Settings
from app.core.errors import ApiError
from app.integrations import github_client
from app.integrations.storage import Storage


def settings():
    return Settings(
        _env_file=None,
        cloudinary_cloud_name="seal-test",
        cloudinary_api_key=SecretStr("test-access-key"),
        cloudinary_api_secret=SecretStr("test-secret-key"),
    )


def test_signed_urls_expiry_and_attachment(monkeypatch):
    monkeypatch.setattr("app.integrations.storage.time", lambda: 100000)
    client = Storage(settings())
    url, fields = client.presign("uploads/random.pdf", "application/pdf", 12)
    assert url == "https://api.cloudinary.com/v1_1/seal-test/raw/upload"
    assert int(fields["timestamp"]) + 3600 == 100600
    assert fields["type"] == "authenticated" and fields["overwrite"] == "false"
    params = {k: v for k, v in fields.items() if k not in {"signature", "api_key"}}
    assert fields["signature"] == cloudinary.utils.api_sign_request(
        params, "test-secret-key", algorithm="sha256"
    )
    assert fields["signature"] != cloudinary.utils.api_sign_request(
        {**params, "overwrite": "true"}, "test-secret-key", algorithm="sha256"
    )
    assert "test-secret-key" not in str(fields)
    download_url = client.download("submissions/random.pdf", "bài nộp.pdf")
    download = parse_qs(urlsplit(download_url).query)
    assert download["expires_at"] == ["100300"]
    assert download["attachment"] == ["1"]
    assert download["type"] == ["authenticated"]
    assert download["public_id"] == ["submissions/random.pdf"] and "format" not in download
    with pytest.raises(ValueError):
        client.delete_temporary("submissions/never-delete")


def zip_data(*names):
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        for name in names:
            archive.writestr(name, "data")
    return data.getvalue()


@pytest.mark.parametrize(
    "filename,mime,data,valid",
    [
        ("a.pdf", "application/pdf", b"%PDF-1.7 content", True),
        ("a.pdf", "application/pdf", b"MZ executable", False),
        ("a.mp4", "video/mp4", b"\x00\x00\x00\x18ftypmp42", True),
        ("a.zip", "application/zip", zip_data("test.txt"), True),
        ("a.zip", "application/zip", b"PK\x03\x04invalid", False),
        (
            "a.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            zip_data("[Content_Types].xml", "ppt/presentation.xml"),
            True,
        ),
        (
            "a.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            zip_data("test.txt"),
            False,
        ),
    ],
)
def test_seal_checks_renamed_authenticated_bytes(monkeypatch, filename, mime, data, valid):
    client = Storage(settings())
    resource = Mock(
        return_value={
            "public_id": "uploads/source",
            "bytes": len(data),
            "type": "authenticated",
            "resource_type": "raw",
        }
    )
    rename = Mock()
    monkeypatch.setattr(cloudinary.api, "resource", resource)
    monkeypatch.setattr(cloudinary.uploader, "rename", rename)
    original = httpx.Client

    def respond(request):
        assert request.url.params["public_id"] == "submissions/target"
        assert request.url.params["type"] == "authenticated"
        return httpx.Response(200, content=data)

    monkeypatch.setattr(
        "app.integrations.storage.httpx.Client",
        lambda **kw: original(transport=httpx.MockTransport(respond), **kw),
    )
    if valid:
        client.seal("uploads/source", "submissions/target", filename, mime, len(data))
    else:
        with pytest.raises(ApiError) as error:
            client.seal("uploads/source", "submissions/target", filename, mime, len(data))
        assert error.value.code == "FILE_TYPE_NOT_ALLOWED"
    assert rename.call_args.args == ("uploads/source", "submissions/target")
    assert rename.call_args.kwargs["overwrite"] is False
    assert rename.call_args.kwargs["type"] == "authenticated"


@pytest.mark.parametrize(
    "exception,code",
    [
        (NotFound("missing"), "FILE_NOT_UPLOADED"),
        (Error("rate limited"), "STORAGE_UNAVAILABLE"),
    ],
)
def test_storage_provider_errors(monkeypatch, exception, code):
    client = Storage(settings())
    monkeypatch.setattr(cloudinary.api, "resource", Mock(side_effect=exception))
    with pytest.raises(ApiError) as error:
        client.seal("uploads/source", "submissions/target", "a.pdf", "application/pdf", 12)
    assert error.value.code == code


def test_storage_size_and_missing_configuration(monkeypatch):
    with pytest.raises(ApiError) as error:
        Storage(Settings(_env_file=None))
    assert error.value.code == "STORAGE_NOT_CONFIGURED"
    client = Storage(settings())
    monkeypatch.setattr(
        cloudinary.api,
        "resource",
        Mock(
            return_value={
                "public_id": "uploads/a",
                "bytes": 1000,
                "type": "authenticated",
                "resource_type": "raw",
            }
        ),
    )
    rename = Mock()
    monkeypatch.setattr(cloudinary.uploader, "rename", rename)
    with pytest.raises(ApiError) as error:
        client.seal("uploads/a", "submissions/a", "a.pdf", "application/pdf", 12)
    assert error.value.code == "FILE_NOT_UPLOADED"
    rename.assert_not_called()


def test_destroy_authenticated_only_and_idempotent(monkeypatch):
    destroy = Mock(return_value={"result": "not found"})
    monkeypatch.setattr(cloudinary.uploader, "destroy", destroy)
    client = Storage(settings())
    client.delete_temporary("uploads/old.pdf")
    assert destroy.call_args.kwargs["resource_type"] == "raw"
    assert destroy.call_args.kwargs["type"] == "authenticated"
    client.discard_unsubmitted("submissions/failed.pdf")
    destroy.return_value = {"result": "unexpected"}
    with pytest.raises(ApiError):
        client.delete_temporary("uploads/old.pdf")


@pytest.mark.parametrize(
    "status,payload,code",
    [
        (200, {"sha": "a" * 40}, None),
        (200, {"sha": "bad"}, "REPO_UNAVAILABLE"),
        (503, {}, "REPO_UNAVAILABLE"),
        (404, {}, "REPO_UNAVAILABLE"),
    ],
)
def test_github_head_snapshot(monkeypatch, status, payload, code):
    import asyncio
    from unittest.mock import AsyncMock

    config = settings()
    config.github_token = SecretStr("test-github-token")
    monkeypatch.setattr(
        github_client,
        "verify_public_repo",
        AsyncMock(return_value="https://github.com/example/public"),
    )
    original = httpx.AsyncClient

    def respond(request):
        assert str(request.url) == "https://api.github.com/repos/example/public/commits/HEAD"
        return httpx.Response(status, json=payload)

    monkeypatch.setattr(
        github_client.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(respond), **kw),
    )
    if code:
        with pytest.raises(ApiError) as error:
            asyncio.run(github_client.head_sha("https://github.com/example/public", config))
        assert error.value.code == code
    else:
        assert (
            asyncio.run(github_client.head_sha("https://github.com/example/public", config))
            == "a" * 40
        )
