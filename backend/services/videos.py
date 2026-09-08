import asyncio
import logging
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from backend.core.config import Settings
from backend.core.errors import AppError
from backend.core.storage import InvalidByteRange, MediaStorage
from backend.models.video import ProcessingJob, Video
from backend.repositories.videos import VideoRepository
from backend.schemas.video import JobResponse, ModelResponse, VideoPage, VideoResponse

logger = logging.getLogger(__name__)


def video_response(row) -> VideoResponse:
    video, job, model = row
    result = VideoResponse.model_validate(video)
    return result.model_copy(
        update={
            "job": JobResponse.model_validate(job) if job else None,
            "model": ModelResponse(
                id=model.id,
                format=model.format,
                model_version=model.model_version,
                created_at=model.created_at,
                download_path=f"/api/v1/models/{model.id}/content",
            )
            if model
            else None,
        }
    )


class VideoService:
    def __init__(
        self, repository: VideoRepository, storage: MediaStorage, settings: Settings
    ) -> None:
        self.repository = repository
        self.session = repository.session
        self.storage = storage
        self.settings = settings

    async def list(self, user_id: UUID, limit: int, offset: int) -> VideoPage:
        rows, total = await self.repository.list(user_id, limit, offset)
        return VideoPage(
            items=[video_response(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get(self, user_id: UUID, video_id: UUID) -> VideoResponse:
        row = await self.repository.get(user_id, video_id)
        if row is None:
            raise AppError(404, "video_not_found", "영상을 찾을 수 없습니다.")
        return video_response(row)

    async def upload(self, user_id: UUID, upload) -> VideoResponse:
        filename = (upload.filename or "video.mp4").replace("\\", "/").split("/")[-1]
        filename = "".join(c for c in filename if c.isprintable())[:255]
        suffix = Path(filename).suffix.lower()
        if suffix not in {".mp4", ".mov"}:
            raise AppError(415, "unsupported_video", "MP4 또는 MOV 영상을 선택하세요.")
        content_type = "video/quicktime" if suffix == ".mov" else "video/mp4"
        video_id = uuid4()
        key = f"videos/{user_id}/{video_id}{suffix}"
        video = None
        with tempfile.TemporaryDirectory(prefix="tennis-upload-") as directory:
            source = Path(directory) / f"source{suffix}"
            size = 0
            handle = await asyncio.to_thread(source.open, "wb")
            try:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.settings.max_upload_bytes:
                        raise AppError(
                            413, "video_too_large", "영상 용량 제한을 초과했습니다."
                        )
                    if size == len(chunk) and (
                        len(chunk) < 12 or chunk[4:8] != b"ftyp"
                    ):
                        raise AppError(
                            415, "unsupported_video", "지원하는 영상 파일이 아닙니다."
                        )
                    await asyncio.to_thread(handle.write, chunk)
            finally:
                await asyncio.to_thread(handle.close)
            if not size:
                raise AppError(422, "empty_video", "빈 파일은 업로드할 수 없습니다.")
            used = await self.repository.reserve_capacity(user_id)
            if used + size > self.settings.max_user_storage_bytes:
                raise AppError(
                    409, "storage_quota_exceeded", "개인 저장 용량을 초과했습니다."
                )
            video = Video(
                id=video_id,
                user_id=user_id,
                filename=filename,
                content_type=content_type,
                storage_key=key,
                size_bytes=size,
                status="uploading",
            )
            self.session.add(video)
            # Persist the reservation before storage I/O so interrupted uploads
            # remain discoverable by worker maintenance instead of becoming orphans.
            await self.session.commit()
            try:
                await self.storage.put(key, source, content_type)
                video.status = "uploaded"
                self.session.add(ProcessingJob(video_id=video_id))
                await self.session.commit()
            except (Exception, asyncio.CancelledError):
                await self.session.rollback()
                # The uploading reservation is reclaimed by worker maintenance.
                raise
        return await self.get(user_id, video_id)

    async def delete(self, user_id: UUID, video_id: UUID) -> None:
        video = await self.repository.lock_owned(user_id, video_id)
        if video is None:
            raise AppError(404, "video_not_found", "영상을 찾을 수 없습니다.")
        video.deleted_at = datetime.now(timezone.utc)
        job = await self.repository.job_for_video(video_id)
        if job:
            job.status = "cancelled"
        await self.session.commit()
        try:
            await self.cleanup(video_id)
        except Exception:
            await self.session.rollback()
            logger.warning("media_cleanup_pending")

    async def cleanup(self, video_id: UUID) -> None:
        row = await self.repository.lock_deleted(video_id)
        if row is None:
            return
        video, model = row
        job = await self.repository.job_for_video(video_id)
        if (
            job
            and job.lease_expires_at
            and job.lease_expires_at > datetime.now(timezone.utc)
        ):
            # A cancelled worker may still be draining a storage transfer.
            await self.session.rollback()
            return
        await self.storage.delete(video.storage_key)
        if model:
            await self.storage.delete(model.storage_key)
        for pending in await self.repository.pending_artifacts(video_id):
            await self.storage.delete(pending.storage_key)
        await self.session.delete(video)
        await self.session.commit()

    async def retry(self, user_id: UUID, video_id: UUID) -> JobResponse:
        video = await self.repository.lock_owned(user_id, video_id)
        if video is None:
            raise AppError(404, "video_not_found", "영상을 찾을 수 없습니다.")
        job = await self.repository.job_for_video(video_id)
        if job is None:
            job = ProcessingJob(video_id=video_id)
            self.session.add(job)
        elif job.status in {"cancelled", "failed"}:
            if job.lease_expires_at and job.lease_expires_at > datetime.now(
                timezone.utc
            ):
                raise AppError(
                    409,
                    "job_stopping",
                    "이전 작업을 정리 중입니다. 잠시 후 다시 시도하세요.",
                )
            job.status = "queued"
            job.attempts = 0
            job.error_code = None
            job.claim_token = None
            job.available_at = datetime.now(timezone.utc)
            video.status = "uploaded"
        # Repeated requests return the same active/waiting job, preventing duplicates.
        await self.session.commit()
        await self.session.refresh(job)
        return JobResponse.model_validate(job)

    async def cancel(self, user_id: UUID, job_id: UUID) -> JobResponse:
        job = await self.repository.job_owned(user_id, job_id)
        if job is None:
            raise AppError(404, "job_not_found", "작업을 찾을 수 없습니다.")
        if job.status != "succeeded":
            job.status = "cancelled"
            job.error_code = None
        await self.session.commit()
        await self.session.refresh(job)
        return JobResponse.model_validate(job)

    async def content(
        self, user_id: UUID, video_id: UUID, byte_range: str | None = None
    ):
        row = await self.repository.get(user_id, video_id)
        if row is None:
            raise AppError(404, "video_not_found", "영상을 찾을 수 없습니다.")
        video = row[0]
        return await self._location(video.storage_key, byte_range), video.content_type

    async def model_content(
        self, user_id: UUID, model_id: UUID, byte_range: str | None = None
    ):
        model = await self.repository.model_owned(user_id, model_id)
        if model is None:
            raise AppError(404, "model_not_found", "3D 모델을 찾을 수 없습니다.")
        return await self._location(model.storage_key, byte_range), "model/gltf-binary"

    async def _location(self, key: str, byte_range: str | None = None):
        if (
            byte_range
            and re.fullmatch(r"bytes=(?:[0-9]+-[0-9]*|-[0-9]+)", byte_range) is None
        ):
            raise AppError(416, "invalid_range", "지원하지 않는 파일 범위입니다.")
        try:
            return await self.storage.download_location(key, byte_range)
        except InvalidByteRange:
            raise AppError(
                416, "invalid_range", "지원하지 않는 파일 범위입니다."
            ) from None
        except FileNotFoundError:
            raise AppError(404, "file_not_found", "파일을 찾을 수 없습니다.") from None
