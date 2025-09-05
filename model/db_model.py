import datetime
import os
from typing import Annotated, Optional, Union, List
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
import uvicorn
from func.config import Config
from pydantic import BaseModel

# Base Model without db connection
class CameraConfigBase(SQLModel):
    name: str = Field(index=True)
    location: Optional[str] = Field(default=None)
    preview_image_url : Optional[str] = Field(default=None)
    webrtc_ip : str
    webrtc_ip_low: Optional[str] = Field(default=None)  # Thêm trường mới
    panorama : int
    statistic_api_url : Optional[str] = Field(default=None)
    eventlog_api_url : Optional[str] = Field(default=None)
    fallback_video_url : Optional[str] = Field(default=None)
    isGate: bool = Field(default=False) # Added isGate field
    gate_disable_alarm_url : Optional[str] = Field(default=None) # Added gate_disable_alarm_url field
    
class UserBase(SQLModel):
    username : str
    hash_password : str
    config : Optional[bool] = Field(default=None)
    
class TagBase(SQLModel):
    tag_name : str
    
# DB Model
class CameraConfigTagLink(SQLModel, table=True):
    __tablename__ = "cameraconfigtaglink" # Explicit table name is good practice
    camera_config_id: Optional[int] = Field(default=None,foreign_key="cameraconfig.id",primary_key=True) # Make Optional
    tag_id: Optional[int] = Field(default=None,foreign_key="tag.id",primary_key=True) # Make Optional
    
class Tag(TagBase, table=True):
    __tablename__ = "tag" # Explicit table name
    id: Optional[int] = Field(default=None, primary_key=True) # Optional for creation
    # Ensure lazy='selectin' is on the CameraConfig side for loading tags with cameras
    camera_configs : List["CameraConfig"] = Relationship(back_populates="tags", link_model=CameraConfigTagLink, sa_relationship_kwargs={"lazy": "selectin"}) # Use selectin loading for better performance
    
class CameraConfig(CameraConfigBase, table=True):
    __tablename__ = "cameraconfig" # Explicit table name
    id: Optional[int] = Field(default=None, primary_key=True) # Optional for creation
    # Use selectin loading for tags when a CameraConfig is loaded
    tags : List[Tag] = Relationship(
        back_populates="camera_configs",
        link_model=CameraConfigTagLink,
        # sa_relationship_kwargs={"lazy": "joined"} # Use joined loading for better performance
        sa_relationship_kwargs={"lazy": "selectin"} # Use selectin loading for better performance
    )
    
class User(UserBase, table=True):
    __tablename__ = "user" # Explicit table name
    id: Optional[int] = Field(default=None, primary_key=True) # Optional for creation
    
class Alarm(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    camera_id: str
    error_detail: str
    location: str
    timestamp: str
    is_confirmed: bool = Field(default=False)  # Trạng thái đã xác nhận hay chưa
    alarm_uuid: Optional[str] = Field(default=None, index=True)  # UUID unique cho alarm
    metadata_path: Optional[str] = Field(default=None)    # Đường dẫn file metadata JSON
    img_error: Optional[str] = Field(default=None, nullable=True)   # ✅ Cho phép null
    video_error: Optional[str] = Field(default=None, nullable=True)
    ai_log_path: Optional[str] = Field(default=None, nullable=True)
    camera_name: Optional[str] = Field(default=None)
    is_confirmed: bool = Field(default=False)

class AlarmConfirmationLog(SQLModel, table=True):
    """
    Model để lưu log xác nhận cảnh báo.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    alarm_id: int = Field(foreign_key="alarm.id", index=True)
    employee_confirm_id: str
    client_ip: str
    logged_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    
    
class WorkerEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    camera_id: str
    error_detail: str
    location: str
    timestamp: str
    status: int = Field(default=0)  # 0: Pending, 1: Accept, 2: Decline
    img_error: Optional[str] = Field(default=None, nullable=True)
    video_error: Optional[str] = Field(default=None, nullable=True)
    ai_log_path: Optional[str] = Field(default=None, nullable=True)
    camera_name: Optional[str] = Field(default=None)

# Định nghĩa Pydantic model cho request body của API "/worker-events/{worker_event_id}/confirm"
class AlarmConfirmationRequest(BaseModel):
    employee_confirm_id: str
    client_ip: Optional[str] = None # Cho phép IP null vì có thể không lấy được
    
# Tạo model đơn giản giống Smart Gate
class WorkerEventActionRequest(BaseModel):
    ID: int
    action: str  # "OK" hoặc "NG"
    status: str  # "Pending", "OK", "NG"

# Đơn giản hóa WorkerEventConfirmationLog - bỏ client_ip và employee_confirm_id
class WorkerEventConfirmationLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    worker_event_id: int = Field(foreign_key="workerevent.id", index=True)
    action: str  # "OK" hoặc "NG"
    status: str  # "Pending", "OK", "NG" 
    logged_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    
# DB Model Public for api
class CameraConfigPublic(CameraConfigBase):
    id: int

class TagPublic(TagBase):
    id: int

class UserPublic(UserBase):
    id: int


# DB Model Create
# class CameraConfigCreate(CameraConfigBase):
#     pass

class CameraConfigCreate(BaseModel): # Use Pydantic BaseModel for input validation
    name: str
    location: Optional[str] = None
    preview_image_url: Optional[str] = None
    webrtc_ip: str
    webrtc_ip_low: Optional[str] = None  # Thêm trường mới
    panorama: int
    statistic_api_url: Optional[str] = None
    eventlog_api_url: Optional[str] = None
    fallback_video_url: Optional[str] = None
    isGate: bool = False # Added isGate field
    gate_disable_alarm_url : Optional[str] = None # Added gate_disable_alarm_url field
    tag_ids: List[int] = PydanticField(default_factory=list) # Use Pydantic Field here

class TagCreate(TagBase):
    pass

class UserCreate(UserBase):
    pass

# DB Model Update
class CameraConfigUpdate(BaseModel): # Use Pydantic BaseModel for input validation
    name: Optional[str] = None
    location: Optional[str] = None
    preview_image_url : Optional[str] = None
    webrtc_ip : Optional[str] = None
    webrtc_ip_low: Optional[str] = None  # Thêm trường mới
    panorama : Optional[int] = None
    statistic_api_url : Optional[str] = None
    eventlog_api_url : Optional[str] = None
    fallback_video_url : Optional[str] = None
    tag_ids : Optional[List[int]] = None
    isGate: bool = False # Added isGate field
    gate_disable_alarm_url : Optional[str] = None # Added gate_disable_alarm_url field
    
class TagUpdate(TagBase):
    pass
class UserUpdate(BaseModel): # Use Pydantic BaseModel for input validation
    # Allow updating only specific fields for User
    username : Optional[str] = None
    hash_password : Optional[str] = None
    config : Optional[bool] = None


# DB Model Public with Relationship
class CameraConfigPublicWithTags(CameraConfigPublic):
    # IMPORTANT: Tell Pydantic how to handle the ORM objects
    # Pydantic V2 uses model_config
    model_config = {
        "from_attributes": True,
    }
    # Pydantic V1 uses Config class
    # class Config:
    #     orm_mode = True

    tags: List[TagPublic] = []
    
class TagPublicWithCameraConfigs(TagPublic):
    model_config = {
        "from_attributes": True,
    }
    # class Config:
    #     orm_mode = True

    camera_configs: List[CameraConfigPublic] = []

# DB Connection
config = Config("config/config.yaml")
config.load_config()
DATABASE_URL = config.get_config().db_connection_string # Use the URL from the config file

# Create the async engine
# echo=True is useful for debugging, prints SQL statements
# Set pool_size and max_overflow according to expected load
async_engine = create_async_engine(
    DATABASE_URL,
    echo=False, # Set to True for debugging SQL
    future=True,
    pool_size=10,
    max_overflow=20
)

# Create an async session factory
async_session_maker = sessionmaker(
    bind=async_engine, class_=AsyncSession, expire_on_commit=False
)

# --- Async Dependency for getting a session ---
async def get_session() -> AsyncSession: # type: ignore
    """Dependency to get an async database session."""
    async with async_session_maker() as session:
        try:
            yield session
            # Removing automatic commit here - let endpoints decide
            # await session.commit()
        except Exception:
            await session.rollback()
            raise

# create connection session

# db initialization
async def create_db_and_tables():
    """Creates database tables asynchronously."""
    # Note: create_all is synchronous, run it within run_sync
    async with async_engine.begin() as conn:
        # Drop all tables first to ensure clean state
        # await conn.run_sync(SQLModel.metadata.drop_all)
        # Create all tables
        await conn.run_sync(SQLModel.metadata.create_all)
    print("Database tables created.")

async def create_example_data():
    """Creates example data asynchronously if none exists."""
    async with async_session_maker() as session:
        # Check if tags exist
        # CORRECTED: Use session.execute and scalars().first()
        result_tag_check = await session.execute(select(Tag).limit(1))
        existing_tag = result_tag_check.scalars().first()
        tag_pano, tag_abnormal = None, None

        if not existing_tag:
            print("Creating example tags...")
            tag_pano = Tag(tag_name="panorama")
            tag_abnormal = Tag(tag_name="abnormal detection")
            session.add(tag_pano)
            session.add(tag_abnormal)
            # Commit here to get IDs if needed later, or before adding related objects
            await session.commit()
            # Refresh is often needed after commit to load relationships or generated values
            await session.refresh(tag_pano)
            await session.refresh(tag_abnormal)
            print("Example tags created.")
        else:
            # If tags exist, try to fetch the specific ones we need
            print("Tags already exist, fetching...")
            # CORRECTED: Use session.execute and scalars().first()
            result_pano = await session.execute(select(Tag).where(Tag.tag_name == "panorama"))
            tag_pano = result_pano.scalars().first()
            result_abnormal = await session.execute(select(Tag).where(Tag.tag_name == "abnormal detection"))
            tag_abnormal = result_abnormal.scalars().first()
            if not tag_pano or not tag_abnormal:
                 print("Warning: Could not find expected 'panorama' or 'abnormal detection' tags.")


        # Check if camera configurations exist
        # CORRECTED: Use session.execute and scalars().first()
        result_cam_check = await session.execute(select(CameraConfig).limit(1))
        existing_cam = result_cam_check.scalars().first()

        if not existing_cam:
            print("Creating example camera config...")
            if tag_pano and tag_abnormal: # Make sure tags were created or fetched
                cam1 = CameraConfig(
                    name="Cam01",
                    location="B09 4F",
                    preview_image_url="http://localhost:8000/static/preview.jpg",
                    webrtc_ip="http://localhost:8000/webrtc",
                    webrtc_ip_low="http://localhost:8889/memay",  # Thêm luồng low quality demo
                    panorama=0,    
                    statistic_api_url="http://localhost:8000/static/statistic",
                    eventlog_api_url="http://localhost:8000/static/eventlog",
                    isGate=False,
                    gate_disable_alarm_url="http://localhost:8000/static/gate_disable_alarm",
                    tags=[tag_pano, tag_abnormal] # Assign tag objects directly
                )
                session.add(cam1)
                await session.commit() # Commit after adding camera
                print("Example camera config created.")
            else:
                print("Could not create example camera: missing required tags.")
        else:
            print("Camera configs already exist.")


        # Check if users exist
        # CORRECTED: Use session.execute and scalars().first()
        result_user_check = await session.execute(select(User).limit(1))
        existing_user = result_user_check.scalars().first()

        if not existing_user:
            print("Creating example user...")
            user1 = User(username="admin", hash_password="$2b$12$U7qmJpDBxoJnFnOPueF6G..7ftwDYcT6PbwKgqjN0.HVBgNvQValC", config=True)
            session.add(user1)
            await session.commit() # Commit after adding user
            print("Example user created.")
        else:
             print("Users already exist.")
             
if __name__ == "__main__":
    from fastapi import Depends, FastAPI, HTTPException, Query
    # Create FastAPI app and create db and tables
    app = FastAPI()
    create_db_and_tables()
    create_example_data()
    # # Create FastAPI app for CRUD with DB
    # @app.on_event("startup")
    # def on_startup():
    #     create_db_and_tables()
    #     create_example_data()

    # app.include_router(camera_config_router)
    # app.include_router(tag_router)  
    # app.include_router(user_router)

    # uvicorn.run(app, host="0.0.0.0", port=8000)