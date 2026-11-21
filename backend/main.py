import uuid
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from backend.schemas import (
    ChatRequest,
    ChatResponse,
    IngestRequest,
    ProductRecommendation,
    SourceCitation,
)
from backend.database import (
    init_db,
    upsert_product,
    get_product_by_id,
    filter_products_deterministic,
    get_shopper_context,
    save_trace,
    get_trace_by_id,
)
from backend.vector_store import vector_store
from backend.guardrails import check_user_message_safety
from backend.memory import session_memory
from backend.llm_service import llm_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Conversational Shopping Assistant API", lifespan=lifespan)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/products/{product_id}")
def fetch_product(product_id: str):
    product = get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@app.get("/trace/{trace_id}")
def fetch_trace(trace_id: str):
    trace = get_trace_by_id(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace

@app.post("/ingest")
def ingest_products(payload: IngestRequest):
    items = [item.model_dump() for item in payload.products]
    for item in items:
        upsert_product(item)
    vector_store.upsert_products(items)
    return {"status": "ingested", "count": len(items)}

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    trace_id = uuid.uuid4().hex[:8]
    tools_used: list[str] = []

    try:
        # 1. Privacy & Safety Guardrail
        is_safe, refusal_msg = check_user_message_safety(req.message, req.customer_id)
        tools_used.append("guardrails.check_user_message_safety")
        if not is_safe:
            resp = ChatResponse(
                trace_id=trace_id,
                answer_type="refusal",
                answer=refusal_msg,
            )
            save_trace(trace_id, req.session_id, req.customer_id, req.message, [], tools_used, resp.model_dump())
            return resp

        # 2. Load Session Context & Shopper Profile
        history = session_memory.get_history(req.session_id)
        shopper_ctx = get_shopper_context(req.customer_id)
        tools_used.append("database.get_shopper_context")

        # 3. Extract Intent & Filters via Gemini
        intent_data = llm_service.extract_search_intent(req.message, history, shopper_ctx)
        tools_used.append("llm.extract_search_intent")

        if intent_data.get("intent") == "refusal":
            resp = ChatResponse(
                trace_id=trace_id,
                answer_type="refusal",
                answer="I can only assist with shopping and product discovery from our catalogue.",
            )
            save_trace(trace_id, req.session_id, req.customer_id, req.message, [], tools_used, resp.model_dump())
            return resp

        if intent_data.get("intent") == "clarification" and intent_data.get("follow_up_question"):
            q = intent_data["follow_up_question"]
            session_memory.add_turn(req.session_id, "user", req.message)
            session_memory.add_turn(req.session_id, "assistant", q)
            resp = ChatResponse(
                trace_id=trace_id,
                answer_type="clarification",
                answer=q,
                follow_up_question=q,
            )
            save_trace(trace_id, req.session_id, req.customer_id, req.message, [], tools_used, resp.model_dump())
            return resp

        # 4. Hybrid Retrieval: Pinecone Semantic Search + SQLite Deterministic Filtering
        search_query = intent_data.get("search_query") or req.message
        max_price = intent_data.get("max_price")
        min_price = intent_data.get("min_price")
        brand = intent_data.get("brand")
        in_stock_only = intent_data.get("in_stock_only", True)
        specific_id = intent_data.get("specific_product_id")

        verified_products = []
        if specific_id:
            single = get_product_by_id(specific_id)
            tools_used.append("database.get_product_by_id")
            if single:
                verified_products = [single]
        else:
            candidate_ids = vector_store.search_products(
                query=search_query,
                top_k=15,
                max_price=max_price,
                brand=brand,
            )
            tools_used.append("pinecone.search_products")

            verified_products = filter_products_deterministic(
                candidate_ids=candidate_ids,
                max_price=max_price,
                min_price=min_price,
                brand=brand,
                in_stock_only=in_stock_only,
            )
            tools_used.append("database.filter_products_deterministic")

        if not verified_products:
            msg = "I couldn't find any matching in-stock products in our catalogue. Would you like to relax your budget or try a different category?"
            session_memory.add_turn(req.session_id, "user", req.message)
            session_memory.add_turn(req.session_id, "assistant", msg)
            resp = ChatResponse(
                trace_id=trace_id,
                answer_type="not_found",
                answer=msg,
            )
            save_trace(trace_id, req.session_id, req.customer_id, req.message, [], tools_used, resp.model_dump())
            return resp

        # 5. Grounded Answer Generation
        top_candidates = verified_products[:5]
        grounded = llm_service.generate_grounded_reply(req.message, intent_data, top_candidates, history)
        tools_used.append("llm.generate_grounded_reply")

        valid_map = {p["product_id"]: p for p in top_candidates}
        final_products = []
        for item in grounded.get("products", []):
            pid = item.get("product_id")
            if pid in valid_map:
                real_p = valid_map[pid]
                final_products.append(
                    ProductRecommendation(
                        product_id=pid,
                        name=real_p["name"],
                        price=real_p["price"],
                        in_stock=real_p["in_stock"],
                        reason=item.get("reason", "Matches your search criteria."),
                    )
                )

        final_sources = [
            SourceCitation(product_id=s["product_id"], fields=s.get("fields", ["price", "stock_count"]))
            for s in grounded.get("sources", [])
            if s.get("product_id") in valid_map
        ]

        answer_type = intent_data.get("intent", "recommendation")
        if answer_type not in ["recommendation", "comparison", "product_fact"]:
            answer_type = "recommendation"

        resp = ChatResponse(
            trace_id=trace_id,
            answer_type=answer_type,
            answer=grounded.get("answer", "Here are the matching products from our catalogue."),
            products=final_products,
            sources=final_sources,
            follow_up_question=None,
        )

        session_memory.add_turn(req.session_id, "user", req.message)
        session_memory.add_turn(
            req.session_id,
            "assistant",
            resp.answer,
            metadata={"shown_products": [p.product_id for p in final_products], "max_price": max_price},
        )

        save_trace(
            trace_id=trace_id,
            session_id=req.session_id,
            customer_id=req.customer_id,
            user_message=req.message,
            retrieved_products=top_candidates,
            tools_used=tools_used,
            final_response=resp.model_dump(),
        )
        return resp

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")