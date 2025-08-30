from enum import Enum
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional
from faker import Faker
import uuid
# import random
# import math

router = APIRouter( prefix="/v1/fakedata", tags=["fakedata"])
fake = Faker()

# Enum for status
class Status(str, Enum):
    PENDING = "Pending"
    OK = "OK"
    NG = "NG"

# Pydantic model for Event Log
class EventLog(BaseModel):
    id: int
    name: str
    datetime: str
    camera: str
    location: str
    error_code: str
    img_url: Optional[str] = None
    video_url: Optional[str] = None
    description: Optional[str] = None
    status: Status

    class Config:
        from_attributes = True

# Response model for paginated results
class PaginatedEventLogs(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[EventLog]

# Fake data generator
def generate_fake_event_logs(count: int) -> List[EventLog]:
    event_logs = []
    error_types = [
        {"name": "Camera Offline", "code": "CAM_OFF_001", "desc": "Camera disconnected from network"},
        {"name": "Image Blur", "code": "IMG_BLUR_002", "desc": "Image quality degraded due to lens issue"},
        {"name": "Motion Detection", "code": "MOT_DET_003", "desc": "Unexpected motion detected"},
        {"name": "Storage Error", "code": "STR_ERR_004", "desc": "Failed to save video footage"}
    ]
    
    for i in range(count):
        error = fake.random_element(error_types)
        event_logs.append(EventLog(
            id=i + 1,
            name=error["name"],
            datetime=fake.date_time_this_year().isoformat(),
            camera=f"CAM-{fake.random_int(100, 999)}",
            location=fake.address().split('\n')[0],
            error_code=error["code"],
            img_url=f"https://example.com/images/{uuid.uuid4()}.jpg" if fake.boolean() else None,
            video_url=f"https://example.com/videos/{uuid.uuid4()}.mp4" if fake.boolean() else None,
            description=error["desc"],
            status=fake.random_element([Status.PENDING, Status.OK, Status.NG])
        ))
    return event_logs

# In-memory fake database
FAKE_DB = generate_fake_event_logs(105)

@router.get("/", response_model=PaginatedEventLogs)
async def get_event_logs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    status: Optional[Status] = Query(None, description="Filter by status"),
    camera: Optional[str] = Query(None, description="Filter by camera"),
    id: Optional[int] = Query(None, description="Filter by ID"),
    name: Optional[str] = Query(None, description="Filter by name"),
    location: Optional[str] = Query(None, description="Filter by location"),
    error_code: Optional[str] = Query(None, description="Filter by error code"),
    sort_by: Optional[str] = Query(None, description="Field to sort by (e.g., 'datetime', 'name', 'camera')"),
    sort_order: Optional[str] = Query("asc", regex="^(asc|desc)$", description="Sort order: 'asc' or 'desc'")
):
    # Filter
    filtered_logs = FAKE_DB
    if status:
        filtered_logs = [log for log in filtered_logs if log.status == status]
    if camera:
        filtered_logs = [log for log in filtered_logs if camera.lower() in log.camera.lower()]
    if id:
        filtered_logs = [log for log in filtered_logs if log.id == id]
    if name:
        filtered_logs = [log for log in filtered_logs if name.lower() in log.name.lower()]
    if location:
        filtered_logs = [log for log in filtered_logs if location.lower() in log.location.lower()]
    if error_code:
        filtered_logs = [log for log in filtered_logs if error_code.lower() in log.error_code.lower()]

    # Sort
    sortable_fields = {"id", "datetime", "name", "camera", "location", "status", "error_code"}
    if sort_by in sortable_fields:
        reverse = sort_order == "desc"
        try:
            filtered_logs.sort(key=lambda x: getattr(x, sort_by), reverse=reverse)
        except Exception as e:
            print(f"Error sorting by {sort_by}: {e}")
            pass

    # Pagination
    total = len(filtered_logs)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_logs = filtered_logs[start:end]

    return PaginatedEventLogs(
        total=total,
        page=page,
        page_size=page_size,
        items=paginated_logs
    )
