import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db.evaluate_rag import evaluate


def test_multilingual_query_expansion_retrieves_expected_sources_for_both_languages():
    result = evaluate(k=3)
    assert result["questions"] == 20
    assert result["by_language"]["en"]["questions"] == 10
    assert result["by_language"]["ar"]["questions"] == 10
    assert result["by_language"]["en"]["hits"] == 10
    assert result["by_language"]["ar"]["hits"] == 10
    assert all(row["expected_source_id"] in {"src001", "src002"} for row in result["results"])
