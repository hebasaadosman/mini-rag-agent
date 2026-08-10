from venv import logger

from .BaseController import BaseController
from models import ProcessingEnum
import os
from .ProjectController import ProjectController
from langchain_community.document_loaders import TextLoader
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from models.enums.ResponseEnum import ResponseSignals
from typing import List
from dataclasses import dataclass

@dataclass
class FileChunk:
    page_content: str
    metadata: dict

class ProcessController(BaseController):
    def __init__(self,project_id: str):
        super().__init__()
        self.project_id = project_id
        self.project_path = ProjectController().get_project_path(project_id=project_id)

    def get_file_extension(self, file_id: int):
        file_extension = os.path.splitext(file_id)[-1]
        return file_extension
    
    def get_file_loader(self, file_id: int):
        file_extension = self.get_file_extension(file_id=file_id)
        file_path = os.path.join(self.project_path, file_id)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"{ResponseSignals.FILE_NOT_FOUND.value}")
        if file_extension == ProcessingEnum.PDF.value:
            loader = PyMuPDFLoader(file_path)
        elif file_extension == ProcessingEnum.TXT.value:
            loader = TextLoader(file_path, encoding="utf8")
        else:
            raise ValueError(f"{ResponseSignals.FILE_NOT_SUPPORTED.value}: {file_extension}")
        return loader
    
    def get_file_content(self, file_id: int):
        loader = self.get_file_loader(file_id=file_id)
        documents = loader.load()
        return documents
    async def process_file_content(self, file_id: int, chunk_size: int = 100, overlap_size: int = 20, do_reset: int = 0):
        file_content = self.get_file_content(file_id=file_id)
        if not file_content or len(file_content) == 0:
            logger.warning(f"Error while processing file {file_id}. No content found.")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap_size,length_function=len, separators=["\n\n", "\n", " ", ""])
        file_content_texts= [
            
            doc.page_content 
            for doc in file_content
            
            
            ]
        file_content_metadata = [
            doc.metadata
            for doc in file_content
        ]
       
        # chunks = text_splitter.create_documents(file_content_texts, metadatas=file_content_metadata)
        # serializable_chunks = [
        #     {
        #         "page_content": chunk.page_content,
        #         "metadata": chunk.metadata,
        #     }
        #     for chunk in chunks
        # ]

        # return serializable_chunks
        return self.process_simpler_spiliter(file_content_texts,file_content_metadata,chunk_size=chunk_size,overlap_size=overlap_size,spiliter_tag="\n")
    
    def process_simpler_spiliter(self,texts:List[str],metadata:List[dict],chunk_size: int = 200, overlap_size: int = 20,spiliter_tag:str="\n"):
        full_text = " ".join(texts)
        lines=[
            doc.strip()
            
            for i, doc in enumerate(full_text.split(spiliter_tag)) if len(doc.strip()) > 1
        ]
        chunks = []
        current_chunk = ""
        for line in lines:
            if len(current_chunk) + len(line) + 1 <= chunk_size:
                current_chunk += line +spiliter_tag
            else:
                chunks.append(FileChunk(page_content=current_chunk.strip(), metadata={}))
                current_chunk = line + spiliter_tag
        if current_chunk:
            chunks.append(FileChunk(page_content=current_chunk.strip(), metadata={}))
        return chunks