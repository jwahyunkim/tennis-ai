"""Durable PostgreSQL jobs; run separately from the HTTP server."""

import argparse
import asyncio
import contextlib
import json
import logging
import signal
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.core.config import Settings
from backend.core.database import create_database_engine
from backend.core.storage import MediaStorage, create_storage
from backend.models.video import ArtifactUpload, BodyModel
from backend.repositories.accounts import AccountRepository
from backend.repositories.videos import VideoRepository
from backend.services.media import (
    BodyReconstructor,
    InvalidMedia,
    UnconfiguredReconstructor,
    inspect_video,
    validate_artifact,
)
from backend.services.videos import VideoService

logger = logging.getLogger("tennis.worker")


class Worker:
    def __init__(
        self,
        sessions: async_sessionmaker,
        storage: MediaStorage,
        settings: Settings,
        reconstructor: BodyReconstructor | None = None,
    ):
        self.sessions = sessions
        self.storage = storage
        self.settings = settings
        # Expensive model initialization belongs at worker startup in this adapter.
        self.reconstructor = reconstructor or UnconfiguredReconstructor()

    async def run_once(self) -> bool:
        async with self.sessions() as session:
            claimed = await VideoRepository(session).claim(
                self.settings.worker_lease_seconds, self.settings.worker_max_attempts
            )
            await session.commit()
            if claimed is None:
                return False
            job, video = claimed
        owner = asyncio.current_task()
        renewal = asyncio.create_task(self._renew_lease(job.id, job.claim_token, owner))
        try:
            return await self._process_claim(job, video)
        finally:
            renewal.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await renewal

    async def _renew_lease(self, job_id, token, owner) -> None:
        while True:
            await asyncio.sleep(30)
            try:
                async with self.sessions() as session:
                    renewed = await VideoRepository(session).renew_claim(
                        job_id, token, self.settings.worker_lease_seconds
                    )
                    await session.commit()
                if not renewed:
                    return
            except Exception:
                logger.error("worker_lease_renewal_failed")
                owner.cancel()
                return

    async def _process_claim(self, job, video) -> bool:
        job_id, token, video_id = job.id, job.claim_token, video.id
        source_key, user_id = video.storage_key, video.user_id
        logger.info(json.dumps({"event": "job_started", "job_id": str(job_id)}))
        stored_artifact = None
        artifact = None
        metadata = None
        error_code = None
        permanent = False
        directory = tempfile.TemporaryDirectory(prefix="tennis-worker-")
        try:
            async with asyncio.timeout(90):
                path = Path(directory.name)
                source = path / "source.mp4"
                await self.storage.copy_to(source_key, source)
                metadata = await inspect_video(source, self.settings.max_video_seconds)
                artifact = await self.reconstructor.reconstruct(source, path)
                if artifact:
                    await validate_artifact(artifact)
                    stored_artifact = f"models/{user_id}/{video_id}/{token}.glb"
                    async with self.sessions() as session:
                        current = await VideoRepository(session).lock_claim(
                            job_id, token
                        )
                        if current:
                            # A crash during storage publication leaves a durable
                            # key that maintenance can reclaim after the lease ends.
                            session.add(
                                ArtifactUpload(
                                    id=token,
                                    video_id=video_id,
                                    storage_key=stored_artifact,
                                )
                            )
                            await session.commit()
                        else:
                            stored_artifact = None
                    if stored_artifact:
                        await self.storage.put(
                            stored_artifact, artifact.path, "model/gltf-binary"
                        )
        except InvalidMedia as exc:
            error_code, permanent = exc.code, True
        except asyncio.CancelledError:
            # The committed lease enables another worker to recover after shutdown.
            raise
        except Exception:
            # Never log SDK errors or user filenames; they can contain private data.
            error_code = "processing_unavailable"
        finally:
            await asyncio.to_thread(directory.cleanup)

        accepted = False
        async with self.sessions() as session:
            row = await VideoRepository(session).lock_claim(job_id, token)
            if row:
                job, video = row
                job.claim_token = None
                job.lease_expires_at = None
                job.updated_at = datetime.now(timezone.utc)
                if error_code:
                    job.error_code = error_code
                    if permanent or job.attempts >= self.settings.worker_max_attempts:
                        job.status = "failed"
                        video.status = "failed"
                    else:
                        job.status = "queued"
                        job.available_at = datetime.now(timezone.utc) + timedelta(
                            seconds=2**job.attempts
                        )
                else:
                    video.duration_seconds = metadata.duration_seconds
                    video.width, video.height = metadata.width, metadata.height
                    video.sha256 = metadata.sha256
                    video.status = "ready"
                    job.status = "succeeded" if artifact else "awaiting_model"
                    job.error_code = None
                    if artifact:
                        session.add(
                            BodyModel(
                                video_id=video.id,
                                storage_key=stored_artifact,
                                model_version=artifact.model_version,
                            )
                        )
                        reservation = await session.get(ArtifactUpload, token)
                        if reservation:
                            await session.delete(reservation)
                        accepted = True
                await session.commit()
            else:
                await VideoRepository(session).release_cancelled_claim(job_id, token)
                await session.commit()
        if stored_artifact and not accepted:
            await self.storage.delete(stored_artifact)
            async with self.sessions() as session:
                reservation = await session.get(ArtifactUpload, token)
                if reservation:
                    await session.delete(reservation)
                    await session.commit()
        logger.info(
            json.dumps(
                {
                    "event": "job_finished",
                    "job_id": str(job_id),
                    "error_code": error_code,
                }
            )
        )
        return True

    async def maintenance(self) -> None:
        async with self.sessions() as session:
            repository = VideoRepository(session)
            candidates = await repository.cleanup_candidates()
            now = datetime.now(timezone.utc)
            await AccountRepository(session).prune_expired(
                now, now - timedelta(seconds=self.settings.auth_lockout_seconds)
            )
            await session.commit()
            try:
                for reservation in await repository.stale_artifacts():
                    await self.storage.delete(reservation.storage_key)
                    await session.delete(reservation)
                await session.commit()
            except Exception:
                await session.rollback()
                logger.warning("artifact_cleanup_pending")
            for video_id in candidates:
                try:
                    await VideoService(repository, self.storage, self.settings).cleanup(
                        video_id
                    )
                except Exception:
                    await session.rollback()
                    logger.warning("media_cleanup_pending")


async def heartbeat(path: Path) -> None:
    while True:
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_text, str(time.time()), encoding="ascii")
        await asyncio.sleep(5)


async def run(settings: Settings, once: bool = False) -> None:
    engine = create_database_engine(settings)
    beat = None
    try:
        storage = await create_storage(settings)
        worker = Worker(
            async_sessionmaker(engine, expire_on_commit=False), storage, settings
        )
        if once:
            await worker.maintenance()
            await worker.run_once()
            return
        beat = asyncio.create_task(heartbeat(settings.worker_heartbeat_path))
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        cycles = 0
        while not stop.is_set():
            try:
                if cycles % 30 == 0:
                    await worker.maintenance()
                await worker.run_once()
            except Exception:
                logger.error("worker_cycle_failed")
            cycles += 1
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), settings.worker_poll_seconds)
    finally:
        if beat:
            beat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await beat
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    if args.healthcheck:
        try:
            age = time.time() - float(settings.worker_heartbeat_path.read_text())
            raise SystemExit(0 if 0 <= age < 60 else 1)
        except (OSError, ValueError):
            raise SystemExit(1) from None
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run(settings, once=args.once))


if __name__ == "__main__":
    main()
