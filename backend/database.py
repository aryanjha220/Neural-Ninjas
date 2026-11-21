import os
import json
import sqlite3
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from backend.config import settings

def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        product_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        brand TEXT NOT NULL,
        price REAL NOT NULL,
        stock_count INTEGER NOT NULL,
        attributes TEXT NOT NULL,
        description TEXT NOT NULL,
        rating REAL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS shoppers (
        customer_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        preferred_language TEXT NOT NULL,
        budget_tier TEXT NOT NULL,
        preferences TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        product_id TEXT NOT NULL,
        order_date TEXT NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES shoppers(customer_id),
        FOREIGN KEY (product_id) REFERENCES products(product_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS traces (
        trace_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        customer_id TEXT NOT NULL,
        user_message TEXT NOT NULL,
        retrieved_products TEXT NOT NULL,
        tools_used TEXT NOT NULL,
        final_response TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()

def upsert_product(product: Dict[str, Any]) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO products (product_id, name, category, brand, price, stock_count, attributes, description, rating)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(product_id) DO UPDATE SET
        name=excluded.name,
        category=excluded.category,
        brand=excluded.brand,
        price=excluded.price,
        stock_count=excluded.stock_count,
        attributes=excluded.attributes,
        description=excluded.description,
        rating=excluded.rating
    """, (
        product["product_id"],
        product["name"],
        product["category"],
        product["brand"],
        float(product["price"]),
        int(product["stock_count"]),
        json.dumps(product.get("attributes", {})),
        product["description"],
        product.get("rating"),
    ))
    conn.commit()
    conn.close()

def get_product_by_id(product_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE product_id = ?", (product_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["attributes"] = json.loads(data["attributes"])
    data["in_stock"] = data["stock_count"] > 0
    return data

def filter_products_deterministic(
    candidate_ids: List[str],
    max_price: Optional[float] = None,
    min_price: Optional[float] = None,
    brand: Optional[str] = None,
    in_stock_only: bool = True,
) -> List[Dict[str, Any]]:
    """
    Deterministic SQLite lookup and hard constraint filtering.
    Preserves the semantic ranking order from Pinecone candidate_ids.
    """
    conn = get_connection()
    cur = conn.cursor()

    query = "SELECT * FROM products WHERE 1=1"
    params: List[Any] = []

    if candidate_ids:
        placeholders = ",".join("?" for _ in candidate_ids)
        query += f" AND product_id IN ({placeholders})"
        params.extend(candidate_ids)

    if max_price is not None:
        query += " AND price <= ?"
        params.append(float(max_price))

    if min_price is not None:
        query += " AND price >= ?"
        params.append(float(min_price))

    if brand:
        query += " AND LOWER(brand) = LOWER(?)"
        params.append(brand.strip())

    if in_stock_only:
        query += " AND stock_count > 0"

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    products_by_id = {}
    for row in rows:
        item = dict(row)
        item["attributes"] = json.loads(item["attributes"])
        item["in_stock"] = item["stock_count"] > 0
        products_by_id[item["product_id"]] = item

    # Preserve Pinecone relevance ranking order
    if candidate_ids:
        return [products_by_id[pid] for pid in candidate_ids if pid in products_by_id]
    return list(products_by_id.values())

def get_shopper_context(customer_id: str) -> Dict[str, Any]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM shoppers WHERE customer_id = ?", (customer_id,))
    shopper = cur.fetchone()
    if not shopper:
        conn.close()
        return {"customer_id": customer_id, "known": False, "past_orders": []}

    cur.execute("""
        SELECT o.order_id, o.order_date, p.product_id, p.name, p.category, p.brand, p.price, p.stock_count
        FROM orders o
        JOIN products p ON o.product_id = p.product_id
        WHERE o.customer_id = ?
        ORDER BY o.order_date DESC
    """, (customer_id,))
    orders = [dict(r) for r in cur.fetchall()]
    conn.close()

    result = dict(shopper)
    result["known"] = True
    result["past_orders"] = orders
    return result

def save_trace(
    trace_id: str,
    session_id: str,
    customer_id: str,
    user_message: str,
    retrieved_products: List[Dict[str, Any]],
    tools_used: List[str],
    final_response: Dict[str, Any],
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO traces (trace_id, session_id, customer_id, user_message, retrieved_products, tools_used, final_response, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trace_id,
        session_id,
        customer_id,
        user_message,
        json.dumps(retrieved_products),
        json.dumps(tools_used),
        json.dumps(final_response),
        datetime.now(timezone.utc).isoformat(),
    ))
    conn.commit()
    conn.close()

def get_trace_by_id(trace_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM traces WHERE trace_id = ?", (trace_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["retrieved_products"] = json.loads(data["retrieved_products"])
    data["tools_used"] = json.loads(data["tools_used"])
    data["final_response"] = json.loads(data["final_response"])
    return data