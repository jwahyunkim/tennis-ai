import asyncio
import hashlib
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class InvalidMedia(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


@dataclass(frozen=True)
class VideoMetadata:
    duration_seconds: float
    width: int
    height: int
    sha256: str


@dataclass(frozen=True)
class ReconstructionArtifact:
    """Self-contained GLB output from a future body reconstruction implementation."""

    path: Path
    model_version: str


class BodyReconstructor(Protocol):
    async def reconstruct(
        self, video_path: Path, output_directory: Path
    ) -> ReconstructionArtifact | None: ...


class UnconfiguredReconstructor:
    async def reconstruct(self, video_path: Path, output_directory: Path) -> None:
        return None


async def inspect_video(path: Path, max_seconds: float) -> VideoMetadata:
    # Restrict protocols and demuxers: uploaded media cannot fetch remote resources.
    process = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-protocol_whitelist",
        "file,pipe",
        "-format_whitelist",
        "mov",
        "-select_streams",
        "v:0",
        "-show_entries",
        "format=duration:stream=width,height,duration,codec_name",
        "-of",
        "json",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=20)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode != 0:
        raise InvalidMedia("invalid_video")
    try:
        data = json.loads(output)
        stream = data["streams"][0]
        duration = float(data.get("format", {}).get("duration") or stream["duration"])
        width, height = int(stream["width"]), int(stream["height"])
    except (ValueError, KeyError, IndexError, TypeError):
        raise InvalidMedia("invalid_video") from None
    if not math.isfinite(duration) or duration <= 0:
        raise InvalidMedia("invalid_video")
    if duration > max_seconds:
        raise InvalidMedia("video_too_long")
    if (
        min(width, height) < 16
        or max(width, height) > 4096
        or width * height > 3840 * 2160
    ):
        raise InvalidMedia("unsupported_resolution")

    def digest() -> str:
        with path.open("rb") as file:
            return hashlib.file_digest(file, "sha256").hexdigest()

    return VideoMetadata(duration, width, height, await asyncio.to_thread(digest))


async def validate_artifact(artifact: ReconstructionArtifact) -> None:
    if not artifact.model_version or len(artifact.model_version) > 100:
        raise InvalidMedia("invalid_model_artifact")

    def validate() -> None:
        size = artifact.path.stat().st_size
        if size < 20 or size > 50 * 1024**2:
            raise InvalidMedia("invalid_model_artifact")
        with artifact.path.open("rb") as source:
            magic, version, declared_size = struct.unpack("<4sII", source.read(12))
            chunk_size, chunk_type = struct.unpack("<I4s", source.read(8))
            if (
                magic != b"glTF"
                or version != 2
                or declared_size != size
                or chunk_type != b"JSON"
                or chunk_size > min(size - 20, 4 * 1024**2)
            ):
                raise InvalidMedia("invalid_model_artifact")
            try:
                document = json.loads(source.read(chunk_size))
            except (ValueError, UnicodeError):
                raise InvalidMedia("invalid_model_artifact") from None

        def external_resource(value) -> bool:
            if isinstance(value, dict):
                return "uri" in value or any(
                    external_resource(v) for v in value.values()
                )
            return isinstance(value, list) and any(external_resource(v) for v in value)

        if (
            not isinstance(document, dict)
            or external_resource(document)
            or not document.get("meshes")
            or not isinstance(document.get("asset"), dict)
            or document.get("asset", {}).get("version") != "2.0"
        ):
            raise InvalidMedia("invalid_model_artifact")

    await asyncio.to_thread(validate)
