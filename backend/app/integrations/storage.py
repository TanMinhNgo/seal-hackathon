from pathlib import PurePosixPath
from tempfile import SpooledTemporaryFile
from time import time
from zipfile import BadZipFile, ZipFile

import cloudinary.api
import cloudinary.uploader
import cloudinary.utils
import httpx
from cloudinary.exceptions import Error, NotFound

from app.core.config import Settings
from app.core.errors import ApiError

MAX_SIZE = 100 * 1024 * 1024
TYPES = {
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".mp4": "video/mp4",
    ".zip": "application/zip",
}


def validate_metadata(filename: str, content_type: str, size: int) -> None:
    if size > MAX_SIZE:
        raise ApiError(422, "FILE_TOO_LARGE", "Maximum file size is 100 MB")
    if TYPES.get(PurePosixPath(filename).suffix.lower()) != content_type:
        raise ApiError(
            422, "FILE_TYPE_NOT_ALLOWED", "Extension and MIME must match an allowed type"
        )


class Storage:
    def __init__(self, settings: Settings) -> None:
        if not (
            settings.cloudinary_cloud_name
            and settings.cloudinary_api_key
            and settings.cloudinary_api_secret
        ):
            raise ApiError(503, "STORAGE_NOT_CONFIGURED", "Cloudinary is not configured")
        self.options = {
            "cloud_name": settings.cloudinary_cloud_name,
            "api_key": settings.cloudinary_api_key.get_secret_value(),
            "api_secret": settings.cloudinary_api_secret.get_secret_value(),
            "resource_type": "raw",
            "type": "authenticated",
            "timeout": 20,
        }

    def presign(self, key: str, content_type: str, size: int) -> tuple[str, dict[str, str]]:
        validate_metadata(key, content_type, size)
        # Cloudinary chấp nhận timestamp trong 1 giờ; lùi 50 phút để chỉ còn 10 phút.
        fields = {
            "public_id": key,
            "timestamp": str(int(time()) - 3000),
            "type": "authenticated",
            "overwrite": "false",
        }
        fields["signature"] = cloudinary.utils.api_sign_request(
            fields, self.options["api_secret"], algorithm="sha256"
        )
        fields["api_key"] = self.options["api_key"]
        return f"https://api.cloudinary.com/v1_1/{self.options['cloud_name']}/raw/upload", fields

    def download(self, key: str, filename: str) -> str:
        # Raw public_id bao gồm extension; không truyền format để tránh nối extension hai lần.
        return cloudinary.utils.private_download_url(
            key, None, attachment=True, expires_at=int(time()) + 300, **self.options
        )

    def seal(self, source: str, target: str, filename: str, content_type: str, size: int) -> None:
        validate_metadata(filename, content_type, size)
        try:
            asset = cloudinary.api.resource(source, **self.options)
            if (
                asset.get("public_id") != source
                or asset.get("bytes") != size
                or asset.get("type") != "authenticated"
                or asset.get("resource_type") != "raw"
            ):
                raise ApiError(422, "FILE_NOT_UPLOADED", "Uploaded asset does not match")
            # Chữ ký client chỉ cho ID tạm với overwrite=false, không cấp quyền ghi ID đã chốt.
            cloudinary.uploader.rename(source, target, overwrite=False, **self.options)
            with httpx.Client(timeout=20, follow_redirects=False) as client:
                with client.stream("GET", self.download(target, filename)) as response:
                    if response.status_code != 200:
                        raise ApiError(
                            503, "STORAGE_UNAVAILABLE", "Cannot read authenticated asset"
                        )
                    with SpooledTemporaryFile(max_size=1024 * 1024) as data:
                        length = 0
                        for chunk in response.iter_bytes(1024 * 1024):
                            length += len(chunk)
                            if length > size:
                                raise ApiError(
                                    422, "FILE_NOT_UPLOADED", "Uploaded size does not match"
                                )
                            data.write(chunk)
                        if length != size:
                            raise ApiError(422, "FILE_NOT_UPLOADED", "Uploaded size does not match")
                        data.seek(0)
                        signature = data.read(32)
                        suffix = PurePosixPath(filename).suffix.lower()
                        valid = (suffix == ".pdf" and signature.startswith(b"%PDF-")) or (
                            suffix == ".mp4" and len(signature) >= 12 and signature[4:8] == b"ftyp"
                        )
                        if suffix in {".zip", ".pptx"} and signature.startswith(
                            (b"PK\x03\x04", b"PK\x05\x06")
                        ):
                            data.seek(0)
                            try:
                                with ZipFile(data) as archive:
                                    valid = suffix == ".zip" or {
                                        "[Content_Types].xml",
                                        "ppt/presentation.xml",
                                    } <= set(archive.namelist())
                            except BadZipFile:
                                valid = False
                        if not valid:
                            raise ApiError(
                                422, "FILE_TYPE_NOT_ALLOWED", "File signature does not match"
                            )
        except NotFound:
            raise ApiError(422, "FILE_NOT_UPLOADED", "Uploaded asset not found") from None
        except (Error, httpx.HTTPError):
            raise ApiError(503, "STORAGE_UNAVAILABLE", "Cloudinary access failed") from None

    def delete_temporary(self, key: str) -> None:
        if not key.startswith("uploads/"):
            raise ValueError("Only temporary uploads may be deleted")
        self._destroy(key)

    def discard_unsubmitted(self, key: str) -> None:
        if not key.startswith("submissions/"):
            raise ValueError("Expected an unsubmitted asset ID")
        self._destroy(key)

    def _destroy(self, key: str) -> None:
        try:
            result = cloudinary.uploader.destroy(key, invalidate=True, **self.options)
            if result.get("result") not in {"ok", "not found"}:
                raise ApiError(503, "STORAGE_UNAVAILABLE", "Cloudinary cleanup failed")
        except Error:
            raise ApiError(503, "STORAGE_UNAVAILABLE", "Cloudinary cleanup failed") from None
