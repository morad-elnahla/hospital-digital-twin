# Retrieval evaluation

Run `python db/evaluate_rag.py --k 3 --output docs/rag_eval_results.json` to reproduce this snapshot. The 20 fixed questions and expected source IDs are in `data/rag_eval_questions.json`; a hit means at least one of the top three retrieved chunks belongs to the expected source.

| Language | Hits | Questions | Hit-rate |
|---|---:|---:|---:|
| English | 10 | 10 | 100% |
| Arabic | 0 | 10 | 0% |
| Overall | 10 | 20 | 50% |

The indexed documents contain English text only. Arabic questions currently have no lexical overlap with those chunks in BM25, so Arabic retrieval does not find the expected sources. This evaluation is a measured gap, not a claim of bilingual retrieval support. Add reviewed Arabic source text or a validated multilingual retrieval layer before relying on Arabic source retrieval.
