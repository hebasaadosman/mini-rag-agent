from .BaseController import BaseController
from models.db_schemes import Project
import re
from typing import List, Dict, Any
from models.db_schemes import DataChunk
from stores.llm.LLMEnum import DocumentTypeEnum
class NLPController(BaseController):
    def __init__(self,vectordb_client=None,generation_client=None,embedding_client=None,template_parser=None):
        super().__init__()
        self.vectordb_client = vectordb_client
        self.generation_client = generation_client
        self.embedding_client = embedding_client
        self.template_parser = template_parser


    async def create_collection_name(self, project_id: str):
        collection_name = f"collection_{self.vectordb_client.default_vector_size}_{project_id}".strip()
        return collection_name


    async def reset_vectordb_collection(self, project: Project):
        collection_name = await self.create_collection_name(project.project_id)
        if self.vectordb_client:
           await self.vectordb_client.delete_collection(collection_name)
           return True, f"Collection '{collection_name}' has been reset."
        else:
            return False, "VectorDB client is not initialized."

    async def get_vectordb_collection_info(self, project: Project):
        collection_name = await self.create_collection_name(project.project_id)
        if self.vectordb_client:
            collection_info = await self.vectordb_client.get_collection_info(collection_name)
            return True, collection_info
        else:
            return False, "VectorDB client is not initialized."

    async def index_into_vectordb(self, project: Project, chunks: List[DataChunk], do_reset: bool = False):
        collection_name = await self.create_collection_name(project.project_id)
        if self.vectordb_client:
            if do_reset:
                await self.vectordb_client.delete_collection(collection_name)
            # Assuming chunks is a list of DataChunk objects
            texts = [chunk.chunk_text for chunk in chunks]
            metadatas = [chunk.chunk_metadata for chunk in chunks]
            vectors=  self.embedding_client.generate_embedding(texts, document_type=DocumentTypeEnum.DOCUMENT.value)
               
            
            record_ids = [
            chunk.chunk_id
            for chunk in chunks
          ]
            # for text, vector, metadata in zip(texts, vectors, metadatas):
            #     records.append({
            #         "text": text,
            #         "vector": vector,
            #         "metadata": metadata,
            #         "chunk_id": None  # Add a placeholder for chunk_id
            #     })
            inserted_count = await self.vectordb_client.insert_many_vectors(
                collection_name=collection_name,
                vectors=vectors,
                texts=texts,
                metadatas=metadatas,
                record_ids=record_ids,
                batch_size=100,
            )

            return True, f"Indexed {inserted_count} chunks into collection '{collection_name}'."
        else:
            return False, "VectorDB client is not initialized."
    async def search_in_vectordb(
        self,
        project: Project,
        query: str,
        limit: int = 5,
    ):
        collection_name = await self.create_collection_name(
            project.project_id
        )

        if not self.vectordb_client:
            return (
                False,
                "VectorDB client is not initialized.",
            )

        query_vector = (
            self.embedding_client.generate_embedding(
                query,
                document_type=(
                    DocumentTypeEnum.QUERY.value
                ),
            )
        )

        if query_vector is None:
            return (
                False,
                "Failed to generate embedding "
                "for the query.",
            )

        if not isinstance(
            query_vector,
            list,
        ):
            return (
                False,
                "Invalid query vector returned "
                "from embedding client.",
            )

        expected_vector_size = (
            self.vectordb_client
            .default_vector_size
        )

        if len(query_vector) != expected_vector_size:
            return (
                False,
                (
                    f"Invalid query vector size: "
                    f"{len(query_vector)}. "
                    f"Expected "
                    f"{expected_vector_size}."
                ),
            )

        # The caller asks for unique results.
        #
        # We fetch more raw vector matches because
        # duplicate documents may occupy the first
        # positions in the vector search results.
        raw_limit = min(
            max(
                limit * 4,
                20,
            ),
            100,
        )

        search_results = (
            await self.vectordb_client
            .search_by_vector(
                collection_name,
                query_vector,
                raw_limit,
            )
        )

        if search_results is None:
            return (
                False,
                "Search operation failed.",
            )

        unique_results = []
        seen_texts = set()

        for result in search_results:
            normalized_text = " ".join(
                result.text.split()
            ).strip()

            if not normalized_text:
                continue

            if normalized_text in seen_texts:
                continue

            seen_texts.add(
                normalized_text
            )

            unique_results.append(
                result
            )

            if len(unique_results) >= limit:
                break

        results = [
            result.model_dump(
                mode="json"
            )
            for result in unique_results
        ]

        if results:
            print(
                "TOP UNIQUE VECTOR SEARCH RESULT:",
                results[0],
            )

        return True, results
    async def answer_rag_question(self, project: Project, query: str, limit: int = 5):
        # Step 1: Search in VectorDB
        search_success, retrived_documents = await self.search_in_vectordb(project, query, limit)
        if not search_success:
            return False, f"Search failed: {retrived_documents}"

        # Step 2: Construct LLM Prompt

        system_prompt = self.template_parser.get("rag", "system_prompt")
        # document_prompt=[]  
        # for ind, doc in enumerate(retrived_documents):
        #     document_prompt.append(self.template_parser.get("rag", "document_prompt",
        #         {
        #             "doc_num": ind + 1,
        #             "chunk_text": doc['text'],
        #         }
        #     ))
    
        document_prompt = "\n".join([self.template_parser.get("rag", "document_prompt",
                {
                    "doc_num": ind + 1,
                    "chunk_text": self.generation_client.process_text(doc['text']),
                }
            ) for ind, doc in enumerate(retrived_documents)
        ])

        footer_prompt = self.template_parser.get(
            "rag",
            "footer_prompt",
            {"query": query}
        )
        chat_history = [
            self.generation_client.construct_prompt(system_prompt, role=self.generation_client.enums.SYSTEM.value),
        ]
        full_prompt = f"{document_prompt}\n{footer_prompt}\n\n"
        answer = self.generation_client.generate_text(full_prompt, chat_history=chat_history)
        if answer is None:
            return False, "Failed to generate answer from LLM." 
        return True, answer,full_prompt, chat_history
