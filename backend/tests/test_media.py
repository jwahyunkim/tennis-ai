import hashlib
import json
import struct

import pytest

from backend.services.media import (
    InvalidMedia,
    ReconstructionArtifact,
    inspect_video,
    validate_artifact,
)


async def test_real_video_metadata_and_duration_limit(tmp_path, small_video_bytes):
    source = tmp_path / "video.mp4"
    source.write_bytes(small_video_bytes)
    metadata = await inspect_video(source, max_seconds=10)
    assert (metadata.width, metadata.height) == (64, 64)
    assert metadata.duration_seconds == pytest.approx(0.4)
    assert metadata.sha256 == hashlib.sha256(small_video_bytes).hexdigest()
    with pytest.raises(InvalidMedia) as error:
        await inspect_video(source, max_seconds=0.1)
    assert error.value.code == "video_too_long"


async def test_spoofed_mp4_header_is_rejected_by_ffprobe(tmp_path):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"\0\0\0\x18ftypmp42" + b"not-a-video" * 5)
    with pytest.raises(InvalidMedia) as error:
        await inspect_video(source, max_seconds=10)
    assert error.value.code == "invalid_video"


async def test_self_contained_glb_is_accepted(tmp_path, triangle_glb_bytes):
    path = tmp_path / "triangle.glb"
    path.write_bytes(triangle_glb_bytes)
    await validate_artifact(ReconstructionArtifact(path, "test-adapter-v1"))


@pytest.mark.parametrize(
    "document",
    [
        {
            "asset": {"version": "2.0"},
            "meshes": [{}],
            "buffers": [{"uri": "https://untrusted.example/model.bin"}],
        },
        {
            "asset": {"version": "2.0"},
            "meshes": [{}],
            "images": [{"uri": "../../private-image.png"}],
        },
        {"asset": "invalid-asset", "meshes": [{}]},
        {"asset": {"version": "2.0"}, "meshes": []},
    ],
)
async def test_unsafe_or_malformed_glb_is_rejected(tmp_path, document):
    encoded = json.dumps(document).encode()
    encoded += b" " * (-len(encoded) % 4)
    path = tmp_path / "unsafe.glb"
    path.write_bytes(
        struct.pack("<4sII", b"glTF", 2, 20 + len(encoded))
        + struct.pack("<I4s", len(encoded), b"JSON")
        + encoded
    )
    with pytest.raises(InvalidMedia) as error:
        await validate_artifact(ReconstructionArtifact(path, "test-adapter-v1"))
    assert error.value.code == "invalid_model_artifact"


async def test_truncated_glb_header_is_rejected(tmp_path):
    path = tmp_path / "truncated.glb"
    path.write_bytes(b"glTF")
    with pytest.raises(InvalidMedia):
        await validate_artifact(ReconstructionArtifact(path, "test-adapter-v1"))
