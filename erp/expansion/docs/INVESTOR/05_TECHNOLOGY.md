# Technology Architecture

## Core Stack

- **Language**: Python 3.11+ (primary runtime), TypeScript/Node.js (ERP backend)
- **AI Runtime**: Singularity Python engine (`singularity/` directory)
- **Vector Database**: Qdrant (or Pinecone / Weaviate alternatives)
- **Embedding Model**: Nomic-embed-text (768-dim) via Ollama / OpenRouter
- **Simulation Engine**: Pure Python, autonomous, non-blocking
- **Redundancy**: 3 parallel worker processes

## Component Details

### Department Mapper
- YAML config (`mapper/CONFIG.md`)
- API endpoint: `PUT /api/dept/mapping`
- Real-time propagation to simulation engine

### Digital Twin Engine (`simulator.py`)
- `SimulationScenario` dataclass with budget, channels, deployment, duration
- Four modules: MarketResponse, ResourceCapacity, DeadlineEstimator, CustomerNPSModel
- Returns trajectory curves + impact assessment + risk flags

### Vectorization (`vectorizer.py`)
- Continuous scan → hash → chunk → embed → upsert
- 512-token chunks, 64-token overlap
- Configurable interval (30s default)
- 3 redundant workers

### Competitive Intel (`intel_model`)
- MoE (Mixture of Experts) — 8 expert FFN layers
- Fine-tuning: LoRA adapter, quantized deployment
- Query interface: `POST /api/intel/query`

## Integration Points

- ERP backend (`erp/backend/`) proxies AI chat to Singularity (`localhost:8450`)
- ERP studio frontend (`erp/studio/`) communicates through backend only
- Singularity maintains full session context and passes through to agents
- All expansion components run inside Singularity context, not externally
