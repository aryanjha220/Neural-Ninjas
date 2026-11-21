import uuid
import requests
import streamlit as st

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="AI Shopping Assistant", page_icon="🛍️", layout="wide")
st.title("🛍️ Conversational Shopping Assistant")

if "session_id" not in st.session_state:
    st.session_state.session_id = f"sess-{uuid.uuid4().hex[:6]}"
if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.header("Session Controls")
    customer_id = st.selectbox(
        "Active Shopper ID",
        options=["CUST-001", "CUST-002", "CUST-003", "CUST-004", "CUST-005"],
        index=0,
    )
    st.text_input("Session ID", value=st.session_state.session_id, disabled=True)

    if st.button("New Conversation"):
        st.session_state.session_id = f"sess-{uuid.uuid4().hex[:6]}"
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.subheader("Trace Inspector")
    trace_lookup = st.text_input("Enter Trace ID to inspect")
    if st.button("Fetch Trace") and trace_lookup:
        r = requests.get(f"{API_URL}/trace/{trace_lookup.strip()}", timeout=30)
        if r.status_code == 200:
            st.json(r.json())
        else:
            st.error("Trace ID not found.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "payload" in msg:
            data = msg["payload"]
            st.caption(f"Trace ID: `{data['trace_id']}` | Type: `{data['answer_type']}`")
            if data.get("products"):
                for p in data["products"]:
                    stock_badge = "✅ In Stock" if p["in_stock"] else "❌ Out of Stock"
                    st.info(
                        f"**{p['name']}** (`{p['product_id']}`) — **₹{p['price']}** | {stock_badge}\n\n"
                        f"*{p['reason']}*"
                    )

user_input = st.chat_input("Ask in English or Hinglish (e.g., 'Trekking gift for father under ₹3000')...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Searching catalogue..."):
            try:
                res = requests.post(
                    f"{API_URL}/chat",
                    json={
                        "session_id": st.session_state.session_id,
                        "customer_id": customer_id,
                        "message": user_input,
                    },
                    timeout=90,
                )
                if res.status_code != 200:
                    st.error(f"Backend error ({res.status_code}): {res.text}")
                else:
                    data = res.json()

                    st.markdown(data["answer"])
                    st.caption(f"Trace ID: `{data['trace_id']}` | Type: `{data['answer_type']}`")

                    for p in data.get("products", []):
                        stock_badge = "✅ In Stock" if p["in_stock"] else "❌ Out of Stock"
                        st.info(
                            f"**{p['name']}** (`{p['product_id']}`) — **₹{p['price']}** | {stock_badge}\n\n"
                            f"*{p['reason']}*"
                        )

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": data["answer"],
                        "payload": data,
                    })
            except Exception as e:
                st.error(f"Backend error: {e}")