# Eval report 2026-01-01T00:00:00Z

This file shows the report shape. It is not a measured run.

Mode: full. k = 5. Answerable questions: 2. Unanswerable questions: 1.

## Retrieval

| mode | hit rate | recall@k | MRR | nDCG@k |
| --- | --- | --- | --- | --- |
| dense | 0.500 | 0.500 | 0.500 | 0.500 |
| bm25 | 1.000 | 1.000 | 0.750 | 0.815 |
| hybrid | 1.000 | 1.000 | 1.000 | 1.000 |

Ranks that differ across modes:

- apple-variety: dense 1, BM25 2, hybrid 1
- shed-code: dense None, BM25 1, hybrid 1

## Answers

- Faithfulness: 1.000
- Relevance: 0.850
- Citation accuracy: 0.500
- Refusal correctness: 1.000
- Mean answer latency: 420.000 ms
- Mean judge latency: 310.000 ms
- Answer tokens: 900 prompt, 120 completion
- Judge tokens: 1100 prompt, 80 completion

## Thresholds

Failed:

- answer citation_accuracy 0.500 is below 0.700

## Failures

### shed-code

Question: What is the orchard shed gate code?

- the cited document and chunk do not match the expected source

Answer:

The code is 4417 [2].

Judge notes: Cited the wrong chunk.
