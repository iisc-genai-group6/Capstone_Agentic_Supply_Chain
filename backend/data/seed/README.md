# Committed seed snapshots (`data/seed/`)

Small, **trimmed** offline snapshots the Phase 1c batch loaders read so a batch run
(`uv run agentic-scd-batch`) works **fully offline** — no Kaggle/Freightos download. These
are committed on purpose (unlike the gitignored `data/snapshots/` live pulls); they are the
local-first / always-demoable source of truth for historical seeding.

> **These values are synthetic.** They were **hand-authored**, not downloaded from Freightos
> or Kaggle. Each file's *structure* (field names, lane codes, record kinds) mirrors the
> public source it is modelled on, but every number, date, and description is fabricated for
> offline demoing — they are **not** real quotes or real dataset rows. Swap in real trimmed
> extracts later if needed; the loaders read by field name, so matching the keys is all that
> is required.

These are intentionally tiny, illustrative samples — not full datasets — kept small enough
to commit and to keep tests fast and deterministic.

## Files

### `freightos_baltic_index.json`
- **What:** A handful of weekly **Freightos Baltic Index (FBX)** freight-rate rows across the
  major China/East-Asia container lanes (USD per 40ft container / FEU).
- **Provenance:** **Synthetic** — modelled on the public **Freightos Baltic Index**
  (https://fbx.freightos.com/) for structure only. The rates and changes are fabricated,
  not live quotes.
- **Loader:** `ingestion/batch/freightos.py` → `FREIGHT_INDEX` signals (freight-rate baselines
  for Prophet in Phase 5).

### `kaggle_supplychainnet.json`
- **What:** A small extract of two record kinds — `demand` baseline time-series and
  `disruption` historical KB-history text.
- **Provenance:** **Synthetic** — modelled on the **Kaggle SupplyChainNet / DataCo Smart
  Supply Chain** family of public datasets for structure only. The demand figures and
  disruption text are fabricated, not real dataset rows.
- **Loader:** `ingestion/batch/kaggle.py` → `DATASET` signals (demand baselines +
  persisted KB-history records).

## Boundary (persist, don't embed)

Phase 1c **persists** these to Postgres (the `signals` table) and snapshot files only. It does
**not** embed/index anything — the vector store (Chroma) is stood up later in Phase 4 (impact
KB) and reused in Phase 7 (playbooks). Postgres stays the source of truth; the vector index is
a derived, rebuildable artifact.
