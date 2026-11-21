import time
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from pinecone import Pinecone, ServerlessSpec
from backend.config import settings

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768

class VectorStore:
    def __init__(self):
        self.genai_client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None
        self.pc = Pinecone(api_key=settings.PINECONE_API_KEY) if settings.PINECONE_API_KEY else None
        self.index_name = settings.PINECONE_INDEX_NAME
        self._index = None

    def _get_index(self):
        if not self.pc:
            return None
        if self._index is not None:
            return self._index

        existing = [idx["name"] for idx in self.pc.list_indexes()]
        if self.index_name not in existing:
            self.pc.create_index(
                name=self.index_name,
                dimension=EMBEDDING_DIM,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
            for _ in range(15):
                desc = self.pc.describe_index(self.index_name)
                if desc.status["ready"]:
                    break
                time.sleep(1)

        self._index = self.pc.Index(self.index_name)
        return self._index

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if settings.MOCK_LLM or not self.genai_client:
            return [[0.01] * EMBEDDING_DIM for _ in texts]

        for attempt in range(3):
            try:
                response = self.genai_client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=texts,
                    config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM),
                )
                return [e.values for e in response.embeddings]
            except ClientError as e:
                if "429" in str(e) and attempt < 2:
                    print("Rate limit hit (100/min free tier). Waiting 65 seconds to resume...")
                    time.sleep(65)
                else:
                    raise

    def embed_text(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    def upsert_products(self, products: List[Dict[str, Any]]) -> None:
        index = self._get_index()
        if not index:
            return

        batch_size = 45
        for i in range(0, len(products), batch_size):
            batch = products[i : i + batch_size]
            print(f"Embedding & uploading products {i + 1} to {i + len(batch)} of {len(products)}...")
            doc_texts = [
                f"{p['name']} | Brand: {p['brand']} | Category: {p['category']} | "
                f"Price: {p['price']} | Description: {p['description']} | "
                f"Attributes: {p.get('attributes', {})}"
                for p in batch
            ]
            embeddings = self.embed_batch(doc_texts)

            vectors = []
            for p, vec in zip(batch, embeddings):
                vectors.append({
                    "id": p["product_id"],
                    "values": vec,
                    "metadata": {
                        "product_id": p["product_id"],
                        "category": p["category"].lower(),
                        "brand": p["brand"].lower(),
                        "price": float(p["price"]),
                        "in_stock": int(p["stock_count"]) > 0,
                    },
                })
            index.upsert(vectors=vectors)

            # Stay under 100 items/min free tier quota between batches
            if i + batch_size < len(products):
                time.sleep(32)

    def search_products(
        self,
        query: str,
        top_k: int = 15,
        max_price: Optional[float] = None,
        brand: Optional[str] = None,
    ) -> List[str]:
        index = self._get_index()
        if not index:
            return []

        query_vec = self.embed_text(query)
        pinecone_filter: Dict[str, Any] = {}
        if max_price is not None:
            pinecone_filter["price"] = {"$lte": float(max_price)}
        if brand:
            pinecone_filter["brand"] = {"$eq": brand.strip().lower()}

        res = index.query(
            vector=query_vec,
            top_k=top_k,
            filter=pinecone_filter if pinecone_filter else None,
            include_metadata=False,
        )
        return [match["id"] for match in res.get("matches", [])]

vector_store = VectorStore()