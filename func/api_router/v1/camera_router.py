from ast import List
import datetime
import os
import shutil
from tokenize import String
from typing import Annotated, Optional, List, Union
import uuid
from zipfile import Path
from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, File, Request
from PIL import Image
import io
import base64
from sqlalchemy import func
from sqlmodel import select, delete
from func.auth.v1.auth import get_current_user
from model.db_model import Alarm, CameraConfig, CameraConfigCreate, CameraConfigPublic, CameraConfigPublicWithTags, CameraConfigTagLink, CameraConfigUpdate, Tag, WorkerEvent, WorkerEventActionRequest, WorkerEventConfirmationLog, get_session, UserPublic, AlarmConfirmationLog
from model.db_model import AlarmConfirmationRequest
from sqlalchemy.ext.asyncio import AsyncSession
router = APIRouter(prefix="/v1/cameras",tags=["cameras"])
from pydantic import BaseModel

@router.patch("/worker-events/{worker_event_id}/decline")
async def decline_worker_event_by_id(
    *,
    session: AsyncSession = Depends(get_session),
    worker_event_id: int,
    request_data: WorkerEventActionRequest,
    request: Request
):
    """
    Decline worker event - Simplified without status field
    """
    try:
        worker_event = await session.get(WorkerEvent, worker_event_id)
        if not worker_event:
            raise HTTPException(status_code=404, detail="Worker event not found")

        # Update status to 2 (declined)
        worker_event.status = 2
        session.add(worker_event)

        # Create simplified log without status field
        new_log = WorkerEventConfirmationLog(
            worker_event_id=worker_event_id,
            action=request_data.action  # "NG"
            # Remove: status=request_data.status
        )
        session.add(new_log)

        await session.commit()
        await session.refresh(worker_event)
        await session.refresh(new_log)

        return {
            "message": "Worker event declined successfully", 
            "event": worker_event,
            "log": new_log
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    

@router.patch("/worker-events/{worker_event_id}/accept")
async def accept_worker_event_by_id(
    *,
    session: AsyncSession = Depends(get_session),
    worker_event_id: int,
    request_data: WorkerEventActionRequest,
    request: Request
):
    """
    Accept worker event - Simplified without status field
    """
    try:
        worker_event = await session.get(WorkerEvent, worker_event_id)
        if not worker_event:
            raise HTTPException(status_code=404, detail="Worker event not found")

        # Update status to 1 (accepted)
        worker_event.status = 1
        session.add(worker_event)
        
        # Create simplified log without status field
        new_log = WorkerEventConfirmationLog(
            worker_event_id=worker_event_id,
            action=request_data.action  # "OK"
            # Remove: status=request_data.status
        )
        session.add(new_log)

        await session.commit()
        await session.refresh(worker_event)
        await session.refresh(new_log)

        return {
            "message": "Worker event accepted successfully",
            "event": worker_event,
            "log": new_log
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/worker-events")
async def create_worker_event(
    *,
    camera_id: str = Form(...),
    error_detail: str = Form(...),
    img_error: Union[UploadFile, None, str] = File(None),
    video_error: Union[UploadFile, None, str] = File(None),
    ai_log_file: Union[UploadFile, None, str] = File(None),
    session: AsyncSession = Depends(get_session),
    # user: Annotated[UserPublic, Depends(get_current_user)],
):
    """
    API tạo WorkerEvent mới (giống như Alarm)
    """
    try:
        # 1. Lấy thông tin camera từ DB
        camera_query = select(CameraConfig).where(CameraConfig.id == int(camera_id))
        camera_result = await session.execute(camera_query)
        camera = camera_result.scalars().first()

        if not camera:
            raise HTTPException(status_code=404, detail=f"Camera with id {camera_id} not found")

        # 2. Tạo timestamp
        current_time = datetime.datetime.now()
        timestamp_str = current_time.strftime('%Y-%m-%d %H:%M:%S')

        # 3. Tạo thư mục lưu trữ
        date_folder = current_time.strftime('%Y-%m-%d')
        event_folder = f"static/worker-events/{date_folder}/camera_{camera_id}"
        os.makedirs(event_folder, exist_ok=True)

        event_uuid = str(uuid.uuid4())

        # --- xử lý file ảnh (nếu có) ---
        img_relative_path = None
        if img_error and img_error.filename:
            img_filename = f"{event_uuid}_error_image.png"
            img_path = os.path.join(event_folder, img_filename)

            img_contents = await img_error.read()
            image = Image.open(io.BytesIO(img_contents))
            image.save(img_path, format="PNG", quality=80)

            img_relative_path = f"static/worker-events/{date_folder}/camera_{camera_id}/{img_filename}"

        # --- xử lý video (nếu có) ---
        video_relative_path = None
        if video_error and video_error.filename:
            video_ext = os.path.splitext(video_error.filename)[1] or ".mp4"
            video_filename = f"{event_uuid}_error_video{video_ext}"
            video_path = os.path.join(event_folder, video_filename)
            with open(video_path, "wb") as buffer:
                shutil.copyfileobj(video_error.file, buffer)
            video_relative_path = f"static/worker-events/{date_folder}/camera_{camera_id}/{video_filename}"

        # --- xử lý log file (nếu có) ---
        ai_log_relative_path = None
        if ai_log_file and ai_log_file.filename:
            log_filename = f"{event_uuid}_ai_log.txt"
            log_path = os.path.join(event_folder, log_filename)
            log_contents = await ai_log_file.read()
            with open(log_path, "wb") as buffer:
                buffer.write(log_contents)
            ai_log_relative_path = f"static/worker-events/{date_folder}/camera_{camera_id}/{log_filename}"

        # 4. Lưu record vào DB
        new_event = WorkerEvent(
            camera_id=camera_id,
            error_detail=error_detail,
            img_error=img_relative_path,
            video_error=video_relative_path,
            ai_log_path=ai_log_relative_path,
            location=camera.location,
            camera_name=camera.name,
            timestamp=timestamp_str,
            is_confirmed=False
        )
        session.add(new_event)
        await session.commit()
        await session.refresh(new_event)

        # 5. Response
        return {
            "success": True,
            "event": {
                "id": new_event.id,
                "uuid": event_uuid,
                "camera_id": new_event.camera_id,
                "camera_name": camera.name,
                "location": camera.location,
                "error_detail": new_event.error_detail,
                "timestamp": new_event.timestamp,
            },
            "files": {
                "image_url": f"/{img_relative_path}" if img_relative_path else None,
                "video_url": f"/{video_relative_path}" if video_relative_path else None,
                "ai_log_url": f"/{ai_log_relative_path}" if ai_log_relative_path else None,
            }
        }

    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    

@router.get("/worker-events")
async def get_worker_events(
    session: AsyncSession = Depends(get_session),
    query: Optional[str] = Query(default=None, description="search by camera_id or camera_name"),
    status: Optional[int] = Query(default=None, description="filter by status (0=Pending, 1=OK, 2=NG)"),
    event_id: Optional[str] = Query(default=None, description="partial match by event ID (as string)"),
    error_code: Optional[str] = Query(default=None, description="partial match by error_detail"),
    location: Optional[str] = Query(default=None, description="partial match by location"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=30, le=100),
    sort_by: str = Query(default="id", description="sort by field (id, timestamp, camera_name, location, error_detail, status)"),
    # order: str = Query(default="desc", regex="^(asc|desc)$"),
    order: str = Query(default="desc", regex="^(asc|desc)$"),
    start_time: Optional[int] = Query(default=None),
    end_time: Optional[int] = Query(default=None),
):
    try:
        stmt = select(WorkerEvent)

        # Apply filters
        if query:
            stmt = stmt.where(
                (WorkerEvent.camera_id.ilike(f"%{query}%")) |
                (WorkerEvent.camera_name.ilike(f"%{query}%"))
            )
        if status is not None:
            stmt = stmt.where(WorkerEvent.status == status)
        if event_id:
            stmt = stmt.where(func.cast(WorkerEvent.id, String).ilike(f"%{event_id}%"))
        if error_code:
            stmt = stmt.where(WorkerEvent.error_detail.ilike(f"%{error_code}%"))
        if location:
            stmt = stmt.where(WorkerEvent.location.ilike(f"%{location}%"))
        if start_time:
            stmt = stmt.where(
                WorkerEvent.timestamp >= datetime.datetime.fromtimestamp(start_time)
            )
        if end_time:
            stmt = stmt.where(
                WorkerEvent.timestamp <= datetime.datetime.fromtimestamp(end_time)
            )

        # Count total (apply same filters)
        count_subquery = stmt.subquery()
        count_stmt = select(func.count()).select_from(count_subquery)
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Apply sorting
        valid_sort_fields = ['id', 'timestamp', 'camera_name', 'location', 'error_detail', 'status']
        actual_sort_by = sort_by if sort_by in valid_sort_fields else 'id'
        if order == 'desc':
            stmt = stmt.order_by(getattr(WorkerEvent, actual_sort_by).desc())
        else:
            stmt = stmt.order_by(getattr(WorkerEvent, actual_sort_by))

        # Pagination
        stmt = stmt.offset((page - 1) * size).limit(size)
        result = await session.execute(stmt)
        events = result.scalars().all()

        total_pages = (total // size) + (1 if total % size else 0)

        return {
            "total": total,
            "current": page,
            "size": size,
            "page": total_pages,
            "data": [e.dict() for e in events]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching worker_events: {str(e)}")
    
    

@router.post("/alarms")
async def create_alarm(
    camera_id: str = Form(...),
    error_detail: str = Form(...),
    img_error: Union[UploadFile, None, str] = File(None),
    video_error: Union[UploadFile, None, str] = File(None),
    ai_log_file: Union[UploadFile, None, str] = File(None),
    session: AsyncSession = Depends(get_session),
):
    """
    API tạo Alarm mới với đầy đủ thông tin và files
    """
    try:
        # 1. Lấy thông tin camera từ database
        camera_query = select(CameraConfig).where(CameraConfig.id == int(camera_id))
        camera_result = await session.execute(camera_query)
        camera = camera_result.scalars().first()
        
        if not camera:
            raise HTTPException(status_code=404, detail=f"Camera with id {camera_id} not found")
        
        # 2. Tạo timestamp hiện tại
        current_time = datetime.datetime.now()
        timestamp_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
        
        # 3. Tạo thư mục lưu trữ theo cấu trúc: static/alarms/YYYY-MM-DD/camera_id/
        date_folder = current_time.strftime('%Y-%m-%d')
        alarm_folder = f"static/alarms/{date_folder}/camera_{camera_id}"
        os.makedirs(alarm_folder, exist_ok=True)

        # 4. Tạo unique ID cho alarm này
        alarm_uuid = str(uuid.uuid4())
        
        # 5. Xử lý file ảnh
        img_relative_path = None
        if img_error and img_error.filename:
            img_filename = f"{alarm_uuid}_error_image.png"
            img_path = os.path.join(alarm_folder, img_filename)
            
            img_contents = await img_error.read()
            image = Image.open(io.BytesIO(img_contents))
            image.save(img_path, format="PNG")
            img_relative_path = f"static/alarms/{date_folder}/camera_{camera_id}/{img_filename}"
        
        # 6. Xử lý video file
        video_relative_path = None
        if video_error and video_error.filename:
            video_ext = os.path.splitext(video_error.filename)[1] or ".mp4"
            video_filename = f"{alarm_uuid}_error_video{video_ext}"
            video_path = os.path.join(alarm_folder, video_filename)
            
            with open(video_path, "wb") as buffer:
                shutil.copyfileobj(video_error.file, buffer)

            video_relative_path = f"static/alarms/{date_folder}/camera_{camera_id}/{video_filename}"
        
        # 7. Xử lý AI log file
        ai_log_relative_path = None
        if ai_log_file and ai_log_file.filename:
            log_filename = f"{alarm_uuid}_ai_prediction_log.txt"
            log_path = os.path.join(alarm_folder, log_filename)
            
            log_contents = await ai_log_file.read()
            with open(log_path, "wb") as buffer:
                buffer.write(log_contents)
            
            ai_log_relative_path = f"static/alarms/{date_folder}/camera_{camera_id}/{log_filename}"
        
        # 8. Tạo metadata file
        metadata = {
            "alarm_id": alarm_uuid,
            "camera_info": {
                "camera_id": camera_id,
                "name": camera.name,
                "location": camera.location,
            },
            "error_detail": error_detail,
            "timestamp": timestamp_str,
            "files": {
                "image": img_relative_path,
                "video": video_relative_path,
                "ai_log": ai_log_relative_path
            },
            "created_at": current_time.isoformat()
        }
        
        metadata_path = os.path.join(alarm_folder, f"{alarm_uuid}_metadata.json")
        import json
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        metadata_relative_path = f"static/alarms/{date_folder}/camera_{camera_id}/{alarm_uuid}_metadata.json"
        
        # 9. Lưu record vào database (full info)
        new_alarm = Alarm(
            camera_id=camera_id,
            error_detail=error_detail,
            img_error=img_relative_path,
            video_error=video_relative_path,
            ai_log_path=ai_log_relative_path,   # ✅ đúng tên field
            location=camera.location,
            timestamp=timestamp_str,
            metadata_path=metadata_relative_path,
            camera_name=camera.name,            # ✅ thêm camera_name
            alarm_uuid=alarm_uuid,
            is_confirmed=False
        )

        session.add(new_alarm)
        await session.commit()
        await session.refresh(new_alarm)

        # 10. Response trả về đầy đủ thông tin
        return {
            "success": True,
            "alarm": {
                "id": new_alarm.id,
                "alarm_uuid": alarm_uuid,
                "camera_id": new_alarm.camera_id,
                "camera_name": camera.name,
                "location": camera.location,
                "error_detail": new_alarm.error_detail,
                "timestamp": new_alarm.timestamp,
            },
            "files": {
                "image_url": f"/{img_relative_path}" if img_relative_path else None,
                "video_url": f"/{video_relative_path}" if video_relative_path else None,
                "ai_log_url": f"/{ai_log_relative_path}" if ai_log_relative_path else None,
                "metadata_url": f"/{metadata_relative_path}"
            },
            "storage_path": str(alarm_folder)
        }

    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating alarm: {str(e)}")



@router.get("/cameras/{camera_config_id}")
async def get_camera_by_id(
    camera_config_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    API lấy thông tin camera theo ID (để FE có thể lấy name, location)
    """
    try:
        query = select(CameraConfig).where(CameraConfig.id == camera_config_id)
        result = await session.execute(query)
        camera = result.scalars().first()
        
        if not camera:
            raise HTTPException(status_code=404, detail="Camera not found")
            
        return {
            "id": camera.id,
            "name": camera.name,
            "location": camera.location,
            "preview_image_url": camera.preview_image_url,
            "webrtc_ip": camera.webrtc_ip,
            "webrtc_ip_low": camera.webrtc_ip_low,
            "panorama": camera.panorama,
            "statistic_api_url": camera.statistic_api_url,
            "eventlog_api_url": camera.eventlog_api_url,
            "fallback_video_url": camera.fallback_video_url,
            "isGate": camera.isGate,
            "gate_disable_alarm_url": camera.gate_disable_alarm_url,
            "tags": [{"id": tag.id, "tag_name": tag.tag_name} for tag in camera.tags]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alarms/{alarm_id}/files")
async def get_alarm_files(
    alarm_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    API lấy danh sách files của một alarm
    """
    try:
        alarm = await session.get(Alarm, alarm_id)
        if not alarm:
            raise HTTPException(status_code=404, detail="Alarm not found")
        
        # Đọc metadata nếu có
        if hasattr(alarm, 'metadata_path') and alarm.metadata_path:
            metadata_full_path = Path(alarm.metadata_path)
            if metadata_full_path.exists():
                import json
                with open(metadata_full_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                return metadata
        
        # Fallback: return basic info
        return {
            "alarm_id": alarm.id,
            "files": {
                "image": f"/{alarm.img_error}" if alarm.img_error else None,
                "video": None,
                "ai_log": None
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
# Thay thế endpoint cũ bằng endpoint mới này
@router.get("/alarms/unconfirmed", response_model=List[Alarm])
async def get_unconfirmed_alarms(
    *,
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=100, le=100),
):
    """Lấy danh sách tất cả các cảnh báo chưa được xác nhận."""
    try:
        query = select(Alarm).where(
            Alarm.is_confirmed == False
        ).order_by(
            Alarm.timestamp.desc()
        ).limit(limit)
        
        result = await session.execute(query)
        alarms = result.scalars().all()
        
        return alarms
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Có thể giữ lại endpoint cũ cho compatibility (optional)
@router.get("/alarms/latest", response_model=Optional[Alarm])
async def get_latest_alarm_and_status(
    *,
    session: AsyncSession = Depends(get_session),
):
    """
    [DEPRECATED] Sử dụng /alarms/unconfirmed thay thế.
    Lấy cảnh báo mới nhất chưa được xác nhận.
    """
    try:
        query = select(Alarm).where(
            Alarm.is_confirmed == False
        ).order_by(
            Alarm.timestamp.desc()
        ).limit(1)
        
        result = await session.execute(query)
        alarm = result.scalars().first()
        return alarm
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    
    
from pydantic import BaseModel
import datetime
from model.db_model import Alarm, AlarmConfirmationLog # Import model mới

# Định nghĩa Pydantic model cho request body
class AlarmConfirmationRequest(BaseModel):
    employee_confirm_id: str
    client_ip: Optional[str] = None # Cho phép IP null vì có thể không lấy được

@router.patch("/alarms/{alarm_id}/confirm")
async def confirm_alarm_by_id(
    *,
    session: AsyncSession = Depends(get_session),
    alarm_id: int,
    request_data: AlarmConfirmationRequest, # Thêm request body vào đây
    request: Request # Thêm tham số Request vào đây

):
    """
    Xác nhận một cảnh báo dựa trên ID của nó và tạo log.
    """
    try:
        alarm = await session.get(Alarm, alarm_id)
        if not alarm:
            raise HTTPException(status_code=404, detail="Alarm not found")
        
        # Cập nhật trạng thái của alarm
        alarm.is_confirmed = True
        session.add(alarm)

        # Lấy IP từ request headers (cách tốt hơn)
        # client_ip = request_data.client_ip or "Unknown" # Sử dụng IP gửi từ FE
        # Có thể dùng request.client.host nếu bạn muốn lấy IP từ backend thay vì FE
        
        # Lấy IP thực tế từ request của FastAPI
        client_ip = request.client.host
        
        # Tạo bản ghi log mới
        new_log = AlarmConfirmationLog(
            alarm_id=alarm_id,
            employee_confirm_id=request_data.employee_confirm_id,
            client_ip=client_ip,
            # logged_at sẽ được tạo tự động
        )
        session.add(new_log)

        await session.commit()
        await session.refresh(alarm)
        await session.refresh(new_log)

        return {
            "message": "Alarm confirmed and logged successfully", 
            "alarm": alarm,
            "log": new_log
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    
    
@router.get("/alarms", response_model=list[Alarm])
async def get_alarms(
    *,
    session: AsyncSession = Depends(get_session),
    offset: int = 0,
    limit: int = Query(default=100, le=100),
    camera_id: Optional[str] = Query(default=None),
):
    """
    Lấy danh sách cảnh báo, có thể lọc theo camera_id.
    """
    try:
        query = select(Alarm)
        if camera_id:
            query = query.where(Alarm.camera_id == camera_id)
        alarms = await session.execute(query.order_by(Alarm.id.asc()).offset(offset).limit(limit))
        alarms = alarms.scalars().all()
        return alarms
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=CameraConfigPublicWithTags)
async def create_camera_config(
    *, session: AsyncSession = Depends(get_session), user: Annotated[UserPublic, Depends(get_current_user)],camera_config: CameraConfigCreate
):
    """
    Create a new camera configuration and link it with specified tags.

    Parameters:
    - session: Database session dependency.
    - camera_config: CameraConfigCreate object containing the camera details and tag_ids.

    Returns:
    - A CameraConfigPublicWithTags object representing the created camera configuration with linked tags.

    Raises:
    - HTTPException: If any tag ID does not exist.
    """

    # Validate if all tag_ids exist
    if not hasattr(user, 'config') or not user.config:
        raise HTTPException(status_code=403, detail="Forbidden")
    existing_tags = await session.execute(select(Tag).where(Tag.id.in_(camera_config.tag_ids)))
    existing_tags = existing_tags.scalars().all()
    if len(existing_tags) != len(camera_config.tag_ids):
        raise HTTPException(status_code=400, detail="One or more tag IDs are invalid")

    # Create new camera config
    db_camera_config = CameraConfig(
        name=camera_config.name,
        location=camera_config.location,
        preview_image_url=camera_config.preview_image_url,
        webrtc_ip=camera_config.webrtc_ip,
        webrtc_ip_low=camera_config.webrtc_ip_low,  # Thêm xử lý trường mới
        panorama=camera_config.panorama,
        statistic_api_url=camera_config.statistic_api_url,
        eventlog_api_url=camera_config.eventlog_api_url,
        fallback_video_url=camera_config.fallback_video_url,
    )
    
    session.add(db_camera_config)
    await session.commit()
    await session.refresh(db_camera_config)

    # Link with tags
    for tag in existing_tags:
        session.add(CameraConfigTagLink(camera_config_id=db_camera_config.id, tag_id=tag.id))

    await session.commit()
    await session.refresh(db_camera_config)

    return db_camera_config

# @router.get("/", response_model=list[CameraConfigPublicWithTags])
# def read_camera_configs(*, session: Session = Depends(get_session), offset: int = 0, limit: int = Query(default=100, le=100), user: Annotated[str, Depends(get_current_user)], tag_ids: list[int] = Query(default=None)):
#     for item in tag_ids:
#         print(item)
#     if not hasattr(user, 'username') or user.username != "admin":
#     # if user != "admin":
#         raise HTTPException(status_code=400, detail="Not authorized")
#     camera_configs = session.exec(select(CameraConfig).offset(offset).limit(limit)).all()
#     return camera_configs


@router.get("/", response_model=list[CameraConfigPublicWithTags])
async def read_camera_configs(
    *,
    session: AsyncSession = Depends(get_session),
    offset: int = 0,
    limit: int = Query(default=100, le=100),
    user: Annotated[UserPublic, Depends(get_current_user)],
    tag_ids: list[int] = Query(default=None),
    name: Optional[str] = Query(default=None),
    location: Optional[str] = Query(default=None),
    panorama: Optional[int] = Query(default=None),
):
    """
    Retrieve a list of camera configurations with associated tags.

    This endpoint allows an admin user to fetch camera configurations, optionally filtered
    by a list of tag IDs, name, location, and panorama value. The response includes camera 
    configurations and their related tags.

    Parameters:
    - session: Database session dependency.
    - offset (int): Pagination offset for the query. Default is 0.
    - limit (int): Maximum number of results to return. Default is 100, with a maximum of 100.
    - user (str): The current authenticated user. Must be an admin to access this endpoint.
    - tag_ids (list[int], optional): A list of tag IDs to filter the camera configurations by.
    - name (str, optional): Partial match filter for the camera configuration name.
    - location (str, optional): Partial match filter for the camera configuration location.
    - panorama (int, optional): Exact match filter for the panorama field.

    Returns:
    - A list of CameraConfigPublicWithTags objects representing camera configurations 
      and their associated tags.

    Raises:
    - HTTPException: If the user is not authorized or if there are any issues with the query.
    """

    # if not hasattr(user, 'config') or not user.config:
    #     raise HTTPException(status_code=403, detail="Forbidden")
    
    query = select(CameraConfig)
    
    if tag_ids:
        for tag_id in tag_ids:
            query = query.where(
                CameraConfig.id.in_(
                    select(CameraConfigTagLink.camera_config_id)
                    .where(CameraConfigTagLink.tag_id == tag_id)
                )
            )
    
    if name:
        query = query.where(CameraConfig.name.contains(name))
    
    if location:
        query = query.where(CameraConfig.location.contains(location))
    
    if panorama is not None:
        query = query.where(CameraConfig.panorama == panorama)
    
    camera_configs = await session.execute(query.order_by(CameraConfig.id.asc()).offset(offset).limit(limit))
    camera_configs = camera_configs.scalars().all()
    return camera_configs




@router.get("/{camera_config_id}", response_model=CameraConfigPublicWithTags)
async def read_camera_config(*, session: AsyncSession = Depends(get_session), user: Annotated[UserPublic, Depends(get_current_user)], camera_config_id: int):
    camera_config = await session.get(CameraConfig, camera_config_id)
    if not camera_config:
        raise HTTPException(status_code=404, detail="CameraConfig not found")
    return camera_config


@router.patch("/{camera_config_id}", response_model=CameraConfigPublic)
async def update_camera_config(*, user: Annotated[UserPublic, Depends(get_current_user)], session: AsyncSession = Depends(get_session), camera_config_id: int, camera_config: CameraConfigUpdate):
    if not hasattr(user, 'config') or not user.config:
        raise HTTPException(status_code=403, detail="Forbidden")
    db_camera_config = await session.get(CameraConfig, camera_config_id)
    if not db_camera_config:
        raise HTTPException(status_code=404, detail="CameraConfig not found")
    camera_config_data = camera_config.dict(exclude_unset=True)
    
    await session.execute(delete(CameraConfigTagLink).where(CameraConfigTagLink.camera_config_id == camera_config_id))
    for tag_id in camera_config_data.pop("tag_ids", []):
        tag = await session.get(Tag, tag_id)
        if not tag:
            raise HTTPException(status_code=404, detail="Tag not found")
        session.add(CameraConfigTagLink(camera_config_id=camera_config_id, tag_id=tag_id))
    
    for key, value in camera_config_data.items():
        if key == "tag_ids":
            continue
        setattr(db_camera_config, key, value)
    session.add(db_camera_config)
    await session.commit()
    await session.refresh(db_camera_config)
    return db_camera_config


@router.delete("/{camera_config_id}")
async def delete_camera_config(*, session: AsyncSession = Depends(get_session), user: Annotated[UserPublic, Depends(get_current_user)],camera_config_id: int):
    if not hasattr(user, 'config') or not user.config:
        raise HTTPException(status_code=403, detail="Forbidden")
    db_camera_config = await session.get(CameraConfig, camera_config_id)
    if not db_camera_config:
        raise HTTPException(status_code=404, detail="CameraConfig not found")
    await session.delete(db_camera_config)
    await session.commit()
    return {"ok": True}
