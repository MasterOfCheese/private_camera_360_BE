import asyncio
import json
import time
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor
import requests
from typing import Set

import psutil
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

try:
    import pynvml
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
        "net_up": net_up,     # MB/s
        "net_down": net_down # MB/s
    }

# Async wrapper để chạy trong thread pool
async def get_system_info() -> Dict[str, Any]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, get_system_info_blocking)

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


def get_mediamtx_active_streams() -> Set[str]:
    """Get active camera streams from MediaMTX API"""
    try:
        # Get MediaMTX API URL from config/environment
        mediamtx_url = "http://localhost:9997/v3/paths/list"  # Có thể config trong .env
        
        response = requests.get(mediamtx_url, timeout=5)
        
        if not response.ok:
            print(f"Failed to fetch MediaMTX status: {response.status_code}")
            return set()
        
        data = response.json()
        active_streams = set()
        
        # Extract active stream names
        if data.get('items') and isinstance(data['items'], list):
            for item in data['items']:
                if item.get('ready') and item.get('name'):
                    active_streams.add(item['name'])
        
        return active_streams
    except requests.exceptions.RequestException as e:
        print(f"Error checking MediaMTX status: {e}")
        return set()
    except Exception as e:
        print(f"Unexpected error in get_mediamtx_active_streams: {e}")
        return set()

def get_camera_status_info() -> dict:
    """Get camera status information"""
    active_streams = get_mediamtx_active_streams()
    return {
        "active_streams": list(active_streams),
        "total_active": len(active_streams),
        "timestamp": time.time()
    }

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