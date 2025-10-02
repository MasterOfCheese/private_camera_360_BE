import asyncio
import json
import time
import os
from typing import Dict, Any, Set, List
from concurrent.futures import ThreadPoolExecutor
import requests

import psutil
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# Import Config class từ config.py
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import Config

try:
    import pynvml # type: ignore
    pynvml.nvmlInit()
    gpu_available = True
except (ImportError, pynvml.NVMLError):
    gpu_available = False

# Create an APIRouter instance
router = APIRouter(
    prefix="/v1/sys",
    tags=["System Info"],
)

# ThreadPoolExecutor để chạy các hàm blocking
executor = ThreadPoolExecutor()

# Load config using Config class
def load_config():
    """Load configuration from config.yaml using Config class"""
    try:
        # Tìm đường dẫn tới config/config.yaml từ project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        config_path = os.path.join(project_root, 'config', 'config.yaml')
        
        # Fallback: thử từ current working directory
        if not os.path.exists(config_path):
            config_path = os.path.join(os.getcwd(), 'config', 'config.yaml')
        
        print(f"Loading config from: {config_path}")
        
        config_manager = Config(config_path)
        config_manager.load_config()
        config_obj = config_manager.get_config()
        
        # Convert ConfigObject to dict
        return config_obj.to_dict()
    except Exception as e:
        print(f"Error loading config: {e}")
        return {}

# Global config
config = load_config()

def get_gpu_load():
    if not gpu_available:
        return -1
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        return util.gpu  # GPU utilization in percent
    except pynvml.NVMLError:
        return -1
    
    
def get_network_load(interval=1.0):
    net1 = psutil.net_io_counters()
    bytes_sent1 = net1.bytes_sent
    bytes_recv1 = net1.bytes_recv

    time.sleep(interval)

    net2 = psutil.net_io_counters()
    bytes_sent2 = net2.bytes_sent
    bytes_recv2 = net2.bytes_recv

    upload_speed = (bytes_sent2 - bytes_sent1) / interval  # bytes/sec
    download_speed = (bytes_recv2 - bytes_recv1) / interval  # bytes/sec
    
    return upload_speed, download_speed

# Hàm blocking thật sự
def get_system_info_blocking() -> Dict[str, Any]:
    cpu_percent = psutil.cpu_percent(interval=1)  # Blocking call
    memory_info = psutil.virtual_memory()
    ram_percent = memory_info.percent
    try:
        disk_info = psutil.disk_usage('/')
        disk_percent = disk_info.percent
    except FileNotFoundError:
        disk_percent = -1

    gpu_percent = get_gpu_load()
    net_up, net_down = get_network_load()
    return {
        "cpu": cpu_percent,
        "ram": ram_percent,
        "disk": disk_percent,
        "gpu": gpu_percent,
        "net_up": net_up,     # bytes/sec
        "net_down": net_down # bytes/sec
    }

# Async wrapper để chạy trong thread pool
async def get_system_info() -> Dict[str, Any]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, get_system_info_blocking)

def get_mediamtx_servers() -> List[Dict[str, Any]]:
    """Get MediaMTX servers from config"""
    servers = config.get('mediamtx_servers', [])
    
    print(f"Debug - Raw config mediamtx_servers: {servers}")
    
    if not servers:
        # Fallback to localhost if no config found
        print("No MediaMTX servers found in config, using localhost fallback")
        return [{"ip": "localhost", "port": 9997, "enabled": True}]
    
    # Only return enabled servers
    enabled_servers = [server for server in servers if server.get('enabled', True)]
    print(f"Debug - Enabled servers: {enabled_servers}")
    
    return enabled_servers

def get_mediamtx_active_streams_from_server(server_ip: str, server_port: int = 9997) -> Set[str]:
    """Get active camera streams from a single MediaMTX server"""
    try:
        mediamtx_url = f"http://{server_ip}:{server_port}/v3/paths/list"
        
        response = requests.get(mediamtx_url, timeout=5)
        
        if not response.ok:
            print(f"Failed to fetch MediaMTX status from {server_ip}:{server_port} - Status: {response.status_code}")
            return set()
        
        data = response.json()
        active_streams = set()
        
        # Extract active stream names
        if data.get('items') and isinstance(data['items'], list):
            for item in data['items']:
                if item.get('ready') and item.get('name'):
                    active_streams.add(item['name'])
        
        print(f"Found {len(active_streams)} active streams from {server_ip}:{server_port}: {list(active_streams)}")
        return active_streams
    except requests.exceptions.RequestException as e:
        print(f"Error checking MediaMTX status from {server_ip}:{server_port}: {e}")
        return set()
    except Exception as e:
        print(f"Unexpected error getting streams from {server_ip}:{server_port}: {e}")
        return set()

def get_mediamtx_active_streams() -> Set[str]:
    """Get active camera streams from all MediaMTX servers"""
    all_active_streams = set()
    servers = get_mediamtx_servers()
    
    print(f"Checking {len(servers)} MediaMTX servers...")
    
    for server in servers:
        server_ip = server.get('ip', 'localhost')
        server_port = server.get('port', 9997)
        
        server_streams = get_mediamtx_active_streams_from_server(server_ip, server_port)
        all_active_streams.update(server_streams)
    
    print(f"Total unique active streams across all servers: {len(all_active_streams)}")
    return all_active_streams

def get_camera_status_info() -> dict:
    """Get camera status information from all MediaMTX servers"""
    active_streams = get_mediamtx_active_streams()
    servers = get_mediamtx_servers()
    
    return {
        "active_streams": sorted(list(active_streams)),  # Sort for consistent output
        "total_active": len(active_streams),
        "servers_checked": len(servers),
        "servers": [{"ip": s.get('ip'), "port": s.get('port')} for s in servers],
        "timestamp": time.time()
    }

# WebSocket Endpoint
@router.websocket("/info")
async def websocket_sysinfo_endpoint(websocket: WebSocket):
    print("Client connecting to /sys/info ...")
    await websocket.accept()
    print("Client connected to /sys/info.")

    try:
        while True:
            sys_info = await get_system_info()  # Gọi async non-blocking
            await websocket.send_json(sys_info)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        print("Client disconnected from /sys/info.")
    except Exception as e:
        print(f"An error occurred on /sys/info: {e}")
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass
    finally:
        print("WebSocket connection closed for /sys/info.")

# Regular HTTP route
@router.get("/status")
async def get_status():
    sys_info = await get_system_info()  # Gọi async non-blocking
    return sys_info

# WebSocket Endpoint for Camera Status
@router.websocket("/camera-status")
async def websocket_camera_status_endpoint(websocket: WebSocket):
    print("Client connecting to /sys/camera-status ...")
    await websocket.accept()
    print("Client connected to /sys/camera-status.")

    try:
        while True:
            loop = asyncio.get_running_loop()
            camera_status = await loop.run_in_executor(executor, get_camera_status_info)
            await websocket.send_json(camera_status)
            await asyncio.sleep(5)  # Update mỗi 5 giây
    except WebSocketDisconnect:
        print("Client disconnected from /sys/camera-status.")
    except Exception as e:
        print(f"An error occurred on /sys/camera-status: {e}")
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass
    finally:
        print("WebSocket connection closed for /sys/camera-status.")

# HTTP endpoint để test
@router.get("/camera-status")
async def get_camera_status():
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, get_camera_status_info)

# Endpoint để reload config (tiện cho việc thay đổi cấu hình server)
@router.post("/reload-config")
async def reload_config():
    global config
    config = load_config()
    return {"message": "Config reloaded successfully", "mediamtx_servers": get_mediamtx_servers()}