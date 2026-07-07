"""LLM-judge: scores answer quality and flags unsupported (hallucinated) claims.

Uses a separate Groq call, kept deliberately simple: ask for JSON, parse it,
fall back to a conservative score if parsing fails so a flaky judge response
doesn't crash the whole eval run.
"""
import json
import os

from groq import Groq

JUDGE_MODEL = os.environ.get("GROQ_JUDGE_MODEL", "llama-3.3-70b-versatile")

JUDGE_PROMPT = """You are grading a customer support assistant's answer.

Question: {question}
Reference (correct) answer: {reference_answer}
Context/tool result the assistant had available: {context}
Assistant's actual answer: {answer}

Score the assistant's answer from 1-5 on correctness/quality compared to the
reference answer (5 = fully correct and complete, 1 = wrong or unhelpful).

Also determine whether the assistant's answer contains any claim (a fact,
number, date, or policy detail) that is NOT supported by the context/tool
result provided. Minor rephrasing is fine; invented specifics are not.

Respond with ONLY a JSON object, no other text:
{{"quality": <int 1-5>, "hallucinated": <true or false>, "reason": "<one short sentence>"}}
"""


def evaluate(question: str, reference_answer: str, context: str, answer: str) -> dict:
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    prompt = JUDGE_PROMPT.format(
        question=question,
        reference_answer=reference_answer,
        context=context or "(none)",
        answer=answer or "(empty)",
    )
    response = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    raw = response.choices[0].message.content.strip()
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        parsed = json.loads(raw[start:end])
        return {
            "quality": int(parsed["quality"]),
            "hallucinated": bool(parsed["hallucinated"]),
            "reason": parsed.get("reason", ""),
        }
    except (ValueError, KeyError, json.JSONDecodeError):
        return {"quality": 1, "hallucinated": True, "reason": f"judge parse failure: {raw[:200]}"}
