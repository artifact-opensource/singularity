# Competitive Intel Model — MoE Transformer & Fine-Tuning Pipeline

## Purpose
Turn ingested vectors into competitive market intelligence: positioning, threat detection, win/loss analysis, and market sizing.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      COMPETITIVE MODEL PIPELINE                    │
├─────────────────────┬─────────────────────┬───────────────────────┤
│  Vector Ingestion   │   MoE Encoder         │   Decoder / Head       │
│  (from Vectorizer)  │   (8× expert FFNs)   │   (Market Intelligence)│
├─────────────────────┼─────────────────────┼───────────────────────┤
│  Fine-Tuning        │   Baselines         │   Inference           │
│  (adapter LoRA)     │   - Prod             │   - Positioning       │
│                     │   - Standalone       │   - Threat score      │
│                     │   - Custom Company   │   - Win/Loss insight  │
└─────────────────────┴─────────────────────┴───────────────────────┘
```

## Model Options (baseline vs full)

| Config | Provider | Model | MoE? | Training | Inference Cost |
|--------|----------|-------|------|----------|----------------|
| `prod` | openrouter | `anthropic/claude-3.5-sonnet` | No (full) | None — LLM-as-a-service | pay-per-token |
| `prod_mixture` | openrouter | `mistralcommixture/experts` | Yes (4 experts) | LoRA fine-tune on internal data | discounted per-token |
| `standalone` | local | `nousresearch/llama-3.1-8b` | No | Full FT on GPU 1× A100 or 4× RTX 4090 | fixed compute |
| `standalone_mixture` | local | `swift/llamamoe-8b` | Yes (8 experts) | Full FT on 2× A100 | reduced per-token via expert routing |

## Fine-Tuning Pipeline

1. **Collect** — pull recent win/loss notes, competitor docs, market reports (from ERP + external APIs)
2. **Chunk** — 256-token windows with overlap
3. **Adapter** — LoRA (rank=8, α=16) on top of foundation model
4. **Train** — 1‑2 epochs, early-stopping on validation loss
5. **Quantize** — AWQ or GPTQ to 4‑bit for inference
6. **Deploy** — Singularity agent serves via `/api/intel/query`

## Query Interface

```json
POST /api/intel/query
{
  "question": "What are the top 3 threats to our enterprise analytics product in Q4?",
  "context": {
    "company": "artifact_virtual",
    "product": "singularity_erp",
    "timeframe": "Q4 2025",
    "include_sources": true
  }
}
```

Response example:

```json
{
  "positioning": "We dominate mid-market SMB with no-code workflow automation; enterprise segment sees 18% churn risk from Weaviate Cloud",
  "threats": [
    {"entity": "Weaviate Cloud", "threat_score": 0.87, "reason": "Dedicated enterprise tier, GCP/AWS integration"},
    {"entity": "Pinecone Serverless", "threat_score": 0.62, "reason": "Pay-as-you-go model attracting early-stage startups"},
    {"entity": "Jina AI", "threat_score": 0.45, "reason": "Research‑focused embeddings attracting academic collaborations"}
  ],
  "win_loss_insights": [
    "40% of closed‑won deals cited 'no‑code' as primary decision factor",
    "25% of lost deals went to competitor after pricing negotiation"
  ],
  "market_sizing": {
    "tam_usd": 2.3B,
    "sam_usd": 320M,
    "som_usd": 45M
  }
}
```

## Deployment Controls

- `MODE` env var: `prod`, `prod_mixture`, `standalone`, `standalone_mixture`
- `FINETUNED_MODEL_PATH` — path to quantized adapter weights
- `INFERENCE_BACKEND`: `openrouter`, `vllm`, `sglang`
- Health endpoint: `GET /api/intel/health`

## Fallback
- If fine‑tuned model unavailable → serve `BASE_MODEL` (e.g., `claude-3.5-sonnet`) with zero‑shot prompting
- Configurable per-company scope based on GPU / budget constraints