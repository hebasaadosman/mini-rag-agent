from helpers.config import Settings,get_settings
import os
import random
import string
class BaseController:
    
    def __init__(self):
        self.app_settings: Settings = get_settings()
        self.base_dir = os.path.dirname(os.path.dirname((__file__)))
        self.files_dir = os.path.join(self.base_dir, "assets/files")
        self.database_dir = os.path.join(self.base_dir, "assets/database")

    def generate_random_string(self, length: int = 12):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    def get_database_path(self,database_name: str = None):
        if database_name:
           database_path = os.path.join(self.database_dir, database_name)
           if not os.path.exists(database_path):
               os.makedirs(database_path)
           return database_path
