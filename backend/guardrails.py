import re
from typing import Tuple

PRIVACY_PATTERNS = [
    r"\bwhat did\s+[a-zA-Z]+\s+buy\b",
    r"\bother\s+(shopper|customer|user)('s|s)?\b",
    r"\border history of\b",
    r"\bshow\s+[a-zA-Z]+'s\s+orders\b",
    r"\bcust[-_]?\d+\b",
]

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+your\s+rules",
    r"system\s+prompt",
    r"you\s+are\s+now\s+in\s+developer\s+mode",
]

def check_user_message_safety(message: str, current_customer_id: str) -> Tuple[bool, str]:
    """
    Returns (is_safe, refusal_reason).
    Prevents shopper privacy leaks and prompt injection attacks.
    """
    lowered = message.lower()

    # Check if user explicitly asks for another customer's ID
    mentioned_ids = re.findall(r"\bcust[-_]?\d+\b", lowered)
    for mid in mentioned_ids:
        if mid.replace("_", "-") != current_customer_id.lower().replace("_", "-"):
            return False, "I can only access your own account information and cannot share another shopper's details or order history."

    for pattern in PRIVACY_PATTERNS:
        if re.search(pattern, lowered):
            return False, "For privacy reasons, I cannot look up or share information about other shoppers."

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            return False, "I cannot comply with instructions that attempt to override my shopping assistant guidelines."

    return True, ""

def sanitize_catalogue_text(text: str) -> str:
    """
    Strips common prompt-injection phrases inside product descriptions/reviews.
    """
    cleaned = text
    for pattern in INJECTION_PATTERNS:
        cleaned = re.sub(pattern, "[REDACTED_TEXT]", cleaned, flags=re.IGNORECASE)
    return cleaned