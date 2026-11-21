import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
    PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "shopping-catalogue")
    MOCK_LLM: bool = os.getenv("MOCK_LLM", "false").lower() == "true"
    DB_PATH: str = os.getenv("DB_PATH", "data/shop.db")
    API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000")

settings = Settings()