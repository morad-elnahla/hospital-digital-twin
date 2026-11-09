# Retrieval evaluation

Run `python db/evaluate_rag.py --k 3 --output docs/rag_eval_results.json` to reproduce this snapshot. The 20 fixed questions and expected source IDs are in `data/rag_eval_questions.json`; a hit means at least one of the top three retrieved chunks belongs to the expected source.

| Language | Before hits / rate | After hits / rate | Questions |
|---|---:|---:|---:|
| English | 10/10 · 100% | 10/10 · 100% | 10 |
| Arabic | 0/10 · 0% | 10/10 · 100% | 10 |
| Overall | 10/20 · 50% | 20/20 · 100% | 20 |

The source documents remain English-only. Arabic queries now use a small lexical expansion map in `data/rag_arabic_query_map.json`; its terms are marked **machine-translated, needs clinical review**. It only adds English search terms and does not translate, summarize, or alter retrieved evidence. Citations still point to the original source chunks. The 20-query top-3 evaluation improved Arabic retrieval from 0% to 100% with no new clinical content.
