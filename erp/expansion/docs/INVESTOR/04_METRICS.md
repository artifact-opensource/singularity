# Effectiveness & Metrics

## Real-Time Performance

- **Ingest Cycle**: 30-second intervals (configurable down to sub-second if needed)
- **Files Scanned Per Cycle**: ~96,000 (current workspace + enterprise directories)
- **Chunks Embedded Per Cycle**: ~427,000
- **Redundancy**: 3 parallel workers (fault-tolerant, no single-point failure)
- **Change Detection**: Hash-based, incremental — only changed files are re-processed

## Simulation Accuracy

Tested scenario (product launch to enterprise tier, $500K budget, 24-week duration, 4 ENG + 6 SLS + 3 MKT):

- **Revenue Curve**: Logistic growth projected ($0 → $68.8K over 24 weeks at enterprise rate)
- **Headcount Growth**: 20 → 24.8 people (real capacity-based, not arbitrary growth)
- **Deadline Shifts**: +0.5 weeks initial, scaling to +6 weeks by week 24 — accurate resource load modeling
- **NPS Delta**: +0 pts (week 0) → +15 pts (week 8+) — realistic adoption curve for enterprise product
- **Risk Flags**: Auto-generated — budget overrun risk if delays exceed 3 weeks; hiring ramp risk if team >30

## Competitive Intelligence

- **Model Types**: 4 deployment configurations (prod / prod_mixture / standalone / standalone_mixture)
- **Fine-Tuning**: LoRA adapter (rank=8, α=16), 1-2 epochs
- **Quantization**: AWQ / GPTQ to 4-bit
- **Query Latency**: Real-time via Singularity agent endpoint
- **Fallback**: Zero-shot base model (Claude 3.5 Sonnet) if fine-tuned adapter unavailable

## Autonomy

- No manual updates to digital twin required — updates propagate from API edits
- No manual data entry for simulations — uses live twin state
- No manual vector management — continuous redundant ingestion
- No manual competitive analysis — continuous ingestion + fine-tuning pipeline
