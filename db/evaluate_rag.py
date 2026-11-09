"""Run the versioned bilingual retrieval smoke evaluation."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hospital_agents.policies import CorpusRetriever


def evaluate(k: int = 3) -> dict:
    corpus_path = ROOT / "data" / "combined.json"
    questions_path = ROOT / "data" / "rag_eval_questions.json"
    corpus = CorpusRetriever(corpus_path)
    metadata = json.loads(corpus_path.read_text(encoding="utf-8"))
    source_by_chunk = {c["id"]: c["source_id"] for c in metadata["chunks"]}
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    report = defaultdict(lambda: {"questions": 0, "hits": 0})
    rows = []
    for item in questions:
        found = asyncio.run(corpus.search(item["question"], k))
        source_ids = list(dict.fromkeys(source_by_chunk[p.doc_id] for p in found if p.doc_id in source_by_chunk))
        hit = item["expected_source_id"] in source_ids
        group = report[item["language"]]
        group["questions"] += 1
        group["hits"] += int(hit)
        rows.append({**item, "hit": hit, "retrieved_source_ids": source_ids})
    return {"k": k, "questions": len(questions),
            "by_language": {lang: {**values, "hit_rate": round(values["hits"] / values["questions"], 3)}
                            for lang, values in sorted(report.items())}, "results": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(args.k)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(json.dumps({"k": result["k"], "questions": result["questions"], "by_language": result["by_language"]}, ensure_ascii=False))
