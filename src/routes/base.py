from fastapi import FastAPI, APIRouter,Depends
from helpers.config import get_settings, Settings

base_router = APIRouter(
    prefix="/api/v1",
    tags=["system"],
)

@base_router.get("/")
async def read_root(app_settings: Settings = Depends(get_settings)):
    return {
        "app_name": app_settings.APP_NAME,
        "version": app_settings.APP_VERSION,
        "message": "Hello from FastAPI! we are ready to serve your requests.",
        "description": "This is the base route of the FastAPI application if test pass.",
        }
@base_router.get("/health", include_in_schema=False)
async def health_check():
    return {"status": "ok"}
