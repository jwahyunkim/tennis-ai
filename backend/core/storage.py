import asyncio
import contextlib
import contextvars
import functools
import os
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import uuid4

from backend.core.config import Settings


async def _complete_io(function, *args, cancel_cleanup=None, **kwargs):
    # Cancelling an executor await does not stop its thread. Drain it before the
    # caller removes a source/target directory or closes a streaming response.
    # Keep the executor Future directly: asyncio shutdown cancels child Tasks.
    future = asyncio.get_running_loop().run_in_executor(
        None,
        contextvars.copy_context().run,
        functools.partial(function, *args, **kwargs),
    )
    try:
        return await asyncio.shield(future)
    except asyncio.CancelledError:
        while not future.done():
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.shield(future)
        if not future.cancelled():
            try:
                result = future.result()
            except Exception:
                pass  # Preserve the cancellation after retrieving the I/O error.
            else:
                if cancel_cleanup is not None:
                    with contextlib.suppress(Exception):
                        await _complete_io(cancel_cleanup, result)
        raise


class InvalidByteRange(Exception):
    pass


@dataclass
class RemoteContent:
    body: object
    size: int
    content_range: str | None = None
    closed: bool = False

    async def close(self) -> None:
        if not self.closed:
            self.closed = True
            await _complete_io(self.body.close)

    async def chunks(self):
        try:
            while chunk := await _complete_io(self.body.read, 1024 * 1024):
                yield chunk
        finally:
            await self.close()


def validate_key(key: str) -> None:
    path = PurePosixPath(key)
    if (
        not key
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in key
        or any(part.startswith(".") for part in path.parts)
        or str(path) != key
    ):
        raise ValueError("Invalid storage key")


class MediaStorage(Protocol):
    async def put(self, key: str, source: Path, content_type: str) -> None: ...
    async def copy_to(self, key: str, target: Path) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def download_location(
        self, key: str, byte_range: str | None = None
    ) -> Path | RemoteContent: ...


class LocalMediaStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def path(self, key: str) -> Path:
        validate_key(key)
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return path

    async def put(self, key: str, source: Path, content_type: str) -> None:
        target = self.path(key)

        def write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporary = target.with_name(f".{target.name}.{uuid4()}.tmp")
            try:
                shutil.copyfile(source, temporary)
                temporary.chmod(0o600)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)

        await _complete_io(write)

    async def copy_to(self, key: str, target: Path) -> None:
        await _complete_io(shutil.copyfile, self.path(key), target)

    async def delete(self, key: str) -> None:
        target = self.path(key)

        def remove() -> None:
            target.unlink(missing_ok=True)
            if not target.parent.is_dir():
                return
            # Hard shutdowns can interrupt the atomic copy before os.replace.
            # Match this target literally, without treating key characters as globs.
            prefix = f".{target.name}."
            with os.scandir(target.parent) as entries:
                for entry in entries:
                    if (
                        entry.name.startswith(prefix)
                        and entry.name.endswith(".tmp")
                        and not entry.is_dir(follow_symlinks=False)
                    ):
                        Path(entry.path).unlink(missing_ok=True)

        await _complete_io(remove)

    async def download_location(self, key: str, byte_range: str | None = None) -> Path:
        path = self.path(key)
        if not await asyncio.to_thread(path.is_file):
            raise FileNotFoundError
        return path


class S3MediaStorage:
    def __init__(self, client, bucket: str) -> None:
        from boto3.s3.transfer import TransferConfig

        self.client = client
        self.bucket = bucket
        self.transfer_config = TransferConfig(
            max_concurrency=2,
            max_io_queue=4,
            io_chunksize=1024 * 1024,
            num_download_attempts=2,
            preferred_transfer_client="classic",
        )

    async def put(self, key: str, source: Path, content_type: str) -> None:
        validate_key(key)
        await _complete_io(
            self.client.upload_file,
            str(source),
            self.bucket,
            key,
            ExtraArgs={"ContentType": content_type},
            Config=self.transfer_config,
        )

    async def copy_to(self, key: str, target: Path) -> None:
        validate_key(key)
        await _complete_io(
            self.client.download_file,
            self.bucket,
            key,
            str(target),
            Config=self.transfer_config,
        )

    async def delete(self, key: str) -> None:
        validate_key(key)
        await _complete_io(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def download_location(
        self, key: str, byte_range: str | None = None
    ) -> RemoteContent:
        from botocore.exceptions import ClientError

        validate_key(key)
        arguments = {"Bucket": self.bucket, "Key": key}
        if byte_range:
            arguments["Range"] = byte_range
        try:
            result = await _complete_io(
                self.client.get_object,
                cancel_cleanup=lambda value: value["Body"].close(),
                **arguments,
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"NoSuchKey", "404"}:
                raise FileNotFoundError from None
            if code == "InvalidRange":
                raise InvalidByteRange from None
            raise
        return RemoteContent(
            result["Body"], result["ContentLength"], result.get("ContentRange")
        )


async def create_storage(settings: Settings) -> MediaStorage:
    if settings.storage_backend == "local":
        storage = LocalMediaStorage(settings.storage_local_path)
        await asyncio.to_thread(
            storage.root.mkdir, parents=True, exist_ok=True, mode=0o700
        )
        return storage
    if not settings.s3_bucket:
        raise ValueError("S3_BUCKET is required for S3 storage")

    # SDK credential discovery can perform I/O; keep it off the event loop.
    def make_s3():
        import boto3
        from botocore.config import Config

        return boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            config=Config(
                connect_timeout=5,
                read_timeout=30,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )

    return S3MediaStorage(await asyncio.to_thread(make_s3), settings.s3_bucket)
