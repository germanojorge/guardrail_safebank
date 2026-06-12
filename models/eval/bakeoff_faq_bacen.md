# Embedding Model Bake-off — faq_bacen

Generated: 2026-06-11T22:44:37.130431Z

**Caveat:** E5-vs-MiniLM comparison is not perfectly apples-to-apples (different pretraining recipes). The fine-tune was trained on FAQ_BACEN train split — a strong FAQ_BACEN score may reflect train-distribution overfit.

Latency numbers are indicative CPU latency on the run machine, not a benchmark guarantee.

| Model | dim | prefix_style | recall@5 | MRR@10 | nDCG@10 | latency_ms/q |
|-------|-----|--------------|----------|--------|---------|--------------|
| e5-small (current) | 384 | e5 | 0.6836 | 0.5354 | 0.5891 | 22.7 |
| e5-base | 768 | e5 | 0.7480 | 0.5885 | 0.6390 | 55.2 |
| MiniLM-L12-v2 | 384 | none | 0.4960 | 0.3718 | 0.4222 | 22.3 |
