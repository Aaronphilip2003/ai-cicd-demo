"""The agent: retrieval + optional tool call + Groq (Llama) completion.

run(question) returns not just the answer text, but the metadata bundle the
eval pipeline needs to score quality, hallucination, tool success, latency,
and cost.
"""
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from groq import BadRequestError, Groq

from src.retrieval import retrieve
from src.tools import TOOL_SCHEMAS, TOOL_IMPLS

load_dotenv()

SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system_prompt.md"
MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

# Approximate Groq per-token pricing in USD per token (check current rates at
# https://groq.com/pricing before trusting these for real cost tracking).
PRICING_PER_TOKEN = {
    "llama-3.1-8b-instant": {"prompt": 0.05e-6, "completion": 0.08e-6},
    "llama-3.3-70b-versatile": {"prompt": 0.59e-6, "completion": 0.79e-6},
}

_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def _cost(usage, model: str) -> float:
    rates = PRICING_PER_TOKEN.get(model, PRICING_PER_TOKEN["llama-3.1-8b-instant"])
    return (
        usage.prompt_tokens * rates["prompt"]
        + usage.completion_tokens * rates["completion"]
    )


def run(question: str) -> dict:
    client = _get_client()
    system_prompt = SYSTEM_PROMPT_PATH.read_text()
    chunks = retrieve(question)
    context_text = "\n\n".join(c["text"] for c in chunks) or "(no relevant context found)"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Context:\n{context_text}\n\nQuestion: {question}"},
    ]

    start = time.monotonic()
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
    except BadRequestError:
        # Model attempted a tool call with arguments that don't match the
        # schema (e.g. missing a required field). Groq rejects this
        # server-side instead of returning it. Fall back to a plain
        # completion with no tools, same as a real agent would recover from
        # a failed tool-call attempt instead of giving up entirely.
        response = client.chat.completions.create(model=MODEL, messages=messages)

    prompt_tokens = response.usage.prompt_tokens
    completion_tokens = response.usage.completion_tokens

    tool_called = None
    tool_args = None
    tool_result = None
    msg = response.choices[0].message

    if msg.tool_calls:
        tool_call = msg.tool_calls[0]
        tool_called = tool_call.function.name
        tool_args = json.loads(tool_call.function.arguments)
        try:
            tool_result = TOOL_IMPLS[tool_called](**tool_args)
        except TypeError as e:
            # Model called the tool with args that don't match its actual
            # signature (e.g. wrong/extra keys). Feed the error back like a
            # real tool API would, instead of crashing the agent.
            tool_result = {"error": f"invalid arguments: {e}"}

        messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {"name": tool_called, "arguments": tool_call.function.arguments},
            }
        ]})
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(tool_result),
        })

        response = client.chat.completions.create(model=MODEL, messages=messages)
        prompt_tokens += response.usage.prompt_tokens
        completion_tokens += response.usage.completion_tokens
        msg = response.choices[0].message

    latency_ms = (time.monotonic() - start) * 1000
    usage_totals = type("Usage", (), {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens})()

    return {
        "answer": msg.content,
        "tool_called": tool_called,
        "tool_args": tool_args,
        "tool_result": tool_result,
        "retrieved_chunks": [c["id"] for c in chunks],
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency_ms": round(latency_ms, 1),
        "cost_usd": round(_cost(usage_totals, MODEL), 8),
        "model": MODEL,
    }
