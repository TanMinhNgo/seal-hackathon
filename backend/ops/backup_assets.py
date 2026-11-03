"""Xuất file bài nộp thành ZIP mã hóa age, không ghi signed URL vào manifest."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import sync_session_factory
from app.integrations.storage import Storage
from app.modules.submissions.models import SubmissionFile


class ZipStream:
    # Pipe trên Windows có thể nhận seek/tell nhưng không backpatch được ZIP header.
    def __init__(self, stream: object) -> None:
        self.stream = stream

    def write(self, data: bytes) -> int:
        return self.stream.write(data)

    def flush(self) -> None:
        self.stream.flush()


def backup(output: Path, recipient: str) -> int:
    if output.exists():
        raise ValueError("Backup output must not already exist")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f"{output.name}.{uuid4().hex}.part")
    storage = Storage(get_settings())
    manifest = []
    process = subprocess.Popen(
        ["age", "-r", recipient, "-o", str(temporary)], stdin=subprocess.PIPE
    )
    try:
        with (
            sync_session_factory() as session,
            ZipFile(ZipStream(process.stdin), "w") as archive,
        ):
            rows = session.scalars(
                select(SubmissionFile).order_by(SubmissionFile.id).execution_options(yield_per=100)
            )
            manifest = storage.backup(rows, archive)
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("Asset backup encryption failed")
        temporary.rename(output)
        output.chmod(0o600)
        return len(manifest)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if temporary.exists():
            temporary.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--recipient", required=True)
    args = parser.parse_args()
    count = backup(args.output.resolve(), args.recipient)
    sys.stdout.write(json.dumps({"files": count, "status": "encrypted"}) + "\n")


if __name__ == "__main__":
    main()
