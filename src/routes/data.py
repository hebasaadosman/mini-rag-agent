
from typing import Annotated

from fastapi import APIRouter, Depends, Request, UploadFile, status
from fastapi.responses import JSONResponse
import aiofiles
from helpers.config import get_settings, Settings
import os
from controllers import DataController
from models import ResponseSignals
import logging
from models.db_schemes import  Asset
from .schemes.data import ProcessRequest
from models.ProjectModel import ProjectModel
from models.ChunkModel import ChunkModel
from models.AssetModel import AssetModel
from models.enums import AssetTypeEnum
from controllers import NLPController
from tasks.file_processing import process_project_files
from authorization import ProjectAccess, ProjectPermission
from authorization.dependencies import require_project_permission
from auditing.correlation import background_request_metadata, request_correlation_id

logger = logging.getLogger("uvicorn.error")
data_controller = DataController()
data_router = APIRouter(
    prefix="/api/v1/data",
    tags=["data"],
)

ProjectWriteAccess = Annotated[
    ProjectAccess,
    Depends(require_project_permission(ProjectPermission.WRITE)),
]

@data_router.post("/upload/{project_id}")

async def upload_data(request: Request, project_id: int, file: UploadFile, app_settings: Settings = Depends(get_settings), access: ProjectWriteAccess = None):

    project_model = await ProjectModel.create_instance(request.app.db_client) 
    project = await project_model.get_project_by_id(project_id)
    if project is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"signal": "PROJECT_NOT_FOUND"},
        )
    is_valid, signal = await data_controller.validate_uploaded_file(file)
    if not is_valid:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"signal": signal})
    
    file_id, file_path = data_controller.generate_unique_filepath(original_filename=file.filename, project_id=project_id)
    try:
        async with aiofiles.open(file_path, "wb") as f:
            while chunk := await file.read(app_settings.FILE_DEFAULT_CHUNK_SIZE):
                await f.write(chunk)
        asset_model = await AssetModel.create_instance(request.app.db_client)
        asset = Asset(
            asset_name=file_id,
            asset_size=os.path.getsize(file_path),
            asset_project_id=project.project_id,
            asset_type=AssetTypeEnum.FILE.value,
        )
        asset_record = await asset_model.create_asset(asset)
        
    except Exception as e:
        logger.error(f"Error occurred while uploading file: {e}")
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"signal": ResponseSignals.FILE_UPLOAD_FAILED.value, "error": str(e)})


    return JSONResponse(
    status_code=status.HTTP_200_OK,
    content={
        "signal": ResponseSignals.FILE_UPLOAD_SUCCESS.value,
        "asset_id": asset_record.asset_id,
        "asset_name": asset_record.asset_name,
        "file_path": str(file_path),
        "file_size": asset_record.asset_size,
    },
)



@data_router.post("/process/{project_id}")
async def process_endpoint(request: Request, project_id: int, process_request: ProcessRequest, app_settings: Settings = Depends(get_settings), _: ProjectWriteAccess = None):
   chunk_size = process_request.chunk_size
   overlap_size = process_request.overlap_size
   do_reset = process_request.do_reset

   task = process_project_files.delay(
        project_id=project_id,
        asset_id=process_request.asset_id,
        chunk_size=chunk_size,
        overlap_size=overlap_size,
        do_reset=do_reset,
        principal_id=_.principal_id if _ else None,
        correlation_id=request_correlation_id(request),
        request_metadata=background_request_metadata(
            route="POST /api/v1/data/process/{project_id}"
        ),
    )

   return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "signal": ResponseSignals.FILE_PROCESSING_TASK_QUEUED.value,
            "task_id": task.id
        }
    )
