import asyncio
import shutil
import threading

import pytest

from backend.core.storage import LocalMediaStorage, validate_key


@pytest.mark.parametrize(
    "key",
    [
        "",
        "../secret",
        "/etc/passwd",
        "videos/../../secret",
        "videos\\secret",
        "videos//x",
        "videos/./x",
        ".private/file",
    ],
)
def test_storage_rejects_path_traversal(key):
    with pytest.raises(ValueError):
        validate_key(key)


def test_local_storage_rejects_symlink_escape(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "videos").symlink_to(outside, target_is_directory=True)
    storage = LocalMediaStorage(root)
    with pytest.raises(ValueError):
        storage.path("videos/private.mp4")


async def test_local_storage_round_trip_and_idempotent_delete(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"test-media-bytes")
    storage = LocalMediaStorage(tmp_path / "media")
    key = "videos/account/video.mp4"
    await storage.put(key, source, "video/mp4")
    stored = await storage.download_location(key)
    assert stored.read_bytes() == source.read_bytes()
    assert stored.stat().st_mode & 0o777 == 0o600
    target = tmp_path / "download.mp4"
    await storage.copy_to(key, target)
    assert target.read_bytes() == source.read_bytes()
    await storage.delete(key)
    await storage.delete(key)
    with pytest.raises(FileNotFoundError):
        await storage.download_location(key)


async def test_delete_reclaims_only_its_own_crash_interrupted_copies(tmp_path):
    storage = LocalMediaStorage(tmp_path / "media")
    key = "videos/account/video[1].mp4"
    target = storage.path(key)
    target.parent.mkdir(parents=True)
    partial = target.with_name(".video[1].mp4.interrupted.tmp")
    unrelated = target.with_name(".video1.mp4.unrelated.tmp")
    directory = target.with_name(".video[1].mp4.directory.tmp")
    partial.write_bytes(b"partial-video")
    unrelated.write_bytes(b"another-video")
    directory.mkdir()

    # The final file need not exist when a process died during the first copy.
    await storage.delete(key)

    assert not partial.exists()
    assert unrelated.read_bytes() == b"another-video"
    assert directory.is_dir()


async def test_cancelled_local_put_finishes_io_before_caller_can_clean_source(
    tmp_path, monkeypatch
):
    storage = LocalMediaStorage(tmp_path / "media")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"original-media")
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    copyfile = shutil.copyfile

    def paused_copy(source_path, target_path):
        loop.call_soon_threadsafe(started.set)
        if not release.wait(5):
            raise TimeoutError("Test copy was not released")
        return copyfile(source_path, target_path)

    monkeypatch.setattr(shutil, "copyfile", paused_copy)
    task = asyncio.create_task(storage.put("videos/a.mp4", source, "video/mp4"))
    try:
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()  # A second cancellation must not detach the storage thread.
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)

    assert storage.path("videos/a.mp4").read_bytes() == b"original-media"
    assert not list(storage.path("videos/a.mp4").parent.glob(".*.tmp"))
