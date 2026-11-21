import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import List, Dict, Any
from google import genai
from google.genai import types
from backend.config import settings
from backend.guardrails import sanitize_catalogue_text

FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]


class LLMService:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None

    def _generate_once(self, model_name: str, prompt: str, temperature: float) -> str:
        response = self.client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=temperature,
            ),
        )
        return response.text

    def _call_with_fallback(self, step_name: str, prompt: str, temperature: float) -> str:
        last_err = None
        for model_name in FALLBACK_MODELS:
            t0 = time.time()
            print(f"[LLM] {step_name} -> calling {model_name}...", flush=True)
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(self._generate_once, model_name, prompt, temperature)
            try:
                text = future.result(timeout=12)
                print(f"[LLM] {step_name} succeeded with {model_name} in {time.time() - t0:.1f}s", flush=True)
                executor.shutdown(wait=False)
                return text
            except FuturesTimeout:
                print(f"[LLM] {step_name} timed out after 12s on {model_name}, switching...", flush=True)
                executor.shutdown(wait=False)
                last_err = TimeoutError(f"{model_name} timed out after 12s")
            except Exception as e:
                executor.shutdown(wait=False)
                last_err = e
                print(f"[LLM] {step_name} error on {model_name}: {e}", flush=True)
        raise last_err

    def extract_search_intent(
        self,
        message: str,
        history: List[Dict[str, Any]],
        shopper_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        if settings.MOCK_LLM or not self.client:
            return self._mock_extract_intent(message, history)

        prompt = f"""
You are the intent parser for an Indian e-commerce shopping assistant.
Analyze the shopper's message and conversation history.

Shopper Profile: {json.dumps(shopper_context)}
Recent Conversation History: {json.dumps(history)}
Current User Message: "{message}"

Return a JSON object with these exact keys:
- "intent": one of ["recommendation", "comparison", "clarification", "product_fact", "refusal"]
- "language": "hi" if Devanagari Hindi, "hinglish" if Hindi words in English script, else "en"
- "search_query": standalone semantic search string combining current query + prior context
- "max_price": number or null
- "min_price": number or null
- "brand": string or null
- "in_stock_only": boolean
- "specific_product_id": string or null
- "follow_up_question": string or null
"""
        try:
            raw_text = self._call_with_fallback("extract_search_intent", prompt, temperature=0.1)
            return json.loads(raw_text)
        except Exception as e:
            print(f"[LLM] Falling back to deterministic intent parser: {e}", flush=True)
            return self._mock_extract_intent(message, history)

    def generate_grounded_reply(
        self,
        message: str,
        intent_data: Dict[str, Any],
        verified_products: List[Dict[str, Any]],
        history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not verified_products:
            return self._mock_generate_reply(intent_data, verified_products)

        if settings.MOCK_LLM or not self.client:
            return self._mock_generate_reply(intent_data, verified_products)

        safe_products = []
        for p in verified_products:
            p_copy = dict(p)
            p_copy["description"] = sanitize_catalogue_text(p_copy["description"])
            safe_products.append(p_copy)

        prompt = f"""
You are a helpful, honest AI shopping assistant.
Reply in the exact language style the shopper used ({intent_data.get('language', 'en')}).

User Message: "{message}"
Detected Intent: "{intent_data.get('intent')}"
Conversation History: {json.dumps(history)}

VERIFIED CATALOGUE PRODUCTS (TRUST ONLY THIS DATA):
{json.dumps(safe_products, indent=2)}

Return a JSON object with keys: "answer" (string), "products" (list of objects with product_id, name, price, in_stock, reason), and "sources" (list of objects with product_id, fields).
"""
        try:
            raw_text = self._call_with_fallback("generate_grounded_reply", prompt, temperature=0.2)
            return json.loads(raw_text)
        except Exception as e:
            print(f"[LLM] Falling back to deterministic reply generator: {e}", flush=True)
            return self._mock_generate_reply(intent_data, verified_products)

    def _mock_extract_intent(self, message: str, history: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        low = message.lower().strip()
        if low in ["i need a laptop", "laptop", "show me phones", "shoes"]:
            return {
                "intent": "clarification",
                "language": "en",
                "search_query": low,
                "max_price": None,
                "min_price": None,
                "brand": None,
                "in_stock_only": True,
                "specific_product_id": None,
                "follow_up_question": "What is your budget and primary use case (e.g., study, office work, or gaming)?",
            }

        max_price = None
        price_match = re.search(r"(?:under|below|less than|within|upto|up to|<=|<|₹|rs\.?)\s*([\d,]+)", low)
        if price_match:
            max_price = float(price_match.group(1).replace(",", ""))
        elif re.search(r"\b\d{3,6}\b", low) and any(w in low for w in ["price", "budget", "cheaper", "sasta"]):
            num_match = re.search(r"\b(\d{3,6})\b", low)
            if num_match:
                max_price = float(num_match.group(1))

        # Carry over prior user topic for follow-ups like "price below 500"
        search_query = message
        if history and len(low.split()) <= 6 and max_price is not None:
            for turn in reversed(history):
                if turn.get("role") == "user" and turn.get("content"):
                    search_query = f"{turn['content']} {message}"
                    break

        return {
            "intent": "comparison" if "compare" in low else "recommendation",
            "language": "hinglish" if any(w in low for w in ["mujhe", "chahiye", "sasta", "dikhao"]) else "en",
            "search_query": search_query,
            "max_price": max_price,
            "min_price": None,
            "brand": None,
            "in_stock_only": True,
            "specific_product_id": None,
            "follow_up_question": None,
        }

    def _mock_generate_reply(
        self, intent_data: Dict[str, Any], verified_products: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if not verified_products:
            budget_note = f" under ₹{int(intent_data['max_price'])}" if intent_data.get("max_price") else ""
            is_hinglish = intent_data.get("language") == "hinglish"
            msg = (
                f"Maaf kijiye, is category mein{budget_note} koi in-stock product available nahi hai. Kripya budget badha kar try karein."
                if is_hinglish
                else f"Sorry, no matching products are currently available in stock{budget_note}. Try increasing your budget or broadening your search."
            )
            return {
                "answer": msg,
                "products": [],
                "sources": [],
            }

        top = verified_products[:3]
        return {
            "answer": f"Here are {len(top)} matching products from our verified catalogue.",
            "products": [
                {
                    "product_id": p["product_id"],
                    "name": p["name"],
                    "price": p["price"],
                    "in_stock": p["in_stock"],
                    "reason": f"Matches your request at ₹{p['price']} (Rating: {p.get('rating', 'N/A')}).",
                }
                for p in top
            ],
            "sources": [
                {"product_id": p["product_id"], "fields": ["price", "stock_count", "description"]}
                for p in top
            ],
        }


llm_service = LLMService()
