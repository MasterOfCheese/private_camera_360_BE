# import threading
import os
import uvicorn
from fastapi import FastAPI, Path
from fastapi.staticfiles import StaticFiles  # Add this import
from fastapi.middleware.cors import CORSMiddleware  # Add this import
from func.api_router.v1.camera_router import router
from func.api_gateway import create_app

app = create_app()

# Mount the static directory to serve files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)


# Mount static files để serve images, videos, logs
# app.mount("/static", StaticFiles(directory="static"), name="static")

# Include your routers
# app.include_router(router, prefix="/v1/cameras", tags=["cameras"])

# Optional: API để list files trong một alarm folder
@app.get("/api/alarms/{alarm_uuid}/browse")
async def browse_alarm_files(alarm_uuid: str):
    """
    API để browse các files trong alarm folder
    """
    try:
        # Tìm alarm folder theo UUID
        base_path = Path("static/alarms")
        
        for date_folder in base_path.iterdir():
            if date_folder.is_dir():
                for camera_folder in date_folder.iterdir():
                    if camera_folder.is_dir():
                        # Check if this folder contains our UUID
                        for file_path in camera_folder.iterdir():
                            if alarm_uuid in file_path.name:
                                # Found the alarm folder
                                files = []
                                for f in camera_folder.iterdir():
                                    if alarm_uuid in f.name:
                                        relative_path = f.relative_to(Path("static"))
                                        files.append({
                                            "filename": f.name,
                                            "path": f"static/{relative_path}",
                                            "url": f"/static/{relative_path}",
                                            "size": f.stat().st_size,
                                            "type": f.suffix.lower()
                                        })
                                
                                return {
                                    "alarm_uuid": alarm_uuid,
                                    "folder_path": str(camera_folder),
                                    "files": files
                                }
        
        return {"error": "Alarm files not found", "alarm_uuid": alarm_uuid}
        
    except Exception as e:
        return {"error": str(e)}

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "static_path_exists": os.path.exists("static")}


def run_server():
    uvicorn.run(app, host=app.state.config.host, port=app.state.config.port, log_config=None)

if __name__ == "__main__":
    run_server()
    print("Server stopped.")