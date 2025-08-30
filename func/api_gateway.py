import datetime
import socket
from fastapi.staticfiles import StaticFiles
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
from contextlib import asynccontextmanager
try:
    from func.api_router.v1.camera_router import router as camera_config_router
    from func.api_router.v1.tag_router import router as tag_router
    from func.api_router.v1.user_router import router as user_router   
    from func.static_router.v1.static_router import router as static_router
    from func.static_router.v1.static_router import router2 as static_router_v2
    from func.auth.v1.auth import router as auth_router
    from func.api_router.v1.fakedata_router import router as fakedata_router
    from func.api_router.v1.monitoring_ws import router as monitoring_router
    from func.logger import Logger
    from func.async_logger import AsyncLogger
    from model.db_model import create_db_and_tables, create_example_data
    from func.config import Config
except Exception as e:
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from func.api_router.v1.camera_router import router as camera_config_router
    from func.api_router.v1.tag_router import router as tag_router
    from func.api_router.v1.user_router import router as user_router  
    from func.static_router.v1.static_router import router as static_router 
    from func.static_router.v1.static_router import router2 as static_router_v2
    from func.api_router.v1.fakedata_router import router as fakedata_router
    from func.api_router.v1.monitoring_ws import router as monitoring_router
    from func.auth.v1.auth import router as auth_router
    from func.logger import Logger
    from func.async_logger import AsyncLogger
    from model.db_model import create_db_and_tables, create_example_data
    from func.config import Config

class FastAPIApp:
    def __init__(self):
        self.create_static_and_template_dir()
        self.app = FastAPI(lifespan=lifespan)
        # self.app.state.logger = Logger()
        self.load_config()
        # self.app.state.config_manager = Config("config.yaml")
        self.app.state.logger = AsyncLogger(log_dir=self.app.state.config.log_dir, buffer_size=10, time_interval=1)
        self.include_routers()
        self.allow_cors()
        self.add_logging()
        self.host_static()
        self.host_fake_data()
 
    def load_config(self):
        self.config_manager= Config("config/config.yaml")
        self.config_manager.load_config()
        self.app.state.config = self.config_manager.get_config()

    def include_routers(self):
        self.app.include_router(camera_config_router)
        self.app.include_router(tag_router)
        self.app.include_router(user_router)
        self.app.include_router(static_router) 
        self.app.include_router(auth_router)
        self.app.include_router(monitoring_router)
        self.app.include_router(static_router_v2)
        
    def allow_cors(self):
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    def add_logging(self):
        @self.app.middleware("http")
        async def log_request(request: Request, call_next):
            response = await call_next(request)
            self.app.state.logger.log(f"IP: {request.client.host} - Request: {request.method} {request.url} - Response: {response.status_code}", show=False)
            return response

    def get_app(self):
        return self.app
    
    def get_logger(self):
        return self.logger

    def host_static(self):
        self.app.mount("/static", StaticFiles(directory="static"), name="static")
        
    def host_fake_data(self):
        self.app.include_router(fakedata_router)
        
    def create_static_and_template_dir(self):
        import os
        if not os.path.exists("static"):
            os.makedirs("static")
        if not os.path.exists("templates"):
            os.makedirs("templates")
            
def read_host_location():
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"Server local IP: {local_ip}")
    return local_ip
    
    # def __del__(self):
    #     self.app.state.logger.stop()
        

def create_app():
    return FastAPIApp().get_app()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting FastAPI application...")
    print(f"Loading configuration: {app.state.config}")
    await create_db_and_tables()
    await create_example_data()
    app.state.local_ip = read_host_location()
    app.state.host_address = f'http://{app.state.local_ip}:{app.state.config.port}'
    yield
    app.state.logger.stop()
    print("Stopping FastAPI application...")

if __name__ == "__main__":
    app = create_app()
    uvicorn.run(app, host=app.state.config.host, port=app.state.config.port, log_config=None)
