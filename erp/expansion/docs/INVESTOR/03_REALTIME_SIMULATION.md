# Real-Time Work + Simulation — Side by Side

The core innovation is that Singularity does not choose between **operating the business** and **simulating the future**. It does both simultaneously, continuously.

## Real-Time Operations

Every 30 seconds (configurable), redundant vector workers scan all files in `singularity/erp/` and `enterprise/`. They:
1. Compute file hashes
2. Detect changes
3. Chunk into 512-token windows with overlap
4. Embed into 768-dimension vectors
5. Upsert into the vector database
6. Trigger event notifications

This means the company always has an up-to-date vector representation of all documentation, contracts, workflows, and data.

## Simulation Analysis

When a scenario is triggered (`POST /api/twin/simulate`), the simulation engine uses the live digital twin (not a static model) to compute:
- Revenue curves based on real budget, market, and team capacity
- Headcount projections based on actual department structures
- Deadline shifts based on real engineer workload and skill mapping
- Customer NPS projections based on real product features and support quality

## How They Work Together

The real-time vector layer feeds the digital twin. The digital twin feeds the simulation engine. The competitive intelligence model reads from both to provide strategic analysis.

So at any moment, a CEO asking "What if we launch this new product?" receives an answer based on:
- **Real-time company data** (not estimates)
- **Actual team capacity** (not generic capacity)
- **Live market intelligence** (not quarterly reports)

This is what makes Singularity effective: it doesn't simulate with templates. It simulates with the real company.
