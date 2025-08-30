# from typing import Annotated, Optional, Union
# from pydantic import BaseModel
# from sqlmodel import Field, Relationship, Session, SQLModel, create_engine, select
# import uvicorn

# # Base Model without db connection
# class CameraConfigBase(SQLModel):
#     name: str = Field(index=True)
#     location: Optional[str] = Field(default=None)
#     preview_image_url : Optional[str] = Field(default=None)
#     webrtc_ip : str
#     panorama : int
#     statistic_api_url : Optional[str] = Field(default=None)
#     eventlog_api_url : Optional[str] = Field(default=None)
#     fallback_video_url : Optional[str] = Field(default=None)
# class UserBase(SQLModel):
#     username : str
#     hash_password : str
#     config : Optional[bool] = Field(default=None)
# class TagBase(SQLModel):
#     tag_name : str
    
# # DB Model
# class CameraConfigTagLink(SQLModel, table=True):
#     camera_config_id: int = Field(default=None,foreign_key="cameraconfig.id",primary_key=True)
#     tag_id: int = Field(default=None,foreign_key="tag.id",primary_key=True)
# class CameraConfig(CameraConfigBase, table=True):
#     id: Union[int, None] = Field(default=None, primary_key=True)
#     tags : Optional[list['Tag']] = Relationship(back_populates="camera_configs", link_model=CameraConfigTagLink, sa_relationship_kwargs={"lazy": "selectin"})
#     # tags : Optional[list['Tag']] = Relationship(back_populates="camera_configs", link_model=CameraConfigTagLink, sa_relationship_kwargs={"lazy": "selectin"}) # this is the correct one
# class Tag(TagBase, table=True):
#     id: Union[int, None] = Field(default=None, primary_key=True)
#     camera_configs : list[CameraConfig] = Relationship(back_populates="tags", link_model=CameraConfigTagLink)
# class User(UserBase, table=True):
#     id: Union[int, None] = Field(default=None, primary_key=True)
    


# # DB Model Public for api
# class CameraConfigPublic(CameraConfigBase):
#     id: int
# class TagPublic(TagBase):
#     id: int
# class UserPublic(UserBase):
#     id: int

# # DB Model Create
# # class CameraConfigCreate(CameraConfigBase):
# #     pass

# class CameraConfigCreate(BaseModel):
#     name: str
#     location: Optional[str] = None
#     preview_image_url: Optional[str] = None
#     webrtc_ip: str
#     panorama: int
#     statistic_api_url: Optional[str] = None
#     eventlog_api_url: Optional[str] = None
#     fallback_video_url: Optional[str] = None
#     tag_ids: list[int] = [] 
    
    
# class TagCreate(TagBase):
#     pass
# class UserCreate(UserBase):
#     pass

# # DB Model Update
# class CameraConfigUpdate(BaseModel):
#     name: Optional[str] = Field(default=None)
#     location: Optional[str] = Field(default=None)
#     preview_image_url : Optional[str] = Field(default=None)
#     webrtc_ip : Optional[str] = Field(default=None)
#     panorama : Optional[int] = Field(default=None)
#     statistic_api_url : Optional[str] = Field(default=None)
#     eventlog_api_url : Optional[str] = Field(default=None)
#     fallback_video_url : Optional[str] = Field(default=None)
#     tag_ids : Optional[list[int]] = Field(default=None)
# class TagUpdate(TagBase):
#     pass
# class UserUpdate(UserBase):
#     hash_password : Optional[str] = Field(default=None)

# # DB Model Public with Relationship
# class CameraConfigPublicWithTags(CameraConfigPublic):
#     tags: list[TagPublic] = []
# class TagPublicWithCameraConfigs(TagPublic):
#     camera_configs: list[CameraConfigPublic] = []

# # DB Connection
# sqlite_file_name = "SGF_database.db"
# sqlite_url = f"sqlite:///database/{sqlite_file_name}"

# connect_args = {"check_same_thread": False}
# engine = create_engine(sqlite_url, connect_args=connect_args)

# # create connection session
# def get_session():
#     with Session(engine) as session:
#         yield session

# def create_db_and_tables():
#     import os
#     os.makedirs("database", exist_ok=True)
#     SQLModel.metadata.create_all(engine)

# def create_example_data():
#     import os
#     from sqlmodel import Session

#     # Check if database directory exists, if not, create it
#     os.makedirs("database", exist_ok=True)

#     with Session(engine) as session:
#         # Check if tags exist, if not, create them
#         if not session.exec(select(Tag)).first():
#             tag_pano = Tag(tag_name="panorama")
#             tag_abnormal = Tag(tag_name="abnormal detection")
#             session.add(tag_pano)
#             session.add(tag_abnormal)
#             session.commit()

#         # Check if camera configurations exist, if not, create them
#         if not session.exec(select(CameraConfig)).first():
#             cam1 = CameraConfig(
#                 name="Cam01", 
#                 location="B09 4F",
#                 preview_image_url="http://localhost:8000/static/preview.jpg",
#                 webrtc_ip="http://localhost:8000/webrtc",
#                 panorama=0,
#                 statistic_api_url="http://localhost:8000/static/statistic",
#                 eventlog_api_url="http://localhost:8000/static/eventlog",
#                 tags=[tag_pano, tag_abnormal]
#             )
#             session.add(cam1)
#             session.commit()
#         # Check if users exist, if not, create them
#         if not session.exec(select(User)).first():
#             user1 = User(username="admin", hash_password="$2b$12$U7qmJpDBxoJnFnOPueF6G..7ftwDYcT6PbwKgqjN0.HVBgNvQValC", config=True)
#             session.add(user1)
#             session.commit()
# if __name__ == "__main__":
#     from fastapi import Depends, FastAPI, HTTPException, Query
#     # Create FastAPI app and create db and tables
#     app = FastAPI()
#     create_db_and_tables()
#     create_example_data()
#     # # Create FastAPI app for CRUD with DB
#     # @app.on_event("startup")
#     # def on_startup():
#     #     create_db_and_tables()
#     #     create_example_data()

#     # app.include_router(camera_config_router)
#     # app.include_router(tag_router)  
#     # app.include_router(user_router)

#     # uvicorn.run(app, host="0.0.0.0", port=8000)