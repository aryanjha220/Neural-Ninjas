import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
    PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "shopping-assistant")
    MOCK_LLM: bool = os.getenv("MOCK_LLM", "false").lower() == "true"
    DB_PATH: str = os.getenv("DB_PATH", "data/shopping_assistant.db")
    API_BASE_URL: str = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

settings = Settings()
