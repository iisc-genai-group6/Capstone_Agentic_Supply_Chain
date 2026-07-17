from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import gradio as gr
import pandas as pd

from agentic_scd.__main__ import run
from agentic_scd.config import get_settings
from agentic_scd.config.localfirst import CONFIG_FIELDS, apply_runtime_env, local_env_path
from agentic_scd.db import connect, init_db, ping
from agentic_scd.ingestion.collect import collect
from agentic_scd.ingestion.paths import SEED_DIR, lexicon_yaml_path, run_dir, snapshot_dir, sources_yaml_path
from agentic_scd.ingestion.relevance import load_lexicon
from agentic_scd.ingestion.store import recent_runs, recent_signals, serialize_state
from agentic_scd.llm.client import completion
from agentic_scd.rag.retriever import (
    forecast_retriever,
    history_retriever,
    impact_retriever,
    mitigation_retriever,
    news_retriever,
    retrieval_mode,
    retriever_stats,
    simulation_retriever,
    weather_retriever,
)
from agentic_scd.runtime_warnings import suppress_known_dependency_warnings

suppress_known_dependency_warnings()


def scenario_names() -> list[str]:
    path = SEED_DIR / "scenarios.json"
    if not path.exists():
        return []
    return [row["name"] for row in json.loads(path.read_text(encoding="utf-8"))]


def database_mode(url: str | None) -> str:
    lowered = (url or "").lower()
    if lowered.startswith("postgresql:") or lowered.startswith("postgres:"):
        return "postgres"
    if lowered.startswith("sqlite:"):
        return "sqlite"
    return "none"


def event_timestamp_label(value: datetime | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def signal_timestamp_label(signal) -> str:
    return event_timestamp_label(signal.event_time or signal.fetched_at)


def signal_timestamp_map(state: dict) -> dict[str, str]:
    return {
        signal.signal_id: signal_timestamp_label(signal)
        for signal in state.get("new_signals", []) or []
    }


def kpi_markdown(state: dict) -> str:
    classifications = state.get("classifications", []) or []
    simulation = state.get("simulation")
    forecast = state.get("forecast")
    max_severity = max((item.severity for item in classifications), default=0.0)
    active = len(classifications)
    stockout = simulation.stockout_probability if simulation else 0.0
    revenue = simulation.revenue_impact if simulation else 0.0
    deviation = forecast.demand_deviation_pct if forecast else 0.0
    # Detect whether the signal came from a live feed, a named scenario, or
    # the seed fallback so the executive overview is honest about the source.
    signals = state.get("new_signals", []) or []
    if signals and signals[0].source == "seed_fallback":
        signal_source_note = "⚠️ **No live feed signals found** — results based on seed fallback scenario.  \n"
    elif signals and signals[0].source == "scenario_library":
        signal_source_note = "🧪 **Scenario test mode** — results based on injected scenario, not live feeds.  \n"
    else:
        signal_source_note = "✅ **Live feed signals** — results based on data from configured RSS / weather feeds.  \n"
    return (
        f"### Executive overview\n"
        f"{signal_source_note}"
        f"**Overall risk index:** {max_severity:.1f}/10  \n"
        f"**Active disruption signals:** {active}  \n"
        f"**Stockout probability:** {stockout:.0%}  \n"
        f"**Expected revenue impact:** {revenue:,.0f}  \n"
        f"**Demand deviation:** {deviation:.1f}%  \n"
        f"**Route:** {state.get('route', 'not set')}"
    )


def system_markdown(state: dict) -> str:
    settings = get_settings()
    status = ping(settings)
    data_dir = Path(settings.data_dir)
    forecast = state.get("forecast")
    retriever = retriever_stats()
    llm_mode = llm_mode_label(settings)
    return (
        f"### System status\n"
        f"**Storage mode:** {database_mode(settings.resolved_database_url)} ({status.detail})  \n"
        f"**LLM mode:** {llm_mode}  \n"
        f"**Retrieval mode:** {retrieval_mode()} via {retriever['backend']}  \n"
        f"**Vector store:** {retriever['vector_store_path']}  \n"
        f"**RAG corpus:** {retriever['impact_documents']} impact / {retriever['mitigation_documents']} playbook / {retriever['history_documents']} history / {retriever['forecast_documents']} forecast docs  \n"
        f"**Data home:** {data_dir}  \n"
        f"**Signals used this run:** {len(state.get('new_signals', []) or [])}  \n"
        f"**Forecast baseline:** {forecast.note if forecast else 'No forecast baseline generated.'}"
    )


def signals_table(state: dict) -> pd.DataFrame:
    rows = []
    classifications = {item.signal_id: item for item in state.get("classifications", []) or []}
    timestamps = signal_timestamp_map(state)
    for signal in state.get("new_signals", []) or []:
        cls = classifications.get(signal.signal_id)
        is_fallback = signal.source == "seed_fallback"
        is_scenario = signal.source == "scenario_library"
        if is_fallback:
            label = "[SEED FALLBACK] "
        elif is_scenario:
            label = "[SCENARIO] "
        else:
            label = "[LIVE] "
        rows.append(
            {
                "event_date": timestamps.get(signal.signal_id, ""),
                "title": label + signal.title,
                "title": signal.title,
                "source": signal.source,
                "region": signal.region or "",
                "category": cls.category if cls else "",
                "severity": cls.severity if cls else 0,
                "risk_level": cls.risk_level if cls else "",
                "confidence": cls.confidence if cls else 0,
                "route": cls.route if cls else "",
            }
        )
    return pd.DataFrame(rows)


def analysis_table(state: dict) -> pd.DataFrame:
    rows = []
    timestamps = signal_timestamp_map(state)
    for item in state.get("event_analyses", []) or []:
        rows.append(
            {
                "event_date": timestamps.get(item.signal_id, ""),
                "event_type": item.event_type,
                "region": item.extracted_region or "",
                "severity_hint": item.severity_hint or "",
                "entities": ", ".join(item.entities),
                "summary": item.summary,
                "context_hits": len(item.retrieved_context),
            }
        )
    return pd.DataFrame(rows)


def impact_table(state: dict) -> pd.DataFrame:
    impacts = state.get("impacts") or []
    if impacts:
        rows = []
        timestamps = signal_timestamp_map(state)
        for impact in impacts:
            rows.append(
                {
                    "event_date": timestamps.get(impact.signal_id, ""),
                    "suppliers": ", ".join(impact.affected_suppliers),
                    "lanes": ", ".join(impact.affected_lanes),
                    "facilities": ", ".join(impact.affected_facilities),
                    "products": ", ".join(impact.product_categories),
                    "reasoning": impact.reasoning,
                }
            )
        return pd.DataFrame(rows)
    # Explain why the table is empty
    route = state.get("route", "")
    classifications = state.get("classifications", []) or []
    if not classifications:
        reason = "No signals classified — pipeline did not reach the impact agent."
    elif "HIGH" in route or "high_path" in route:
        reason = (
            "Skipped — per routing spec, HIGH severity (>7) signals bypass "
            "impact mapping and go straight to simulation. "
            "Impact analysis runs only for MEDIUM (4–7) signals."
        )
    elif "monitor_only" in route.lower() or all(
        getattr(c, "severity", 0) < 4 for c in classifications
    ):
        severities = ", ".join(f"{c.severity:.1f}" for c in classifications)
        reason = (
            f"Skipped — route is monitor-only (signal severities: {severities}). "
            f"Impact mapping runs only for MEDIUM (≥4.0) and HIGH (>7.0) signals."
        )
    else:
        reason = "Impact mapping ran but returned no results."
    return pd.DataFrame([{"status": "— skipped —", "reason": reason}])


def weather_table(state: dict) -> pd.DataFrame:
    rows = []
    timestamps = signal_timestamp_map(state)
    for risk in state.get("weather_risks", []) or []:
        rows.append(
            {
                "event_date": timestamps.get(risk.signal_id, ""),
                "hub": risk.hub_port or "",
                "region": risk.region or "",
                "horizon_days": risk.horizon_days,
                "aggregate_severity": risk.aggregate_severity,
                "port_disruption_risk": risk.port_disruption_risk,
                "peak_day": risk.peak_day or "",
                "operations": ", ".join(risk.affected_operations),
                "context_hits": len(risk.retrieved_context),
            }
        )
    return pd.DataFrame(rows)


def forecast_table(state: dict) -> pd.DataFrame:
    forecast = state.get("forecast")
    if not forecast:
        return pd.DataFrame()
    rows = []
    for date, base, adj in zip(forecast.dates, forecast.baseline, forecast.adjusted, strict=False):
        delta = round(adj - base, 2)
        pct   = round(100.0 * delta / base, 1) if base else 0.0
        rows.append({
            "week":          date,
            "baseline (units/wk)": round(base, 0),
            "risk-adjusted":       round(adj, 0),
            "delta":               delta,
            "change %":            f"{pct:+.1f}%",
        })
    # Summary row
    b_mean = round(sum(forecast.baseline) / len(forecast.baseline), 0) if forecast.baseline else 0
    a_mean = round(sum(forecast.adjusted) / len(forecast.adjusted), 0) if forecast.adjusted else 0
    d_mean = round(a_mean - b_mean, 0)
    p_mean = f"{forecast.demand_deviation_pct:+.1f}%"
    rows.append({
        "week":                "── 8-week mean ──",
        "baseline (units/wk)": b_mean,
        "risk-adjusted":       a_mean,
        "delta":               d_mean,
        "change %":            p_mean,
    })
    df = pd.DataFrame(rows)
    return df


def forecast_context_markdown(state: dict) -> str:
    forecast = state.get("forecast")
    classifications = state.get("classifications", [])
    route = state.get("route", "")
    if not forecast:
        if not classifications:
            return "⚠️ *Forecast skipped — no signals were classified.*"
        if "HIGH" in route or "high_path" in route:
            high_sev = max((getattr(c,"severity",0) for c in classifications), default=0)
            return (
                f"⚠️ *Forecast skipped — **per routing spec**, HIGH severity signals (>7) "
                f"bypass forecast and go straight to simulation "
                f"(highest signal: {high_sev:.1f}/10).  \n"
                f"Forecast runs only on MEDIUM (4–7) severity signals.*"
            )
        if "LOW" in route or "monitor" in route.lower():
            severities = ", ".join(f"{c.severity:.1f}" for c in classifications)
            return (
                f"⚠️ *Forecast skipped — route is **monitor-only** "
                f"(signal severities: {severities}).  \n"
                f"Forecast runs only for MEDIUM (≥4.0) and HIGH (>7.0) signals.*"
            )
        return "⚠️ *Forecast skipped — no result available for this route.*"
    category = ""
    if classifications:
        top = max(classifications, key=lambda c: c.severity)
        category = top.category or ""
    deviation = forecast.demand_deviation_pct
    direction = "▼ suppressed" if deviation < -1.0 else "▲ elevated" if deviation > 1.0 else "≈ stable"
    return (
        f"**Forecast model:** {forecast.model_name or 'unknown'}  \n"
        f"**Disruption category:** {category or '—'}  \n"
        f"**Demand signal:** {direction} by **{abs(deviation):.1f}%** over 8 weeks  \n"
        f"**Inventory days remaining:** {forecast.inventory_days_left:.1f} days  \n"
        f"**Predicted replenishment delay:** {forecast.predicted_delay_days:.1f} days  \n"
        f"**Freight pressure:** {forecast.freight_pressure_pct:+.2f}%  \n"
        f"**MAPE estimate:** {forecast.mape_estimate:.1%}"
    )


def recommendation_table(state: dict) -> pd.DataFrame:
    rec = state.get("recommendation")
    if not rec:
        return pd.DataFrame()
    return pd.DataFrame([item.model_dump() for item in rec.structured_actions])


def evidence_table(state: dict) -> pd.DataFrame:
    rec = state.get("recommendation")
    if not rec:
        return pd.DataFrame()
    return pd.DataFrame({"evidence": rec.evidence})


def simulation_markdown(state: dict) -> str:
    sim = state.get("simulation")
    route = state.get("route", "")
    classifications = state.get("classifications", []) or []
    if not sim:
        if not classifications:
            return "⚠️ **Simulation skipped** — no signals were classified."
        if "LOW" in route or "monitor" in route.lower():
            severities = ", ".join(f"{c.severity:.1f}" for c in classifications)
            return (
                f"⚠️ **Simulation skipped** — route is **monitor-only**.\n\n"
                f"Signal severities: {severities}. "
                f"Simulation runs only for MEDIUM (≥4.0) and HIGH (>7.0) severity signals. "
                f"No stockout risk or revenue impact to report at this severity level."
            )
        return "⚠️ **Simulation skipped** — no result available for this route."
    return (
        f"### Simulation lab\n"
        f"Engine: **{sim.engine or 'local'}**  \n"
        f"Stockout probability: **{sim.stockout_probability:.0%}**  \n"
        f"Service level: **{sim.service_level:.0%}**  \n"
        f"Expected shortage: **{sim.expected_shortage_units:,.0f} units**  \n"
        f"Recovery time: **{sim.recovery_time_days:.1f} days**  \n"
        f"Revenue impact mean / p50 / p90: **{sim.revenue_impact:,.0f} / {sim.revenue_loss_p50:,.0f} / {sim.revenue_loss_p90:,.0f}**  \n"
        f"{sim.assumptions}"
    )
def run_dashboard(scenario: str | None, use_pending_signals: bool) -> tuple:
    scenario_value = scenario or None
    state = run(scenario_value, use_pending_signals=use_pending_signals)
    return (
        kpi_markdown(state),
        system_markdown(state),
        analysis_table(state),
        weather_table(state),
        signals_table(state),
        impact_table(state),
        forecast_context_markdown(state),
        forecast_table(state),
        simulation_markdown(state),
        recommendation_table(state),
        evidence_table(state),
        json.dumps(serialize_state(state), indent=2, default=str),
    )


def collect_dashboard() -> str:
    summary = collect()
    total = summary.totals
    settings = get_settings()
    return f"Collected {total.fetched} raw items, kept {total.kept}, dropped {total.dropped}, persisted {total.persisted}. Storage mode: {database_mode(settings.resolved_database_url)}."


def history_table() -> pd.DataFrame:
    init_db()
    try:
        with connect() as conn:
            rows = recent_runs(conn, 20)
    except Exception:
        rows = []
    return pd.DataFrame([{key: row[key] for key in ("run_id", "created_at", "scenario_name", "route", "max_severity")} for row in rows])


def inbox_table() -> pd.DataFrame:
    init_db()
    try:
        with connect() as conn:
            signals = recent_signals(conn, 50)
    except Exception:
        signals = []
    return pd.DataFrame(
        [
            {
                "event_date": signal_timestamp_label(item),
                "title": item.title,
                "source": item.source,
                "type": item.source_type,
                "region": item.region or "",
                "severity_hint": item.severity_hint or "",
                "status": "stored",
            }
            for item in signals
        ]
    )


def ask_network(question: str) -> str:
    docs = (
        impact_retriever().search(question, top_k=3)
        + mitigation_retriever().search(question, top_k=3)
        + news_retriever().search(question, top_k=2)
        + forecast_retriever().search(question, top_k=2)
        + simulation_retriever().search(question, top_k=2)
    )
    if not docs:
        return "No local network or playbook context matched that question."
    settings = get_settings()
    lines = ["Relevant local context:"]
    seen: set[str] = set()
    context_rows: list[str] = []
    for doc in docs:
        if doc.doc_id in seen:
            continue
        seen.add(doc.doc_id)
        label = doc.metadata.get("name") or doc.metadata.get("title") or doc.doc_id
        row = f"- {label}: {doc.text}"
        lines.append(row)
        context_rows.append(row)
        if len(seen) >= 5:
            break
    if not settings.llm_is_mock:
        system = "Answer using the provided local supply-chain context only. Keep the response concise and practical."
        prompt = f"Question: {question}\n\nContext:\n" + "\n".join(context_rows)
        try:
            answer = completion(prompt, system=system, settings=settings, temperature=0).strip()
            if answer:
                return f"### Answer\n{answer}\n\n" + "\n".join(lines)
        except Exception:
            pass
    return "\n".join(lines)


def llm_mode_label(settings) -> str:
    return "mock" if settings.llm_is_mock else f"groq:{settings.groq_model}"


def dashboard_css() -> str:
    return """
    #config-modal {
        position: fixed !important;
        inset: 0;
        z-index: 999;
        background: rgba(15, 23, 42, 0.48);
        overflow-y: auto;
        padding: 24px 0 32px;
    }

    #config-panel {
        max-width: 1180px;
        margin: 0 auto;
        background: white;
        border-radius: 18px;
        padding: 20px 22px 24px;
        box-shadow: 0 28px 80px rgba(15, 23, 42, 0.24);
    }
    """


def config_input_value(field_name: str):
    settings = get_settings()
    if field_name in {
        "AGENTIC_SCD_HOME",
        "DATABASE_URL",
        "VECTOR_DATABASE_URL",
        "AGENTIC_SCD_SOURCES_YAML",
        "AGENTIC_SCD_LEXICON_YAML",
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
        "HF_TOKEN",
        "XAI_API_KEY",
    }:
        return os.getenv(field_name, "")
    if field_name == "GROQ_MODEL":
        return os.getenv(field_name, settings.groq_model)
    if field_name == "USE_MOCK_LLM":
        return settings.use_mock_llm
    if field_name == "RAG_AUTO_REBUILD":
        return settings.rag_auto_rebuild
    if field_name == "INGEST_POLL_INTERVAL_MINUTES":
        return str(settings.ingest_poll_interval_minutes)
    if field_name == "INGEST_SCHEDULER_ENABLED":
        return settings.ingest_scheduler_enabled
    if field_name == "INGEST_HOST":
        return settings.ingest_host
    if field_name == "INGEST_PORT":
        return str(settings.ingest_port)
    if field_name == "WEBHOOK_SOURCE_RELIABILITY":
        return str(settings.webhook_source_reliability)
    if field_name == "BATCH_ENABLED":
        return settings.batch_enabled
    if field_name == "RETENTION_ENABLED":
        return settings.retention_enabled
    if field_name == "RETENTION_REJECTED_TTL_DAYS":
        return str(settings.retention_rejected_ttl_days)
    if field_name == "RETENTION_SIGNALS_TTL_DAYS":
        return str(settings.retention_signals_ttl_days)
    if field_name == "SIMULATION_ITERATIONS":
        return str(settings.simulation_iterations)
    if field_name == "GRADIO_SHARE":
        return settings.dashboard_share
    if field_name == "GRADIO_SERVER_NAME":
        return os.getenv(field_name, "127.0.0.1")
    return os.getenv(field_name, "")


def config_runtime_values() -> tuple[str, ...]:
    settings = get_settings()
    status = ping(settings)
    retrieval = retriever_stats()
    return (
        str(local_env_path()),
        f"{database_mode(settings.resolved_database_url)} ({status.detail})",
        settings.resolved_database_url or "",
        llm_mode_label(settings),
        f"{retrieval_mode()} via {retrieval['backend']} ({retrieval['history_documents']} history / {retrieval['impact_documents']} impact / {retrieval['mitigation_documents']} mitigation / {retrieval['forecast_documents']} forecast)",
        str(settings.data_dir),
        str(snapshot_dir()),
        str(run_dir()),
        str(sources_yaml_path()),
        str(lexicon_yaml_path()),
        str(SEED_DIR),
        "7860",
        "8000",
    )


def config_status_text(message: str) -> str:
    lines = []
    if message:
        lines.append(f"**{message}**")
    lines.append(f"Config file: `{local_env_path()}`")
    lines.append("Leave `VECTOR_DATABASE_URL` blank to follow Postgres automatically when `DATABASE_URL` points to Postgres; otherwise the local-first runtime keeps a separate SQLite vector store under the data home.")
    lines.append("Next dashboard action picks up storage selection, data-home changes, YAML overrides, Groq settings, retention values, and simulation iterations.")
    lines.append("Restart the dashboard or ingestion service for `GRADIO_SERVER_NAME`, `GRADIO_SHARE`, `INGEST_HOST`, `INGEST_PORT`, `INGEST_POLL_INTERVAL_MINUTES`, and `INGEST_SCHEDULER_ENABLED`.")
    lines.append("`OPENAI_API_KEY`, `HF_TOKEN`, and `XAI_API_KEY` are stored by the panel but are not consumed by the current local-first runtime yet.")
    return "\n\n".join(lines)


def config_snapshot(visible: bool, message: str) -> tuple:
    values = [config_input_value(field.name) for field in CONFIG_FIELDS]
    readonly = list(config_runtime_values())
    return (
        gr.update(visible=visible),
        *values,
        *readonly,
        config_status_text(message),
    )


def open_config_panel() -> tuple:
    return config_snapshot(True, "Local-first runtime configuration")


def reload_config_panel() -> tuple:
    return config_snapshot(True, "Reloaded current local-first settings")


def close_config_panel():
    return gr.update(visible=False)


def apply_config_panel(*args) -> tuple:
    values = {}
    for field, raw_value in zip(CONFIG_FIELDS, args, strict=False):
        values[field.name] = "1" if field.kind == "bool" and raw_value else "0" if field.kind == "bool" else raw_value
    apply_runtime_env(values)
    get_settings.cache_clear()
    load_lexicon.cache_clear()
    impact_retriever.cache_clear()
    mitigation_retriever.cache_clear()
    history_retriever.cache_clear()
    news_retriever.cache_clear()
    weather_retriever.cache_clear()
    forecast_retriever.cache_clear()
    simulation_retriever.cache_clear()
    return config_snapshot(True, "Saved local-first configuration")


def build_dashboard() -> gr.Blocks:
    scenarios = [""] + scenario_names()
    sections: dict[str, list] = {}
    for field in CONFIG_FIELDS:
        sections.setdefault(field.section, []).append(field)
    with gr.Blocks(title="Agentic Supply Chain Disruption Predictor") as app:
        gr.HTML(f"<style>{dashboard_css()}</style>")
        gr.Markdown("# Agentic Supply Chain Disruption Predictor & Simulation Engine")
        gr.Markdown("Run a live or packaged scenario, inspect the agent path, and test mitigation choices from one local dashboard.")
        with gr.Row():
            scenario = gr.Dropdown(choices=scenarios, value=scenarios[0], label="Scenario")
            use_pending_signals = gr.Checkbox(label="Use pending DB signals", value=False)
            run_btn = gr.Button("Run pipeline", variant="primary")
            collect_btn = gr.Button("Refresh external data")
            config_btn = gr.Button("Config")
        collect_status = gr.Markdown()
        config_inputs = []
        with gr.Column(visible=False, elem_id="config-modal") as config_modal:
            with gr.Column(elem_id="config-panel"):
                gr.Markdown("## Config")
                gr.Markdown("Manage the local-first Python runtime without changing the notebook or docker paths.")
                with gr.Tabs():
                    for section, fields in sections.items():
                        with gr.Tab(section):
                            for field in fields:
                                if field.kind == "bool":
                                    component = gr.Checkbox(label=field.label)
                                else:
                                    component = gr.Textbox(
                                        label=field.label,
                                        type="password" if field.secret else "text",
                                    )
                                config_inputs.append(component)
                with gr.Row():
                    save_config = gr.Button("Save config", variant="primary")
                    reload_config = gr.Button("Reload values")
                    close_config = gr.Button("Close")
                config_status = gr.Markdown()
                with gr.Row():
                    config_file_box = gr.Textbox(label="Config file", interactive=False)
                    storage_box = gr.Textbox(label="Resolved storage", interactive=False)
                    llm_box = gr.Textbox(label="Resolved LLM mode", interactive=False)
                with gr.Row():
                    database_box = gr.Textbox(label="Resolved DB URL", interactive=False)
                    retrieval_box = gr.Textbox(label="Retrieval mode", interactive=False)
                with gr.Row():
                    data_home_box = gr.Textbox(label="Resolved data home", interactive=False)
                    sources_box = gr.Textbox(label="Resolved sources YAML", interactive=False)
                    lexicon_box = gr.Textbox(label="Resolved lexicon YAML", interactive=False)
                with gr.Row():
                    snapshot_box = gr.Textbox(label="Snapshot directory", interactive=False)
                    run_box = gr.Textbox(label="Run directory", interactive=False)
                    seed_box = gr.Textbox(label="Seed directory", interactive=False)
                with gr.Row():
                    dashboard_port_box = gr.Textbox(
                        label="Dashboard port", interactive=False
                    )
                    api_port_box = gr.Textbox(label="API port", interactive=False)
        config_outputs = [
            config_modal,
            *config_inputs,
            config_file_box,
            storage_box,
            database_box,
            llm_box,
            retrieval_box,
            data_home_box,
            snapshot_box,
            run_box,
            sources_box,
            lexicon_box,
            seed_box,
            dashboard_port_box,
            api_port_box,
            config_status,
        ]
        with gr.Tabs():
            with gr.Tab("Executive"):
                kpis = gr.Markdown()
                system_card = gr.Markdown()
                history = gr.Dataframe(label="Recent runs", interactive=False)
                refresh_history = gr.Button("Refresh run history")
            with gr.Tab("Risk monitor"):
                signals = gr.Dataframe(label="Signals and classification", interactive=False)
                inbox = gr.Dataframe(label="Stored signal inbox", interactive=False)
                refresh_inbox = gr.Button("Refresh inbox")
            with gr.Tab("News analysis"):
                analyses = gr.Dataframe(label="Event extraction and summarization", interactive=False)
            with gr.Tab("Weather risk"):
                weather = gr.Dataframe(label="7-day hub weather risk", interactive=False)
            with gr.Tab("Impact map"):
                impacts = gr.Dataframe(label="Affected suppliers, lanes, and facilities", interactive=False)
            with gr.Tab("Demand forecast"):
                forecast_context = gr.Markdown(value="*Run the pipeline to see forecast context.*")
                forecast = gr.Dataframe(label="Baseline vs risk-adjusted forecast (weekly units)", interactive=False)
            with gr.Tab("Simulation"):
                simulation = gr.Markdown()
            with gr.Tab("Mitigation"):
                recommendations = gr.Dataframe(label="Ranked action plan", interactive=False)
                evidence = gr.Dataframe(label="Supporting evidence", interactive=False)
            with gr.Tab("Trace JSON"):
                raw = gr.Code(language="json")
            with gr.Tab("Ask the local KB"):
                question = gr.Textbox(label="Question", value="Which suppliers and lanes are exposed to Shanghai weather disruption?")
                answer_btn = gr.Button("Ask")
                answer = gr.Markdown()
        config_btn.click(open_config_panel, outputs=config_outputs)
        save_config.click(
            apply_config_panel, inputs=config_inputs, outputs=config_outputs
        )
        reload_config.click(reload_config_panel, outputs=config_outputs)
        close_config.click(close_config_panel, outputs=[config_modal])
        run_btn.click(run_dashboard, inputs=[scenario, use_pending_signals], outputs=[kpis, system_card, analyses, weather, signals, impacts, forecast_context, forecast, simulation, recommendations, evidence, raw]).then(history_table, outputs=[history]).then(inbox_table, outputs=[inbox])
        collect_btn.click(collect_dashboard, outputs=[collect_status]).then(inbox_table, outputs=[inbox])
        refresh_history.click(history_table, outputs=[history])
        refresh_inbox.click(inbox_table, outputs=[inbox])
        answer_btn.click(ask_network, inputs=[question], outputs=[answer])
    return app


def main() -> None:
    settings = get_settings()
    server_name = os.getenv("GRADIO_SERVER_NAME") or "127.0.0.1"
    build_dashboard().launch(server_name=server_name, server_port=7860, share=settings.dashboard_share)


if __name__ == "__main__":
    main()
