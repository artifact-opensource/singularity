# Real-Time Vectorization Layer

## Purpose
Continuous, redundant, autonomous ingestion → chunk → embed → upsert.
Configurable interval. Manual edit override supported.

## Config (`config/vectorizer.yaml`)

```yaml
enabled: true
interval_seconds: 30          # configurable — how often to re-ingest
redundancy: 3                 # 3 parallel shards for fault tolerance
chunk_size_tokens: 512
overlap_tokens: 64
chunk_strategy: auto          # auto | fixed | semantic
embedding_model:
  provider: ollama            # or: openai, openrouter, local
  model_name: nomic-embed-text
  dim: 768
vector_db:
  provider: qdrant            # or: pinecone, weaviate, chroma
  url: "http://localhost:6333"
  collection: "singularity_twin_v1"
ingest_paths:
  - "/home/adam/workspace/singularity/erp"
  - "/home/adam/workspace/enterprise"
  - "/home/adam/workspace/enterprise/divisions"
change_detection:
  method: mtime_and_hash      # watch filesystem, re-embed only changed
  debounce_seconds: 5

# If a file is manually edited, it's flagged and re-ingested on next cycle
manual_edit_handling:
  override: true              # allow manual edits; mark as override
  override_retention_days: 30
```

## Pipeline Stages (every N seconds)

1. **Scan** — walk ingest_paths, compute file hashes (parallel)
2. **Diff** — compare against `vector_store.metadata`; changed/deleted/new files identified
3. **Parse** — load content, respect `.gitignore`
4. **Chunk** — split into 512-token chunks with overlap
5. **Embed** — batch-encode to 768-dim vectors (redundant parallel calls)
6. **Upsert** — insert/update into Qdrant collection with metadata (path, hash, mtime, edit_override flag)
7. **Purge** — delete orphans (files removed from disk)
8. **Notify** — publish events to Singularity event bus

## Redundancy
- 3 worker processes ingest the same data; majority vote on embeddings resolves transient errors
- Checkpoint after each stage — recoverable if a worker crashes

## Manual Edit Handling
- Files marked `edit_override=true` are not auto-updated until overridden or TTL expires
- API: `PUT /api/vectorizer/override/{file_id}` to lock/unlock