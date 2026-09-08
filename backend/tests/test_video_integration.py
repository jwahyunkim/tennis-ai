import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update

from backend.models.video import ArtifactUpload, BodyModel, ProcessingJob, Video
from backend.services.media import ReconstructionArtifact
from backend.worker import Worker

pytestmark = pytest.mark.integration


async def sign_in(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"video-{uuid4().hex}@example.com",
            "password": "integration-tennis-password",
            "display_name": "Player",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def upload(client, headers, data):
    response = await client.post(
        "/api/v1/videos",
        headers=headers,
        files={"file": ("swing.mp4", data, "video/mp4")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def worker(app, reconstructor=None):
    return Worker(
        app.state.session_factory,
        app.state.storage,
        app.state.settings,
        reconstructor=reconstructor,
    )


async def test_upload_metadata_range_download_and_awaiting_model(
    api_client, api_app, small_video_bytes
):
    headers = await sign_in(api_client)
    capabilities = (await api_client.get("/api/v1/capabilities")).json()
    assert capabilities["body_reconstruction"] is False
    empty = (await api_client.get("/api/v1/videos", headers=headers)).json()
    assert empty["items"] == [] and empty["total"] == 0
    video = await upload(api_client, headers, small_video_bytes)
    assert video["status"] == "uploaded"
    assert video["job"]["status"] == "queued"
    assert video["model"] is None
    assert video["size_bytes"] == len(small_video_bytes)

    assert await worker(api_app).run_once()
    assert not await worker(api_app).run_once()
    response = await api_client.get(f"/api/v1/videos/{video['id']}", headers=headers)
    result = response.json()
    assert result["status"] == "ready"
    assert result["job"]["status"] == "awaiting_model"
    assert result["job"]["attempts"] == 1
    assert result["model"] is None
    assert (result["width"], result["height"]) == (64, 64)
    assert result["duration_seconds"] == pytest.approx(0.4)
    page = (await api_client.get("/api/v1/videos?limit=1", headers=headers)).json()
    assert page["total"] == 1 and len(page["items"]) == 1

    path = f"/api/v1/videos/{video['id']}/content"
    response = await api_client.get(path, headers=headers)
    assert response.content == small_video_bytes
    assert response.headers["Content-Type"] == "video/mp4"
    response = await api_client.get(path, headers={**headers, "Range": "bytes=0-15"})
    assert response.status_code == 206
    assert response.content == small_video_bytes[:16]
    assert response.headers["Content-Range"] == f"bytes 0-15/{len(small_video_bytes)}"


async def test_cross_account_video_job_and_model_access_is_denied(
    api_client, api_app, small_video_bytes, triangle_glb_bytes
):
    owner = await sign_in(api_client)
    stranger = await sign_in(api_client)
    video = await upload(api_client, owner, small_video_bytes)
    assert (await api_client.get("/api/v1/videos", headers=stranger)).json()[
        "total"
    ] == 0
    operations = [
        ("GET", f"/api/v1/videos/{video['id']}"),
        ("GET", f"/api/v1/videos/{video['id']}/content"),
        ("DELETE", f"/api/v1/videos/{video['id']}"),
        ("POST", f"/api/v1/videos/{video['id']}/jobs"),
        ("POST", f"/api/v1/jobs/{video['job']['id']}/cancel"),
    ]
    for method, path in operations:
        response = await api_client.request(method, path, headers=stranger)
        assert response.status_code == 404

    await worker(api_app, TriangleReconstructor(triangle_glb_bytes)).run_once()
    result = (
        await api_client.get(f"/api/v1/videos/{video['id']}", headers=owner)
    ).json()
    model_path = result["model"]["download_path"]
    assert (await api_client.get(model_path, headers=stranger)).status_code == 404
    response = await api_client.get(model_path, headers=owner)
    assert response.status_code == 200
    assert response.content == triangle_glb_bytes
    assert response.headers["Content-Type"] == "model/gltf-binary"
    assert result["job"]["status"] == "succeeded"
    assert result["model"]["model_version"] == "test-triangle-v1"
    async with api_app.state.session_factory() as session:
        assert await session.scalar(select(ArtifactUpload)) is None


class TriangleReconstructor:
    def __init__(self, data):
        self.data = data

    async def reconstruct(self, video_path, output_directory):
        path = output_directory / "test-triangle.glb"
        path.write_bytes(self.data)
        return ReconstructionArtifact(path, "test-triangle-v1")


@pytest.mark.parametrize(
    "filename,data,status",
    [
        ("empty.mp4", b"", 422),
        ("bad.mp4", b"not-a-video" * 3, 415),
        ("bad.webm", b"\0\0\0\x18ftypmp42" + b"x" * 20, 415),
    ],
)
async def test_invalid_uploads_leave_no_records(api_client, filename, data, status):
    headers = await sign_in(api_client)
    response = await api_client.post(
        "/api/v1/videos",
        headers=headers,
        files={"file": (filename, data, "video/mp4")},
    )
    assert response.status_code == status
    assert (await api_client.get("/api/v1/videos", headers=headers)).json()[
        "total"
    ] == 0


async def test_unauthorized_and_missing_uploads(api_client, small_video_bytes):
    response = await api_client.post(
        "/api/v1/videos", files={"file": ("swing.mp4", small_video_bytes, "video/mp4")}
    )
    assert response.status_code == 401
    headers = await sign_in(api_client)
    response = await api_client.post("/api/v1/videos", headers=headers)
    assert response.status_code == 422


async def test_file_and_request_body_limits(api_client, api_app, small_video_bytes):
    headers = await sign_in(api_client)
    api_app.state.settings = api_app.state.settings.model_copy(
        update={"max_upload_bytes": 1024}
    )
    response = await api_client.post(
        "/api/v1/videos",
        headers=headers,
        files={"file": ("swing.mp4", small_video_bytes, "video/mp4")},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "video_too_large"
    response = await api_client.post(
        "/api/v1/auth/login",
        content=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": "70000"},
    )
    assert response.status_code == 413
    assert (await api_client.get("/api/v1/videos", headers=headers)).json()[
        "total"
    ] == 0


async def test_concurrent_uploads_cannot_exceed_account_quota(
    api_client, api_app, small_video_bytes
):
    headers = await sign_in(api_client)
    api_app.state.settings = api_app.state.settings.model_copy(
        update={"max_user_storage_bytes": len(small_video_bytes)}
    )
    responses = await asyncio.gather(
        *(
            api_client.post(
                "/api/v1/videos",
                headers=headers,
                files={"file": ("swing.mp4", small_video_bytes, "video/mp4")},
            )
            for _ in range(2)
        )
    )
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert (await api_client.get("/api/v1/videos", headers=headers)).json()[
        "total"
    ] == 1


async def test_cancel_and_retry_are_idempotent(api_client, api_app, small_video_bytes):
    headers = await sign_in(api_client)
    video = await upload(api_client, headers, small_video_bytes)
    job_id = video["job"]["id"]
    for _ in range(2):
        response = await api_client.post(
            f"/api/v1/jobs/{job_id}/cancel", headers=headers
        )
        assert response.json()["status"] == "cancelled"
    assert not await worker(api_app).run_once()
    for _ in range(2):
        response = await api_client.post(
            f"/api/v1/videos/{video['id']}/jobs", headers=headers
        )
        assert response.status_code == 202
        assert response.json()["status"] == "queued"
        assert response.json()["id"] == job_id
    assert await worker(api_app).run_once()
    result = (
        await api_client.get(f"/api/v1/videos/{video['id']}", headers=headers)
    ).json()
    assert result["job"]["status"] == "awaiting_model"


async def test_running_cancellation_fences_result_and_removes_artifact(
    api_client, api_app, small_video_bytes, triangle_glb_bytes
):
    headers = await sign_in(api_client)
    video = await upload(api_client, headers, small_video_bytes)
    started, release = asyncio.Event(), asyncio.Event()

    class PausedReconstructor(TriangleReconstructor):
        async def reconstruct(self, video_path, output_directory):
            started.set()
            await release.wait()
            return await super().reconstruct(video_path, output_directory)

    processing = asyncio.create_task(
        worker(api_app, PausedReconstructor(triangle_glb_bytes)).run_once()
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=10)
        response = await api_client.post(
            f"/api/v1/jobs/{video['job']['id']}/cancel", headers=headers
        )
        assert response.json()["status"] == "cancelled"
        response = await api_client.post(
            f"/api/v1/videos/{video['id']}/jobs", headers=headers
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "job_stopping"
    finally:
        release.set()
        await asyncio.wait_for(processing, timeout=10)
    result = (
        await api_client.get(f"/api/v1/videos/{video['id']}", headers=headers)
    ).json()
    assert result["job"]["status"] == "cancelled"
    assert result["model"] is None
    assert list(api_app.state.storage.root.glob("models/**/*.glb")) == []
    response = await api_client.post(
        f"/api/v1/videos/{video['id']}/jobs", headers=headers
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"


async def test_concurrent_workers_claim_a_job_once(
    api_client, api_app, small_video_bytes
):
    headers = await sign_in(api_client)
    video = await upload(api_client, headers, small_video_bytes)
    results = await asyncio.gather(
        worker(api_app).run_once(), worker(api_app).run_once()
    )
    assert sorted(results) == [False, True]
    result = (
        await api_client.get(f"/api/v1/videos/{video['id']}", headers=headers)
    ).json()
    assert result["job"]["attempts"] == 1


async def test_expired_claim_recovers_and_exhausted_claim_fails(
    api_client, api_app, small_video_bytes
):
    headers = await sign_in(api_client)
    recoverable = await upload(api_client, headers, small_video_bytes)
    exhausted = await upload(api_client, headers, small_video_bytes)
    async with api_app.state.session_factory() as session:
        for video, attempts in (
            (recoverable, 1),
            (exhausted, api_app.state.settings.worker_max_attempts),
        ):
            await session.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == UUID(video["job"]["id"]))
                .values(
                    status="processing",
                    attempts=attempts,
                    claim_token=uuid4(),
                    lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
                )
            )
        await session.commit()
    await worker(api_app).run_once()
    await worker(api_app).run_once()
    recovered = (
        await api_client.get(f"/api/v1/videos/{recoverable['id']}", headers=headers)
    ).json()
    assert recovered["job"]["status"] == "awaiting_model"
    assert recovered["job"]["attempts"] == 2
    failed = (
        await api_client.get(f"/api/v1/videos/{exhausted['id']}", headers=headers)
    ).json()
    assert failed["job"]["status"] == "failed"
    assert failed["job"]["error_code"] == "worker_interrupted"
    assert failed["status"] == "failed"


async def test_spoofed_container_fails_processing_without_a_model(api_client, api_app):
    headers = await sign_in(api_client)
    video = await upload(api_client, headers, b"\0\0\0\x18ftypmp42" + b"x" * 100)
    assert await worker(api_app).run_once()
    result = (
        await api_client.get(f"/api/v1/videos/{video['id']}", headers=headers)
    ).json()
    assert result["status"] == "failed"
    assert result["job"]["status"] == "failed"
    assert result["job"]["error_code"] == "invalid_video"
    assert result["model"] is None


async def test_tombstoned_delete_is_hidden_until_maintenance_cleans_files(
    api_client, api_app, small_video_bytes, triangle_glb_bytes, monkeypatch
):
    headers = await sign_in(api_client)
    video = await upload(api_client, headers, small_video_bytes)
    await worker(api_app, TriangleReconstructor(triangle_glb_bytes)).run_once()
    real_delete = api_app.state.storage.delete
    monkeypatch.setattr(api_app.state.storage, "delete", AsyncMock(side_effect=OSError))
    response = await api_client.delete(f"/api/v1/videos/{video['id']}", headers=headers)
    assert response.status_code == 204
    assert (
        await api_client.get(f"/api/v1/videos/{video['id']}", headers=headers)
    ).status_code == 404
    async with api_app.state.session_factory() as session:
        stored = await session.get(Video, UUID(video["id"]))
        assert stored.deleted_at is not None
    monkeypatch.setattr(api_app.state.storage, "delete", real_delete)
    await worker(api_app).maintenance()
    async with api_app.state.session_factory() as session:
        assert await session.get(Video, UUID(video["id"])) is None
        assert await session.scalar(select(BodyModel)) is None
        assert await session.scalar(select(ProcessingJob)) is None
    assert list(api_app.state.storage.root.rglob("*.mp4")) == []
    assert list(api_app.state.storage.root.rglob("*.glb")) == []


async def test_chunked_body_limit_without_content_length(api_client):
    async def oversized_body():
        yield b'{"email":"'
        yield b"a" * 65536
        yield b'","password":"irrelevant-password"}'

    response = await api_client.post(
        "/api/v1/auth/login",
        content=oversized_body(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


async def test_transient_worker_failure_waits_for_backoff_then_recovers(
    api_client, api_app, small_video_bytes
):
    class UnavailableReconstructor:
        async def reconstruct(self, video_path, output_directory):
            raise OSError("simulated model storage failure")

    headers = await sign_in(api_client)
    video = await upload(api_client, headers, small_video_bytes)
    assert await worker(api_app, UnavailableReconstructor()).run_once()
    result = (
        await api_client.get(f"/api/v1/videos/{video['id']}", headers=headers)
    ).json()
    assert result["job"]["status"] == "queued"
    assert result["job"]["error_code"] == "processing_unavailable"
    assert not await worker(api_app).run_once()
    async with api_app.state.session_factory() as session:
        await session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == UUID(video["job"]["id"]))
            .values(available_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()
    assert await worker(api_app).run_once()
    result = (
        await api_client.get(f"/api/v1/videos/{video['id']}", headers=headers)
    ).json()
    assert result["job"]["status"] == "awaiting_model"
    assert result["job"]["attempts"] == 2
    assert result["job"]["error_code"] is None


async def test_interrupted_upload_reservation_is_reclaimed(
    api_client, api_app, small_video_bytes, monkeypatch
):
    headers = await sign_in(api_client)
    real_put = api_app.state.storage.put
    monkeypatch.setattr(
        api_app.state.storage,
        "put",
        AsyncMock(side_effect=OSError("private-storage-error-details")),
    )
    response = await api_client.post(
        "/api/v1/videos",
        headers=headers,
        files={"file": ("swing.mp4", small_video_bytes, "video/mp4")},
    )
    assert response.status_code == 500
    assert "private-storage-error-details" not in response.text
    assert (await api_client.get("/api/v1/videos", headers=headers)).json()[
        "total"
    ] == 0
    async with api_app.state.session_factory() as session:
        reservation = await session.scalar(select(Video))
        assert reservation.status == "uploading"
        assert reservation.size_bytes == len(small_video_bytes)
        reservation.created_at = datetime.now(UTC) - timedelta(hours=2)
        await session.commit()
    monkeypatch.setattr(api_app.state.storage, "put", real_put)
    await worker(api_app).maintenance()
    async with api_app.state.session_factory() as session:
        assert await session.scalar(select(Video)) is None


async def test_delete_during_processing_waits_for_transfer_then_cleans(
    api_client, api_app, small_video_bytes, triangle_glb_bytes, monkeypatch
):
    headers = await sign_in(api_client)
    video = await upload(api_client, headers, small_video_bytes)
    started, release = asyncio.Event(), asyncio.Event()

    real_put = api_app.state.storage.put

    async def paused_put(key, source, content_type):
        if key.startswith("models/"):
            started.set()
            await release.wait()
        await real_put(key, source, content_type)

    monkeypatch.setattr(api_app.state.storage, "put", paused_put)
    active_worker = worker(api_app, TriangleReconstructor(triangle_glb_bytes))
    processing = asyncio.create_task(active_worker.run_once())
    try:
        await asyncio.wait_for(started.wait(), timeout=10)
        response = await api_client.delete(
            f"/api/v1/videos/{video['id']}", headers=headers
        )
        assert response.status_code == 204
        assert (
            await api_client.get(f"/api/v1/videos/{video['id']}", headers=headers)
        ).status_code == 404
        await active_worker.maintenance()
        async with api_app.state.session_factory() as session:
            tombstone = await session.get(Video, UUID(video["id"]))
            assert tombstone is not None
            assert tombstone.deleted_at is not None
            assert await session.scalar(select(ArtifactUpload)) is not None
    finally:
        release.set()
        await asyncio.wait_for(processing, timeout=10)
    await active_worker.maintenance()
    async with api_app.state.session_factory() as session:
        assert await session.get(Video, UUID(video["id"])) is None
        assert await session.scalar(select(BodyModel)) is None
    assert list(api_app.state.storage.root.rglob("*.mp4")) == []
    assert list(api_app.state.storage.root.rglob("*.glb")) == []


async def test_failed_artifact_upload_keeps_reservation_until_cleanup_succeeds(
    api_client, api_app, small_video_bytes, triangle_glb_bytes, monkeypatch
):
    headers = await sign_in(api_client)
    video = await upload(api_client, headers, small_video_bytes)
    real_put = api_app.state.storage.put
    real_delete = api_app.state.storage.delete

    async def failed_artifact_put(key, source, content_type):
        async with api_app.state.session_factory() as session:
            reservation = await session.scalar(
                select(ArtifactUpload).where(ArtifactUpload.storage_key == key)
            )
            assert reservation is not None
            assert reservation.video_id == UUID(video["id"])
        await real_put(key, source, content_type)
        raise OSError("simulated connection failure after object was stored")

    monkeypatch.setattr(api_app.state.storage, "put", failed_artifact_put)
    monkeypatch.setattr(api_app.state.storage, "delete", AsyncMock(side_effect=OSError))
    active_worker = worker(api_app, TriangleReconstructor(triangle_glb_bytes))
    # The outer worker loop handles a failed cleanup iteration; its next
    # maintenance pass must retain enough durable state to finish the cleanup.
    with pytest.raises(OSError):
        await active_worker.run_once()
    async with api_app.state.session_factory() as session:
        reservation = await session.scalar(select(ArtifactUpload))
        assert reservation is not None
        pending_key = reservation.storage_key
        assert api_app.state.storage.path(pending_key).is_file()
        assert await session.scalar(select(BodyModel)) is None
        job = await session.get(ProcessingJob, UUID(video["job"]["id"]))
        assert job.status == "queued"
        assert job.error_code == "processing_unavailable"
    monkeypatch.setattr(api_app.state.storage, "delete", real_delete)
    await active_worker.maintenance()
    assert not api_app.state.storage.path(pending_key).exists()
    async with api_app.state.session_factory() as session:
        assert await session.scalar(select(ArtifactUpload)) is None


async def test_artifact_sweeper_preserves_live_lease_then_reclaims_stale_object(
    api_client, api_app, small_video_bytes, triangle_glb_bytes, tmp_path
):
    headers = await sign_in(api_client)
    video = await upload(api_client, headers, small_video_bytes)
    token = uuid4()
    key = f"models/test-account/{video['id']}/{token}.glb"
    source = tmp_path / "pending.glb"
    source.write_bytes(triangle_glb_bytes)
    await api_app.state.storage.put(key, source, "model/gltf-binary")
    async with api_app.state.session_factory() as session:
        session.add(
            ArtifactUpload(
                id=token,
                video_id=UUID(video["id"]),
                storage_key=key,
                created_at=datetime.now(UTC) - timedelta(hours=2),
            )
        )
        job = await session.get(ProcessingJob, UUID(video["job"]["id"]))
        job.status = "processing"
        job.claim_token = token
        job.attempts = 1
        job.lease_expires_at = datetime.now(UTC) + timedelta(minutes=2)
        await session.commit()
    await worker(api_app).maintenance()
    assert api_app.state.storage.path(key).is_file()
    async with api_app.state.session_factory() as session:
        assert await session.get(ArtifactUpload, token) is not None
        job = await session.get(ProcessingJob, UUID(video["job"]["id"]))
        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    await worker(api_app).maintenance()
    assert not api_app.state.storage.path(key).exists()
    async with api_app.state.session_factory() as session:
        assert await session.get(ArtifactUpload, token) is None
