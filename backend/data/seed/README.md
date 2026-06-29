# Seed data

These files are small, synthetic, committed snapshots used so the project runs without network access or private credentials.

- `supply_chain_dataset.csv` is a 100-row Kaggle-style beauty and personal-care supply-chain dataset with SKU, supplier, stock, lead-time, shipping, cost, inspection, and defect-rate fields.
- `freightos_baltic_index.json` is a Freightos-style freight-rate snapshot for container lanes.
- `kaggle_supplychainnet.json` has small historical demand and disruption records.
- `network.json` describes suppliers, facilities, and logistics lanes for local impact mapping.
- `playbooks.json` stores mitigation playbooks used by the recommendation agent.
- `scenarios.json` stores the dashboard and CLI demo scenarios.
- `synthetic_disruption_events.jsonl` contains 300 labeled disruption narratives for classifier experiments.

The values are fabricated for reproducible capstone demos and are not live commercial data.
