from enum import Enum

class LLMType(Enum):
    OPEN_AI = 1
    GROQ_AI = 2
    MISTRAL = 3
 
    
    @classmethod
    def from_string(cls, name: str):
        """Convert string (case-insensitive) to LLMType."""
        normalized = name.strip().lower()
        mapping = {
            "openai": cls.OPEN_AI,
            "groq": cls.GROQ_AI,
            "mistral": cls.MISTRAL,
           
        }
        if normalized not in mapping:
            raise ValueError(f"Unknown LLM type: {name}")
        return mapping[normalized]