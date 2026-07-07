"""Runs every row in benchmark.jsonl through the agent + judge, and writes
an aggregate results file (the 5 metrics from the CI/CD pipeline).

Usage:
    python -m eval.run_eval [--out eval/results/current.json]
"""
import argparse
import json
from pathlib import Path

from src.agent import run as run_agent
from eval.judge import evaluate as judge_evaluate

BENCHMARK_PATH = Path(__file__).parent / "benchmark.jsonl"
DOCS_DIR = Path(__file__).parent.parent / "docs"


def _load_benchmark():
    rows = []
    with open(BENCHMARK_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _tool_success(row: dict, result: dict) -> bool:
    expected = row.get("expected_tool_call")
    if expected is None:
        return result["tool_called"] is None
    return (
        result["tool_called"] == expected["name"]
        and result["tool_args"] == expected["args"]
    )


def _context_for_judge(result: dict) -> str:
    parts = []
    if result["retrieved_chunks"]:
        for chunk_id in result["retrieved_chunks"]:
            doc_name, _, _ = chunk_id.partition("#")
            path = DOCS_DIR / f"{doc_name}.md"
            if path.exists():
                parts.append(path.read_text())
    if result["tool_result"]:
        parts.append(json.dumps(result["tool_result"]))
    return "\n\n".join(parts)


def run_all() -> dict:
    rows = _load_benchmark()
    per_row = []

    for row in rows:
        result = run_agent(row["question"])
        tool_success = _tool_success(row, result)
        judged = judge_evaluate(
            question=row["question"],
            reference_answer=row["reference_answer"],
            context=_context_for_judge(result),
            answer=result["answer"],
        )
        per_row.append({
            "id": row["id"],
            "tags": row.get("tags", []),
            "question": row["question"],
            "answer": result["answer"],
            "tool_success": tool_success,
            "quality": judged["quality"],
            "hallucinated": judged["hallucinated"],
            "judge_reason": judged["reason"],
            "prompt_tokens": result["prompt_tokens"],
            "completion_tokens": result["completion_tokens"],
            "latency_ms": result["latency_ms"],
            "cost_usd": result["cost_usd"],
            "model": result["model"],
        })

    n = len(per_row)
    summary = {
        "quality_avg": round(sum(r["quality"] for r in per_row) / n, 3),
        "hallucination_rate": round(sum(r["hallucinated"] for r in per_row) / n, 3),
        "tool_success_rate": round(sum(r["tool_success"] for r in per_row) / n, 3),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in per_row) / n, 1),
        "total_cost_usd": round(sum(r["cost_usd"] for r in per_row), 8),
        "n_rows": n,
    }
    return {"summary": summary, "rows": per_row}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="eval/results/current.json")
    args = parser.parse_args()

    results = run_all()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))

    print(json.dumps(results["summary"], indent=2))
