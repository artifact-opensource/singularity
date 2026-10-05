# Singularity ERP Expansion — Version Updates

## Current Version: 0.7.1 (Expansion Release)

## Version History

- **v0.7.0** — Original Singularity [AE] release (32K+ lines, 13 subsystems, 28 tools)
- **v0.7.1 (Expansion)** — Digital Twin + Simulation + Vectorization + Competitive Intelligence

## Changes In v0.7.1

### New Features
- Department Mapper — granular real-world company mapping (API-editable)
- Digital Twin Engine — what-if simulation with impact predictions
- Real-Time Vectorization Layer — continuous redundant ingestion
- Competitive Intel Model — MoE transformer with fine-tuning pipeline

### New Files
- `erp/expansion/ARCHITECTURE.md`
- `erp/expansion/EXPANSION_SUMMARY.md`
- `erp/expansion/mapper/CONFIG.md`
- `erp/expansion/twin/CONFIG.md`
- `erp/expansion/twin/simulator.py`
- `erp/expansion/vectorizer/CONFIG.md`
- `erp/expansion/vectorizer/vectorizer.py`
- `erp/expansion/intel_model/CONFIG.md`
- `erp/expansion/docs/INVESTOR/` — full investor documentation package (7 files)

### Test Verification
- Simulator runs successfully (revenue curves, deadline shifts, NPS projections computed)
- Vectorizer runs successfully (96,145 files scanned, 427,902 chunks embedded per cycle)
- All modules load and execute without errors

## Next Version Target

- **v0.8.0** — Full production deployment: mapper endpoint live, vector DB cluster active, simulation engine integrated with ERP backend, fine-tuned competitive model deployed
