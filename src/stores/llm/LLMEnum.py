from enum import Enum


class LLMEnum(Enum):

  OPENAI = "OPENAI"
  COHERE = "COHERE"

class OpenAIRoleEnum(Enum):

  USER = "user"
  ASSISTANT = "assistant"
  SYSTEM = "system"


class CohereRoleEnum(Enum):
  USER = "USER"
  ASSISTANT = "CHATBOT"
  SYSTEM = "SYSTEM"

  DOCUMENT = "search_document"
  QUERY = "search_query"

class DocumentTypeEnum(Enum):
  DOCUMENT = "document"
  QUERY = "query"