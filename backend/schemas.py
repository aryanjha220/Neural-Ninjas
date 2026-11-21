from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

AnswerType = Literal[
    "recommendation",
    "comparison",
    "clarification",
    "product_fact",
    "not_found",
    "refusal",
]

class ChatRequest(BaseModel):
    session_id: str
    customer_id: str
    message: str

class ProductRecommendation(BaseModel):
    product_id: str
    name: str
    price: float
    in_stock: bool
    reason: str

class SourceCitation(BaseModel):
    product_id: str
    fields: List[str]

class ChatResponse(BaseModel):
    trace_id: str
    answer_type: AnswerType
    answer: str
    products: List[ProductRecommendation] = []
    sources: List[SourceCitation] = []
    follow_up_question: Optional[str] = None

class ProductIngestItem(BaseModel):
    product_id: str
    name: str
    category: str
    brand: str
    price: float
    stock_count: int
    attributes: Dict[str, Any] = Field(default_factory=dict)
    description: str
    rating: Optional[float] = None

class IngestRequest(BaseModel):
    products: List[ProductIngestItem]