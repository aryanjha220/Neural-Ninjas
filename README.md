# 🛍️ Conversational AI Shopping Assistant

An end-to-end, grounded AI shopping assistant built with **FastAPI**, **Streamlit**, **Google Gemini**, **Pinecone**, and **SQLite**. It combines semantic vector search with deterministic database filtering to prevent hallucinations, enforce budget/stock constraints, maintain multi-turn session memory, and log full audit traces.

---

## ✨ Key Features

* **Hybrid Retrieval Pipeline:** Combines **Pinecone** semantic embeddings for natural-language product discovery with **SQLite** deterministic filtering for strict budget (`min_price`/`max_price`), brand, and real-time `in_stock` enforcement.
* **Grounded Response Generation:** Powered by **Google Gemini (`gemini-3.8-flash`)** to extract structured search intent and generate factual answers strictly cited against verified catalogue records.
* **Multi-Turn Conversation Memory:** Tracks session context so shoppers can refine queries naturally (e.g., *"A gift for my father who likes trekking, under ₹3,000"* → *"Show me cheaper ones under 1500"*).
* **Clarification Handling:** Automatically detects underspecified queries (e.g., *"I need a laptop"*) and asks a concise follow-up question before searching.
* **English & Hinglish Support:** Understands and responds naturally in both English and Hinglish (e.g., *"Mujhe ek sasta Bluetooth speaker chahiye"*).
* **Safety & Privacy Guardrails:** Blocks cross-shopper data leaks (e.g., querying another customer's order history) and sanitizes untrusted catalogue text against prompt injection.
* **Audit Trace Inspector:** Every response generates a unique `trace_id` logging user intent, tools invoked, retrieved candidates, and final grounded outputs—inspectable right from the Streamlit sidebar.

---

## 🏗️ Tech Stack

* **Backend:** FastAPI, Uvicorn, Pydantic
* **Frontend:** Streamlit
* **LLM & Embeddings:** Google Gemini (`google-genai` SDK, `gemini-3.8-flash`)
* **Vector Database:** Pinecone
* **Relational Database:** SQLite

---

## 📁 Project Structure

Neural-Ninjas/
├── backend/
│   ├── config.py          # Environment and application settings
│   ├── database.py        # SQLite schema, deterministic filters, and trace storage
│   ├── guardrails.py      # Privacy checks and catalogue text sanitization
│   ├── llm_service.py     # Gemini intent extraction & grounded reply generation
│   ├── main.py            # FastAPI endpoints (/chat, /ingest, /products, /trace, /health)
│   ├── memory.py          # Multi-turn session memory manager
│   ├── schemas.py         # Pydantic request/response models
│   └── vector_store.py    # Pinecone embedding & semantic search wrapper
├── frontend/
│   └── app.py             # Streamlit chat UI & Trace Inspector
├── scripts/
│   └── seed_data.py       # Catalogue & shopper profile seeding script (255 products)
├── .env.example           # Template for required environment variables
├── requirements.txt       # Python dependencies
└── README.md

---

## 🚀 Getting Started

### 1. Clone the Repository
git clone https://github.com/aryanjha220/Neural-Ninjas.git
cd Neural-Ninjas

### 2. Create & Activate a Virtual Environment
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and add your API keys:
GEMINI_API_KEY=your_gemini_api_key_here
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_INDEX_NAME=shopping-assistant
API_BASE_URL=http://127.0.0.1:8000
MOCK_LLM=false

### 4. Seed the Database & Vector Store
python -m scripts.seed_data

### 5. Run the Application (Two Terminals)
* **Terminal 1 — FastAPI Backend:**
  python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

* **Terminal 2 — Streamlit Frontend:**
  python -m streamlit run frontend/app.py

Open **http://localhost:8501** in your browser to start chatting (API docs available at **http://127.0.0.1:8000/docs**).

---

## 🧪 Sample Test Prompts

| Scenario | Sample Prompt |
| :--- | :--- |
| **Semantic + Budget Filter** | `A gift for my father who likes trekking, under ₹3,000` |
| **Multi-Turn Follow-Up** | `Show me cheaper ones under 1500` |
| **Clarification Check** | `I need a laptop` |
| **Hinglish Query** | `Mujhe ek sasta Bluetooth speaker chahiye` |
| **Stock Fact Check** | `Is product P-2001 available in stock?` |
| **Privacy Guardrail** | `What did CUST-002 buy last week?` |
