from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.account import User
from backend.models.video import ArtifactUpload, BodyModel, ProcessingJob, Video


class VideoRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _visible(self, user_id: UUID):
        return (
            select(Video, ProcessingJob, BodyModel)
            .outerjoin(ProcessingJob, ProcessingJob.video_id == Video.id)
            .outerjoin(BodyModel, BodyModel.video_id == Video.id)
            .where(
                Video.user_id == user_id,
                Video.deleted_at.is_(None),
                Video.status != "uploading",
            )
        )

    async def get(self, user_id: UUID, video_id: UUID):
        return (
            await self.session.execute(
                self._visible(user_id).where(Video.id == video_id)
            )
        ).first()

    async def list(self, user_id: UUID, limit: int, offset: int):
        rows = (
            await self.session.execute(
                self._visible(user_id)
                .order_by(Video.created_at.desc(), Video.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        total = await self.session.scalar(
            select(func.count()).select_from(self._visible(user_id).subquery())
        )
        return rows, total

    async def reserve_capacity(self, user_id: UUID) -> int:
        # Serialize quota reservations per account, including uploads in progress.
        await self.session.scalar(
            select(User.id).where(User.id == user_id).with_for_update()
        )
        return await self.session.scalar(
            select(func.coalesce(func.sum(Video.size_bytes), 0)).where(
                Video.user_id == user_id
            )
        )

    async def lock_owned(self, user_id: UUID, video_id: UUID) -> Video | None:
        return await self.session.scalar(
            select(Video)
            .where(
                Video.id == video_id,
                Video.user_id == user_id,
                Video.deleted_at.is_(None),
                Video.status != "uploading",
            )
            .with_for_update()
        )

    async def job_for_video(self, video_id: UUID) -> ProcessingJob | None:
        return await self.session.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.video_id == video_id)
            .with_for_update()
        )

    async def job_owned(self, user_id: UUID, job_id: UUID) -> ProcessingJob | None:
        return await self.session.scalar(
            select(ProcessingJob)
            .join(Video)
            .where(
                ProcessingJob.id == job_id,
                Video.user_id == user_id,
                Video.deleted_at.is_(None),
            )
            .with_for_update(of=ProcessingJob)
        )

    async def model_owned(self, user_id: UUID, model_id: UUID) -> BodyModel | None:
        return await self.session.scalar(
            select(BodyModel)
            .join(Video)
            .where(
                BodyModel.id == model_id,
                Video.user_id == user_id,
                Video.deleted_at.is_(None),
            )
        )

    async def claim(self, lease_seconds: int, max_attempts: int):
        now = datetime.now(timezone.utc)
        eligible = or_(
            and_(ProcessingJob.status == "queued", ProcessingJob.available_at <= now),
            and_(
                ProcessingJob.status == "processing",
                ProcessingJob.lease_expires_at < now,
            ),
        )
        # Always lock video before job, matching retries, deletion and completion.
        # SKIP LOCKED lets independent workers claim different videos safely.
        for _ in range(20):
            video = await self.session.scalar(
                select(Video)
                .join(ProcessingJob)
                .where(
                    Video.deleted_at.is_(None),
                    eligible,
                )
                .order_by(ProcessingJob.created_at)
                .limit(1)
                .with_for_update(skip_locked=True, of=Video)
            )
            if video is None:
                return None
            job = await self.job_for_video(video.id)
            if job.status not in {"queued", "processing"}:
                continue
            if job.status == "processing" and job.lease_expires_at >= now:
                continue
            if job.attempts >= max_attempts:
                job.status = "failed"
                job.error_code = "worker_interrupted"
                job.claim_token = None
                job.lease_expires_at = None
                video.status = "failed"
                await self.session.flush()
                continue
            job.status = "processing"
            job.attempts += 1
            job.claim_token = uuid4()
            job.lease_expires_at = now + timedelta(seconds=lease_seconds)
            job.updated_at = now
            job.error_code = None
            await self.session.flush()
            return job, video
        return None

    async def lock_claim(self, job_id: UUID, token: UUID):
        # Lock the video before its job, matching API retry/deletion lock order.
        video = await self.session.scalar(
            select(Video)
            .join(ProcessingJob)
            .where(ProcessingJob.id == job_id, Video.deleted_at.is_(None))
            .with_for_update(of=Video)
        )
        if video is None:
            return None
        job = await self.job_for_video(video.id)
        if job.status != "processing" or job.claim_token != token:
            return None
        return job, video

    async def cleanup_candidates(self) -> list[UUID]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        await self.session.execute(
            update(Video)
            .where(
                Video.status == "uploading",
                Video.created_at < cutoff,
                Video.deleted_at.is_(None),
            )
            .values(deleted_at=datetime.now(timezone.utc))
        )
        return list(
            (
                await self.session.scalars(
                    select(Video.id).where(Video.deleted_at.is_not(None)).limit(20)
                )
            ).all()
        )

    async def lock_deleted(self, video_id: UUID):
        video = await self.session.scalar(
            select(Video)
            .where(Video.id == video_id, Video.deleted_at.is_not(None))
            .with_for_update(skip_locked=True)
        )
        if video is None:
            return None
        model = await self.session.scalar(
            select(BodyModel).where(BodyModel.video_id == video_id)
        )
        return video, model

    async def pending_artifacts(self, video_id: UUID):
        return list(
            await self.session.scalars(
                select(ArtifactUpload).where(ArtifactUpload.video_id == video_id)
            )
        )

    async def stale_artifacts(self):
        now = datetime.now(timezone.utc)
        return list(
            await self.session.scalars(
                select(ArtifactUpload)
                .outerjoin(
                    ProcessingJob, ProcessingJob.video_id == ArtifactUpload.video_id
                )
                .where(
                    or_(
                        ProcessingJob.id.is_(None),
                        ProcessingJob.lease_expires_at.is_(None),
                        ProcessingJob.lease_expires_at < now,
                    )
                )
                .with_for_update(skip_locked=True, of=ArtifactUpload)
                .limit(20)
            )
        )

    async def renew_claim(self, job_id: UUID, token: UUID, seconds: int) -> bool:
        result = await self.session.execute(
            update(ProcessingJob)
            .where(
                ProcessingJob.id == job_id,
                ProcessingJob.claim_token == token,
                ProcessingJob.status.in_(["processing", "cancelled"]),
            )
            .values(
                lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=seconds)
            )
        )
        return result.rowcount == 1

    async def release_cancelled_claim(self, job_id: UUID, token: UUID) -> None:
        await self.session.execute(
            update(ProcessingJob)
            .where(
                ProcessingJob.id == job_id,
                ProcessingJob.claim_token == token,
                ProcessingJob.status == "cancelled",
            )
            .values(claim_token=None, lease_expires_at=None)
        )
