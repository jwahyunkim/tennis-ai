from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile

from backend.core.auth import get_current_user
from backend.core.dependencies import get_session
from backend.core.errors import AppError
from backend.core.storage import RemoteContent
from backend.models.account import User
from backend.repositories.videos import VideoRepository
from backend.schemas.video import JobResponse, VideoPage, VideoResponse
from backend.services.videos import VideoService

router = APIRouter(prefix="/api/v1", tags=["videos"])
CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_video_service(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> VideoService:
    return VideoService(
        VideoRepository(session), request.app.state.storage, request.app.state.settings
    )


Service = Annotated[VideoService, Depends(get_video_service)]


@router.get("/capabilities")
async def capabilities(request: Request):
    settings = request.app.state.settings
    return {
        "body_reconstruction": False,
        "max_upload_bytes": settings.max_upload_bytes,
        "max_video_seconds": settings.max_video_seconds,
        "accepted_extensions": [".mp4", ".mov"],
    }


@router.post(
    "/videos",
    response_model=VideoResponse,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {"file": {"type": "string", "format": "binary"}},
                    }
                }
            },
        }
    },
)
async def upload_video(request: Request, user: CurrentUser, service: Service):
    # Authenticate before multipart parsing, so anonymous callers cannot spool files.
    async with request.form(max_files=1, max_fields=0) as form:
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise AppError(422, "missing_video", "영상 파일을 선택하세요.")
        return await service.upload(user.id, file)


@router.get("/videos", response_model=VideoPage)
async def list_videos(
    user: CurrentUser,
    service: Service,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
):
    return await service.list(user.id, limit, offset)


@router.get("/videos/{video_id}", response_model=VideoResponse)
async def get_video(video_id: UUID, user: CurrentUser, service: Service):
    return await service.get(user.id, video_id)


@router.delete("/videos/{video_id}", status_code=204)
async def delete_video(video_id: UUID, user: CurrentUser, service: Service):
    await service.delete(user.id, video_id)


def media_response(location: Path | RemoteContent, content_type: str):
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if isinstance(location, Path):
        return FileResponse(location, media_type=content_type, headers=headers)
    headers["Accept-Ranges"] = "bytes"
    headers["Content-Length"] = str(location.size)
    if location.content_range:
        headers["Content-Range"] = location.content_range
    return StreamingResponse(
        location.chunks(),
        media_type=content_type,
        status_code=206 if location.content_range else 200,
        headers=headers,
        background=BackgroundTask(location.close),
    )


@router.get("/videos/{video_id}/content")
async def video_content(
    request: Request, video_id: UUID, user: CurrentUser, service: Service
):
    return media_response(
        *await service.content(user.id, video_id, request.headers.get("range"))
    )


@router.get("/models/{model_id}/content")
async def model_content(
    request: Request, model_id: UUID, user: CurrentUser, service: Service
):
    return media_response(
        *await service.model_content(user.id, model_id, request.headers.get("range"))
    )


@router.post("/videos/{video_id}/jobs", response_model=JobResponse, status_code=202)
async def retry_job(video_id: UUID, user: CurrentUser, service: Service):
    return await service.retry(user.id, video_id)


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: UUID, user: CurrentUser, service: Service):
    return await service.cancel(user.id, job_id)
