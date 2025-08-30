from fastapi import APIRouter
from fastapi.responses import HTMLResponse,FileResponse
from fastapi.staticfiles import StaticFiles

router = APIRouter(prefix="/v1",tags=["static"])
router2 = APIRouter(prefix="/v2",tags=["static"])

@router.get("/", response_class=FileResponse)
async def root():
    return "templates/index.html"
@router2.get("/", response_class=FileResponse)
async def root():
    return "templates/index2.html"