"""Naive keyword-overlap retrieval over the local docs/ knowledge base.

Good enough for a demo app: no embeddings, no vector DB. Each doc is split
into sections on '## ' headers, and sections are ranked by how many
question words they share.
"""
import re
from pathlib import Path

DOCS_DIR = Path(__file__).parent.parent / "docs"

STOPWORDS = {
    "a", "an", "the", "to", "of", "in", "on", "for", "and", "or", "is", "are",
    "do", "does", "did", "i", "you", "my", "me", "it", "this", "that", "can",
    "how", "what", "where", "when", "who", "have", "has", "be", "get", "with",
    "at", "from", "am", "will", "would", "should", "there",
}


def _load_chunks():
    chunks = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        text = path.read_text()
        sections = re.split(r"\n(?=## )", text)
        for section in sections:
            section = section.strip()
            if not section:
                continue
            title_match = re.match(r"#+\s*(.+)", section)
            title = title_match.group(1) if title_match else path.stem
            chunk_id = f"{path.stem}#{title.lower().replace(' ', '-')}"
            chunks.append({"id": chunk_id, "text": section})
    return chunks


_CHUNKS = _load_chunks()


def _stem(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def _tokenize(text: str) -> set:
    tokens = {_stem(t) for t in re.findall(r"[a-z0-9]+", text.lower())}
    return tokens - STOPWORDS


def retrieve(question: str, top_k: int = 2) -> list[dict]:
    q_tokens = _tokenize(question)
    scored = []
    for chunk in _CHUNKS:
        overlap = len(q_tokens & _tokenize(chunk["text"]))
        if overlap > 0:
            scored.append((overlap, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]
