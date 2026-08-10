from helpers.config import Settings, get_settings

class BaseDataModel:
    def __init__(self,db_client):
        self.settings: Settings = get_settings()
        self.db_client = db_client  
