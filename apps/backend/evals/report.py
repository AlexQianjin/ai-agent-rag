"""Console summary and JSON / Markdown reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        f"# Eval report {report['created_at']}",
        "",
        f"Mode: {report['mode']}. k = {report['k']}. Answerable questions: {report['answerable_count']}. "
        f"Unanswerable questions: {report['unanswerable_count']}.",
        "",
        "## Retrieval",
        "",
        "| mode | hit rate | recall@k | MRR | nDCG@k |",
        "| --- | --- | --- | --- | --- |",
    ]
    for mode in ("dense", "bm25", "hybrid"):
        row = metrics[mode]
        lines.append(
            f"| {mode} | {_fmt(row['hit_rate'])} | {_fmt(row['recall_at_k'])} | {_fmt(row['mrr'])} | {_fmt(row['ndcg_at_k'])} |"
        )
    answer = metrics.get("answer") or {}
    gaps = [
        row
        for row in report["cases"]
        if not row.get("unanswerable")
        and (row.get("dense_rank") != row.get("bm25_rank") or row.get("hybrid_rank") != row.get("dense_rank"))
    ]
    if gaps:
        lines.extend(["", "Ranks that differ across modes:", ""])
        for row in gaps:
            lines.append(
                f"- {row['id']}: dense {row.get('dense_rank')}, BM25 {row.get('bm25_rank')}, hybrid {row.get('hybrid_rank')}"
            )
    lines.extend(["", "## Answers", ""])
    if answer.get("faithfulness") is None:
        lines.append("Answer judging was not run.")
    else:
        lines.extend(
            [
                f"- Faithfulness: {_fmt(answer['faithfulness'])}",
                f"- Relevance: {_fmt(answer['relevance'])}",
                f"- Citation accuracy: {_fmt(answer['citation_accuracy'])}",
                f"- Refusal correctness: {_fmt(answer['refusal_correctness'])}",
                f"- Mean answer latency: {_fmt(answer['mean_answer_latency_ms'])} ms",
                f"- Mean judge latency: {_fmt(answer['mean_judge_latency_ms'])} ms",
                f"- Answer tokens: {_fmt_int(answer.get('answer_prompt_tokens'))} prompt, "
                f"{_fmt_int(answer.get('answer_completion_tokens'))} completion",
                f"- Judge tokens: {_fmt_int(answer.get('judge_prompt_tokens'))} prompt, "
                f"{_fmt_int(answer.get('judge_completion_tokens'))} completion",
            ]
        )
    lines.extend(["", "## Thresholds", ""])
    if report["passed"]:
        lines.append("Passed.")
    else:
        lines.append("Failed:")
        for item in report["threshold_failures"]:
            lines.append(f"- {item}")
    lines.extend(["", "## Failures", ""])
    failed = [row for row in report["cases"] if row.get("failure_reasons")]
    if not failed:
        lines.append("No per-case failures.")
    else:
        for row in failed:
            lines.append(f"### {row['id']}")
            lines.append("")
            lines.append(f"Question: {row['question']}")
            lines.append("")
            for reason in row["failure_reasons"]:
                lines.append(f"- {reason}")
            if row.get("answer"):
                lines.append("")
                lines.append("Answer:")
                lines.append("")
                lines.append(row["answer"])
            if row.get("notes"):
                lines.append("")
                lines.append(f"Judge notes: {row['notes']}")
            lines.append("")
    lines.append("")
    return "\n".join(lines)


def write_reports(report: dict[str, Any], directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = directory / f"{stamp}.json"
    markdown_path = directory / f"{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def print_summary(report: dict[str, Any]) -> None:
    print()
    print(f"Retrieval (k={report['k']}, n={report['answerable_count']})")
    print(f"{'mode':<8} {'hit_rate':>8} {'recall@k':>8} {'MRR':>8} {'nDCG@k':>8}")
    for mode in ("dense", "bm25", "hybrid"):
        row = report["metrics"][mode]
        print(
            f"{mode:<8} {_fmt(row['hit_rate']):>8} {_fmt(row['recall_at_k']):>8} "
            f"{_fmt(row['mrr']):>8} {_fmt(row['ndcg_at_k']):>8}"
        )
    answer = report["metrics"].get("answer") or {}
    if answer.get("faithfulness") is None:
        print("\nAnswers: skipped")
    else:
        print(
            "\nAnswers "
            f"faithfulness={_fmt(answer['faithfulness'])} "
            f"relevance={_fmt(answer['relevance'])} "
            f"citation={_fmt(answer['citation_accuracy'])} "
            f"refusal={_fmt(answer['refusal_correctness'])}"
        )
        print(
            f"latency answer={_fmt(answer['mean_answer_latency_ms'])} ms "
            f"judge={_fmt(answer['mean_judge_latency_ms'])} ms"
        )
    if report["passed"]:
        print("\nThresholds: passed")
    else:
        print("\nThresholds: failed")
        for item in report["threshold_failures"]:
            print(f"- {item}")
    failed = [row for row in report["cases"] if row.get("failure_reasons")]
    if failed:
        print(f"\nCase failures: {len(failed)}")
        for row in failed:
            print(f"- {row['id']}: {'; '.join(row['failure_reasons'])}")


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.3f}"


def _fmt_int(value: object) -> str:
    if value is None:
        return "n/a"
    return str(int(value))
