from .BaseController import BaseController
from fastapi import UploadFile
from models import ResponseSignals
import os
from .ProjectController import ProjectController
import re

class DataController(BaseController):
    def __init__(self):
        super().__init__()
        self.size_scale=1048576  # 1 MB in bytes

    async def validate_uploaded_file(self, file: UploadFile):
        # Validate file type
        if file.content_type not in self.app_settings.FILE_ALLOWED_TYPES:
            return False, f"{ResponseSignals.FILE_TYPE_NOT_ALLOWED.value}. Allowed types: {', '.join(self.app_settings.FILE_ALLOWED_TYPES)}."
        # Validate file size
        if file.size > self.app_settings.FILE_MAX_SIZE * self.size_scale:
            return False, f"{ResponseSignals.FILE_SIZE_EXCEEDED.value}. Maximum limit: {self.app_settings.FILE_MAX_SIZE} MB."
        
        # Reset file pointer after reading
        await file.seek(0)
        
        return True, ResponseSignals.FILE_UPLOAD_SUCCESS.value
    
    def generate_unique_filepath(self, original_filename: str ,project_id: str):
        random_string = self.generate_random_string()
        project_path = ProjectController().get_project_path(project_id=project_id)
        cleaned_filename = self.get_cleaned_filename(original_filename)
        new_filename = f"{random_string}_{cleaned_filename}"
        file_path = os.path.join(project_path, new_filename)
        while os.path.exists(file_path):        
            random_string = self.generate_random_string(8)
            new_filename = f"{random_string}_{cleaned_filename}"
            file_path = os.path.join(project_path, new_filename)
        return new_filename, file_path
    
    def get_cleaned_filename(self, original_file_name: str):
        cleaned_filename =re.sub(r'[^a-zA-Z0-9_.-]', '_', original_file_name)
        return cleaned_filename