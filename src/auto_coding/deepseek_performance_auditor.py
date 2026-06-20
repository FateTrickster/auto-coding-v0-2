"""v1.1 — DeepSeek performance auditor."""

from __future__ import annotations

import json
from pathlib import Path


def _jl(p: Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def audit(project_dir: str | Path, run_dir: str) -> dict:
    root = Path(project_dir)
    rd = root / run_dir
    log_dir = rd / "logs"

    a_calls = _jl(log_dir / "deepseek_api_calls.jsonl")
    log_files = list(log_dir.glob("deepseek_api_calls.jsonl"))

    times = [c.get("elapsed_s", 0) for c in a_calls if c.get("elapsed_s")]
    tokens = [c.get("tokens", 0) for c in a_calls if c.get("tokens")]
    sorted_calls = sorted(a_calls, key=lambda c: c.get("elapsed_s", 0), reverse=True)

    # Count cache hits from results
    cache_hits = 0; retries = 0
    for agent in ["A", "B"]:
        fn = rd / f"coder_{agent}_results.jsonl"
        if fn.exists():
            items = _jl(fn)
            cache_hits += sum(1 for r in items if r.get("cache_hit"))
            retries += sum(r.get("retry_count", 0) for r in items)

    result = {
        "total_api_calls": len(a_calls),
        "cache_hit_count": cache_hits,
        "retry_count": retries,
        "total_tokens": sum(tokens),
        "total_runtime_s": round(sum(times), 1),
        "average_latency_s": round(sum(times) / max(len(times), 1), 2),
        "max_latency_s": round(max(times) if times else 0, 2),
        "slowest_10": [{"time": c.get("time",""), "elapsed_s": c.get("elapsed_s",0), "tokens": c.get("tokens",0)}
                       for c in sorted_calls[:10]],
        "throughput_units_per_minute": round(len(a_calls) / max(sum(times) / 60, 1), 1),
    }
    with open(rd / "performance_audit_report.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    (rd / "performance_audit_report.md").write_text(
        f"# Performance Audit\n\n"
        f"- API calls: {result['total_api_calls']}\n"
        f"- Cache hits: {result['cache_hit_count']}\n"
        f"- Total runtime: {result['total_runtime_s']}s\n"
        f"- Avg latency: {result['average_latency_s']}s\n"
        f"- Max latency: {result['max_latency_s']}s\n"
        f"- Tokens: {result['total_tokens']}\n"
        f"- Throughput: {result['throughput_units_per_minute']}/min\n", encoding="utf-8")
    return result
