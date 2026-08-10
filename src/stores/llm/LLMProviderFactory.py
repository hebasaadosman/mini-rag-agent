from .LLMEnum import LLMEnum
from stores.llm.providers.OpenAIProvider import OpenAIProvider
from stores.llm.providers.CohereProvider import CohereProvider
    

class LLMProviderFactory:
    def __init__(self, config: dict):
        self.config = config

    def create_provider(self, provider_name: str):
        if provider_name == LLMEnum.OPENAI.value:
            return OpenAIProvider(
                api_key=self.config.get("OPENAI_API_KEY"),
                api_url=self.config.get("OPENAI_API_URL"),
                default_input_max_characters=self.config.get("INPUT_DEFAULT_MAX_CHARACTERS"),
                default_generation_max_output_tokens=self.config.get("GENERATION_DEFAULT_MAX_TOKENS"),
                default_generation_temperature=self.config.get("GENERATION_DEFAULT_TEMPERATURE"),
                generation_model_id=self.config.get("GENEERATION_MODEL_ID")
            )
        elif provider_name == LLMEnum.COHERE.value:
            return CohereProvider(
                api_key=self.config.get("COHERE_API_KEY"),
                default_input_max_characters=self.config.get("INPUT_DEFAULT_MAX_CHARACTERS"),
                default_generation_max_output_tokens=self.config.get("GENERATION_DEFAULT_MAX_TOKENS"),
                default_generation_temperature=self.config.get("GENERATION_DEFAULT_TEMPERATURE")
            )
        else:
            raise ValueError(f"Unknown provider: {provider_name}")      
