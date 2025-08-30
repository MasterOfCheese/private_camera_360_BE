import asyncio
import json
import time
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor

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
