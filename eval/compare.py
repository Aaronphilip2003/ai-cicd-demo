"""Diffs eval/results/current.json against eval/results/baseline.json using
the thresholds in eval/thresholds.yml. Prints a markdown table (for posting
as a PR comment) and exits non-zero if any gate is breached.

Usage:
    python -m eval.compare [--current eval/results/current.json]
                           [--baseline eval/results/baseline.json]
                           [--thresholds eval/thresholds.yml]
                           [--out eval/results/pr_comment.md]
"""
import argparse
import json
import sys
from pathlib import Path

import yaml


def _pct_change(new: float, old: float) -> float:
    if old == 0:
        return 0.0 if new == 0 else float("inf")
    return (new - old) / old * 100


def build_report(current: dict, baseline: dict | None, thresholds: dict) -> tuple[str, list[str]]:
    cur = current["summary"]
    breaches = []

    if baseline is None:
        lines = [
            "No baseline found yet — this run's results will become the",
            "baseline once merged to main. No gates were checked.",
            "",
            "| metric | value |",
            "|---|---|",
        ]
        for k, v in cur.items():
            lines.append(f"| {k} | {v} |")
        return "\n".join(lines), breaches

    base = baseline["summary"]
    latency_delta = _pct_change(cur["avg_latency_ms"], base["avg_latency_ms"])
    cost_delta = _pct_change(cur["total_cost_usd"], base["total_cost_usd"])

    rows = [
        ("quality_avg", base["quality_avg"], cur["quality_avg"], ""),
        ("hallucination_rate", base["hallucination_rate"], cur["hallucination_rate"], ""),
        ("tool_success_rate", base["tool_success_rate"], cur["tool_success_rate"], ""),
        ("avg_latency_ms", base["avg_latency_ms"], cur["avg_latency_ms"], f"{latency_delta:+.1f}%"),
        ("total_cost_usd", base["total_cost_usd"], cur["total_cost_usd"], f"{cost_delta:+.1f}%"),
    ]

    lines = ["| metric | baseline | this run | delta |", "|---|---|---|---|"]
    for name, b, c, delta in rows:
        lines.append(f"| {name} | {b} | {c} | {delta} |")

    if cur["quality_avg"] < thresholds["min_quality_avg"]:
        breaches.append(f"quality_avg {cur['quality_avg']} below floor {thresholds['min_quality_avg']}")
    if cur["hallucination_rate"] > thresholds["max_hallucination_rate"]:
        breaches.append(f"hallucination_rate {cur['hallucination_rate']} above ceiling {thresholds['max_hallucination_rate']}")
    if cur["tool_success_rate"] < thresholds["min_tool_success_rate"]:
        breaches.append(f"tool_success_rate {cur['tool_success_rate']} below floor {thresholds['min_tool_success_rate']}")
    if latency_delta > thresholds["max_latency_increase_pct"]:
        breaches.append(f"avg_latency_ms up {latency_delta:.1f}% (max {thresholds['max_latency_increase_pct']}%)")
    if cost_delta > thresholds["max_cost_increase_pct"]:
        breaches.append(f"total_cost_usd up {cost_delta:.1f}% (max {thresholds['max_cost_increase_pct']}%)")

    report = "\n".join(lines)
    if breaches:
        report += "\n\n**Gate FAILED:**\n" + "\n".join(f"- {b}" for b in breaches)
    else:
        report += "\n\n**Gate passed.**"
    return report, breaches


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", default="eval/results/current.json")
    parser.add_argument("--baseline", default="eval/results/baseline.json")
    parser.add_argument("--thresholds", default="eval/thresholds.yml")
    parser.add_argument("--out", default="eval/results/pr_comment.md")
    args = parser.parse_args()

    current = json.loads(Path(args.current).read_text())
    baseline_path = Path(args.baseline)
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else None
    thresholds = yaml.safe_load(Path(args.thresholds).read_text())

    report, breaches = build_report(current, baseline, thresholds)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(report)
    print(report)

    sys.exit(1 if breaches else 0)
