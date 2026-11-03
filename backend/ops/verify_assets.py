"""Kiểm tra archive đã giải mã và phục hồi file vào thư mục cách ly mới."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from uuid import UUID
from zipfile import ZipFile


def restore(archive_path: Path, target: Path) -> int:
    target.mkdir(parents=True, exist_ok=False)
    with ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if len({row["id"] for row in manifest}) != len(manifest):
            raise ValueError("Duplicate file IDs")
        for row in manifest:
            identifier = str(UUID(row["id"]))
            if row["entry"] != f"files/{identifier}" or row["size"] < 0:
                raise ValueError("Invalid manifest")
            digest, size = hashlib.sha256(), 0
            with (
                archive.open(row["entry"]) as source,
                (target / identifier).open("xb") as destination,
            ):
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > row["size"]:
                        raise ValueError("Restored asset size mismatch")
                    digest.update(chunk)
                    destination.write(chunk)
            if size != row["size"] or digest.hexdigest() != row["sha256"]:
                raise ValueError("Restored asset checksum mismatch")
    return len(manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    sys.stdout.write(
        json.dumps({"verified_files": restore(args.archive, args.target), "status": "verified"})
        + "\n"
    )


if __name__ == "__main__":
    main()
