import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_mistralai import ChatMistralAI

from enums.llm_type import LLMType



class LLMConnector:
    """
    Connector for various language models (LLMs) such as OpenAI GPT and GROQ AI.

    Attributes:
        model (object): The language model to be used.
        temperature (float): The creativity level of the model. Default is 0.0.
        api_key (str): The API key for OpenAI/GROQ. Default is None.
        llm_type (LLMType): The type of language model to be used. Default is LLMType.GROQ_AI.
    """
    def __init__(self, model_name: str,
                temperature: float = 0,
                llm_type: LLMType = LLMType.GROQ_AI,
                api_key: str = None,
                max_retries: int = 3,
                llm_kwargs: Optional[Dict[str, Any]] = None,
                ):
        load_dotenv()
        
        self.model = model_name
        
        self.llm_type = llm_type
        if api_key is None:
            
            if self.llm_type == LLMType.OPEN_AI:
                self.api_key = os.getenv("OPENAI_API_KEY")
            elif self.llm_type == LLMType.MISTRAL:
                self.api_key = os.getenv("MISTRAL_API_KEY")
         
            else:
                self.api_key =  os.getenv("GROQ_API_KEY")
        else:
            self.api_key = api_key
        if os.getenv("LLM_TEMPERATURE") is not None:
            self.temperature = os.getenv("LLM_TEMPERATURE")
        else:
            self.temperature = temperature
                    
        self.max_retries = max_retries
        self.llm_kwargs = llm_kwargs or {}

    
    def __call__(self) -> object:
        if not self.model:
            raise ValueError("Model is not defined")

        if not self.api_key:
            raise ValueError("API key is not defined")
        
        try:
            if self.llm_type == LLMType.OPEN_AI:
                return self.get_openai_llm()
            elif self.llm_type == LLMType.MISTRAL:
                return self.get_mistral_llm()
            else:
                return self.get_groq_llm()
        except Exception as e:
            raise ValueError(f"Failed to initialize LLM: {e}")
    
    def get_openai_llm(self) -> object:
        """
        ✅ CORRECTION: Configuration simple sans tool_choice
        OpenAI rejette tool_choice si aucun tool n'est défini
        """
        return ChatOpenAI(
            model_name=self.model,
            openai_api_key=self.api_key,
            temperature=self.temperature,
            max_retries=self.max_retries,
            **self.llm_kwargs,
        )
    
    def get_groq_llm(self) -> object:
        """
        ✅ Configuration simple pour Groq
        """
        return ChatGroq(
            model=self.model, 
            temperature=self.temperature,
            api_key=self.api_key,
            max_retries=self.max_retries,
            **self.llm_kwargs,
        )
    
    def get_mistral_llm(self) -> object:
        """
        ✅ Configuration simple pour Mistral
        """
        return ChatMistralAI(
            model=self.model,
            api_key=self.api_key,
            temperature=self.temperature,
            max_retries=self.max_retries,
            **self.llm_kwargs,
        )