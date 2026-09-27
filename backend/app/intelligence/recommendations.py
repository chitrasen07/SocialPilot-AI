"""Product names that already appear in knowledge documents.

A name is recommended only when that same name is in a ready knowledge chunk and it also
appears in the conversation or an approved memory. Nothing is invented.
"""

import re

_LINE = re.compile(r"(?im)^(?:product|item)\s*:\s*(.{2,80})$")
_WORD = re.compile(r"[a-z0-9][a-z0-9'-]{2,}")
_STOP = {
    "about",
    "available",
    "availability",
    "have",
    "hello",
    "help",
    "item",
    "kitna",
    "much",
    "need",
    "order",
    "price",
    "pricing",
    "product",
    "products",
    "stock",
    "thanks",
    "this",
    "want",
    "what",
    "with",
    "your",
}


def recommend(context: str, memories: list[str], documents: list[str]) -> list[dict]:
    catalog = _catalog(documents)
    if not catalog:
        return []
    context_text = (context or "").lower()
    memory_text = "\n".join(memories).lower()
    found: list[dict] = []
    seen: set[str] = set()
    for name in catalog:
        key = name.lower()
        if key in seen:
            continue
        tokens = [token for token in _WORD.findall(key) if token not in _STOP and len(token) >= 4]
        if not tokens:
            continue
        in_context = key in context_text or any(token in context_text for token in tokens)
        in_memory = key in memory_text or any(token in memory_text for token in tokens)
        if not in_context and not in_memory:
            continue
        seen.add(key)
        if in_context:
            reason = "Listed in the knowledge base and mentioned in the conversation."
            confidence = 0.85
        else:
            reason = "Listed in the knowledge base and matches an approved memory."
            confidence = 0.7
        found.append({"product_name": name.strip(), "reason": reason, "confidence": confidence})
    return found[:5]


def _catalog(documents: list[str]) -> list[str]:
    names: list[str] = []
    for document in documents:
        for match in _LINE.finditer(document or ""):
            name = " ".join(match.group(1).split())
            if name:
                names.append(name[:120])
    return names
