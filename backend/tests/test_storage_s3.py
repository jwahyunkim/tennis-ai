import asyncio
import io
import threading
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.core.storage import InvalidByteRange, S3MediaStorage
from backend.routers.videos import media_response


def storage_with_body(data=b"video-bytes", content_range=None):
    stream = io.BytesIO(data)
    body = StreamingBody(stream, len(data))
    client = Mock()
    client.get_object.return_value = {"Body": body, "ContentLength": len(data)}
    if content_range:
        client.get_object.return_value["ContentRange"] = content_range
    return S3MediaStorage(client, "private-media"), stream


async def test_s3_get_object_preserves_range_and_closes_response_body():
    storage, stream = storage_with_body(b"video", "bytes 0-4/11")
    content = await storage.download_location("videos/a.mp4", "bytes=0-4")
    storage.client.get_object.assert_called_once_with(
        Bucket="private-media", Key="videos/a.mp4", Range="bytes=0-4"
    )
    assert content.size == 5
    assert content.content_range == "bytes 0-4/11"
    assert b"".join([chunk async for chunk in content.chunks()]) == b"video"
    assert stream.closed


async def test_s3_invalid_storage_key_never_calls_sdk():
    storage, stream = storage_with_body()
    with pytest.raises(ValueError):
        await storage.download_location("../secret")
    storage.client.get_object.assert_not_called()
    stream.close()


@pytest.mark.parametrize(
    "code,exception",
    [
        ("NoSuchKey", FileNotFoundError),
        ("404", FileNotFoundError),
        ("InvalidRange", InvalidByteRange),
    ],
)
async def test_s3_errors_are_translated_without_sdk_details(code, exception):
    client = Mock()
    client.get_object.side_effect = ClientError(
        {"Error": {"Code": code, "Message": "private-sdk-details"}}, "GetObject"
    )
    storage = S3MediaStorage(client, "private-media")
    with pytest.raises(exception) as error:
        await storage.download_location("videos/a.mp4")
    assert "private-sdk-details" not in str(error.value)


async def test_remote_stream_closes_on_interrupted_consumption():
    storage, stream = storage_with_body(b"x" * (1024 * 1024 + 1))
    content = await storage.download_location("videos/a.mp4")
    chunks = content.chunks()
    assert len(await anext(chunks)) == 1024 * 1024
    await chunks.aclose()
    assert stream.closed


async def test_remote_media_response_streams_without_redirect_or_credentials():
    storage, stream = storage_with_body(b"video", "bytes 0-4/11")
    app = FastAPI()

    @app.get("/media")
    async def download():
        return media_response(
            await storage.download_location("videos/a.mp4", "bytes=0-4"), "video/mp4"
        )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/media")
    assert response.status_code == 206
    assert response.content == b"video"
    assert response.headers["Content-Length"] == "5"
    assert response.headers["Content-Range"] == "bytes 0-4/11"
    assert response.headers["Accept-Ranges"] == "bytes"
    assert "Location" not in response.headers
    assert stream.closed


async def test_s3_managed_transfers_have_bounded_threads_and_buffering(tmp_path):
    storage = S3MediaStorage(Mock(), "private-media")
    path = tmp_path / "media.mp4"
    await storage.put("videos/a.mp4", path, "video/mp4")
    await storage.copy_to("videos/a.mp4", path)

    for call in (
        storage.client.upload_file.call_args,
        storage.client.download_file.call_args,
    ):
        config = call.kwargs["Config"]
        assert config.max_concurrency == 2
        assert config.max_io_queue == 4
        assert config.num_download_attempts == 2
        assert config.preferred_transfer_client == "classic"


async def test_cancelled_s3_get_closes_body_created_after_cancellation():
    storage, stream = storage_with_body()
    result = storage.client.get_object.return_value
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()

    def paused_get(**kwargs):
        loop.call_soon_threadsafe(started.set)
        if not release.wait(5):
            raise TimeoutError("Test S3 request was not released")
        return result

    storage.client.get_object.side_effect = paused_get
    task = asyncio.create_task(storage.download_location("videos/a.mp4"))
    try:
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert not stream.closed
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
    assert stream.closed
