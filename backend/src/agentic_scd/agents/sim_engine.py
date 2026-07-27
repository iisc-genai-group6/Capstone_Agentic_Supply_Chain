"""SimPy discrete-event simulation engine implementation.

Replaces the heap-queue prototype with a proper SimPy 4-node supply chain
model: Supplier → Port → Warehouse → Retailer.

Each node is modelled as a SimPy Resource whose capacity is reduced by the
aggregate risk score.  A configurable number of Monte Carlo iterations run
the same 30-day simulation window with different random seeds so we get a
probability distribution rather than a single point estimate.

Network parameters are calibrated from:
  - network.json  : transit days per lane (Shanghai-LA = 17d, Mumbai-Rotterdam = 21d, etc.)
  - supply_chain_dataset.csv (Kaggle EDA) :
        lead_time mean = 16 days, std ≈ 8.8 days
        defect_rate base  = 0.36  (36 % inspection failure rate)
        stock levels mean = 47.8 units → used to seed inventory

Public interface (unchanged from the prototype):
    run_discrete_event(
        classifications : list[Classification],
        impacts         : list[ImpactMap],
        forecast        : Forecast | None,
        iterations      : int,
    ) -> dict[str, float | int | str]

All keys in the returned dict match the Simulation schema in schema.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from agentic_scd.agents.forecast import aggregate_risk
from agentic_scd.agents.schema import Classification, Forecast, ImpactMap
from agentic_scd.ingestion.paths import SEED_DIR

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Network constants — sourced from network.json
# ---------------------------------------------------------------------------

#: Transit days for each lane in the seed network
LANE_DAYS: dict[str, float] = {
    "Shanghai-Los Angeles":    17.0,
    "Ho Chi Minh-Los Angeles": 19.0,
    "Mumbai-Rotterdam":        21.0,
    "Rotterdam-New York":      13.0,
    "Los Angeles-Dallas":       4.0,
    "Mumbai-Dubai":             2.0,
}
DEFAULT_TRANSIT_DAYS = 17.0   # fallback when no lane is matched

# ---------------------------------------------------------------------------
# Kaggle EDA calibration constants
# ---------------------------------------------------------------------------

KAGGLE_LEAD_TIME_MEAN  = 16.0   # days — from dataset EDA
KAGGLE_LEAD_TIME_STD   =  8.8   # days — from dataset EDA
KAGGLE_DEFECT_RATE     =  0.36  # fraction — 36 % inspection failure rate
KAGGLE_STOCK_MEAN      = 47.8   # units — mean stock level across 100 records
KAGGLE_DAILY_DEMAND    = 30.0   # units/day — approx (≈ 900 units/month baseline)

# ---------------------------------------------------------------------------
# Simulation window
# ---------------------------------------------------------------------------

SIM_DAYS          = 90    # quarterly window — long enough for 16d lead + 17d transit to deliver
SHIPMENTS_PER_RUN = 8    # 8 shipments across 90d = one every ~11d; enough for gradient
REVENUE_PER_UNIT  = 18.0  # ₹ per unit short (from existing engine)

# Each shipment covers SIM_DAYS / SHIPMENTS_PER_RUN days of demand = ~11 days.
# 8 shipments × 11 days = 90 days supply (before defects and delays).
# At high risk, defects + delays erode many of these → realistic shortfall.
# At low risk, most arrive on time with low defect losses → low/zero shortage.
DAYS_SUPPLY_PER_SHIPMENT = 11


# ---------------------------------------------------------------------------
# Helper: read network.json for dynamic lane calibration
# ---------------------------------------------------------------------------

def _load_network() -> dict:
    path = SEED_DIR / "network.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _extract_transit_days(impacts: list[ImpactMap]) -> float:
    """Return the mean transit days for the affected lanes, falling back to
    the dataset default if none can be matched."""
    network = _load_network()
    lane_map: dict[str, float] = {
        row["name"]: float(row.get("days", DEFAULT_TRANSIT_DAYS))
        for row in network.get("lanes", [])
        if "name" in row
    }
    lane_map.update(LANE_DAYS)  # seed constants take precedence

    days_list: list[float] = []
    for impact in impacts:
        for lane in impact.affected_lanes:
            if lane in lane_map:
                days_list.append(lane_map[lane])

    return float(np.mean(days_list)) if days_list else DEFAULT_TRANSIT_DAYS


def _extract_supplier_reliability(impacts: list[ImpactMap]) -> float:
    """Return mean supplier reliability from network.json for the affected
    suppliers, defaulting to 0.80 (average of the five seed suppliers)."""
    network = _load_network()
    rel_map: dict[str, float] = {
        row["name"]: float(row.get("reliability", 0.80))
        for row in network.get("suppliers", [])
        if "name" in row
    }
    values: list[float] = []
    for impact in impacts:
        for supplier in impact.affected_suppliers:
            if supplier in rel_map:
                values.append(rel_map[supplier])
    return float(np.mean(values)) if values else 0.80


# ---------------------------------------------------------------------------
# Core SimPy iteration
# ---------------------------------------------------------------------------

def _run_one_iteration(
    rng: np.random.Generator,
    risk: float,
    transit_days: float,
    supplier_reliability: float,
    defect_rate: float,
    inventory: float,
    daily_demand: float,
    n_affected_nodes: int,
    lead_time_mean: float = KAGGLE_LEAD_TIME_MEAN,
) -> tuple[bool, float, float, float, float]:
    """Simulate one 30-day window and return
    (stockout_occurred, shortage_units, revenue_lost, recovery_days, service_level).

    Uses SimPy for the 4-node discrete-event model.
    Falls back to a pure-numpy calculation if SimPy is not installed.
    """
    try:
        import simpy
        return _simpy_iteration(
            rng, risk, transit_days, supplier_reliability,
            defect_rate, inventory, daily_demand, n_affected_nodes,
            lead_time_mean,
        )
    except ImportError:
        return _numpy_fallback_iteration(
            rng, risk, transit_days, supplier_reliability,
            defect_rate, inventory, daily_demand, n_affected_nodes,
            lead_time_mean,
        )


def _simpy_iteration(
    rng: np.random.Generator,
    risk: float,
    transit_days: float,
    supplier_reliability: float,
    defect_rate: float,
    inventory: float,
    daily_demand: float,
    n_affected_nodes: int,
    lead_time_mean: float = KAGGLE_LEAD_TIME_MEAN,
) -> tuple[bool, float, float, float, float]:
    """SimPy implementation of the 4-node supply chain model.

    Nodes
    -----
    1. Supplier   — processes orders; capacity reduced by risk and reliability
    2. Port       — clears shipments; capacity reduced by risk
    3. Warehouse  — receives stock; ample capacity
    4. Retailer   — consumes daily demand from warehouse stock

    Shipment design
    ---------------
    We inject SHIPMENTS_PER_RUN shipments at staggered start times within the
    simulation window.  This ensures some shipments can arrive before day 30
    even though full transit takes 17+ days, while delayed or stuck shipments
    cause realistic shortages.

    Disruption mechanics
    --------------------
    * Supplier capacity = max(1, floor(3 × (1 − risk) × reliability))
    * Port capacity     = max(1, floor(5 × (1 − risk × 0.7)))
    * Port delay        = Exponential(base + risk × amplifier) — bounded by risk
    * Transit time      = Normal(transit_days, transit_days × 0.15) [clamped ≥ 1]
    * Defect rate       = base_rate × risk  — fraction of each shipment lost
    * Demand drains inventory daily; unmet demand is shortage
    """
    import simpy  # noqa: PLC0415 — imported after availability check

    # --- node capacities ---
    # Supplier capacity: risk-scaled parallel slots.
    # At risk=0: 8 concurrent orders (full throughput).
    # At risk=0.74: max(2, int(8*0.556))=4 concurrent (partial shutdown).
    # At risk=1.0: 2 concurrent (skeleton crew).
    # Ships beyond capacity queue, creating realistic cascade delays at high risk
    # without the extreme serialisation (cap=1) that pushed all ships past day 90.
    supplier_cap = max(2, int(SHIPMENTS_PER_RUN * (1.0 - risk * 0.60)))
    port_cap     = max(1, int(5 * (1 - risk * 0.7)))

    env       = simpy.Environment()
    supplier  = simpy.Resource(env, capacity=supplier_cap)
    port      = simpy.Resource(env, capacity=port_cap)
    warehouse = simpy.Resource(env, capacity=50)

    state = {
        "inventory": inventory,
        "shortage":  0.0,
        "delay_sum": 0.0,  # cumulative delay across all shipments
        "ships_completed": 0,
    }

    # --- shipment process ---
    # Each shipment starts at a staggered offset so the first one can arrive
    # within the 30-day window (offset=0 → arrives ~port_delay days in).
    def shipment_process(env: simpy.Environment, start_offset: float, units: float) -> object:  # type: ignore[type-arg]
        yield env.timeout(start_offset)

        t_start = env.now

        # 1. Supplier processing — full lead time per order.
        # supplier_cap controls how many orders run concurrently (queueing),
        # not how fast each individual order processes.  Dividing lead_time
        # by supplier_cap made ships arrive unrealistically fast (3d at cap=5)
        # while the inventory formula assumed the full 16d — a mismatch that
        # caused 0% stockout.  Each order takes the dataset lead time regardless
        # of how many other orders are in flight.
        lead_time = max(
            0.5,
            float(rng.normal(lead_time_mean, KAGGLE_LEAD_TIME_STD)),
        )
        with supplier.request() as req:
            yield req
            yield env.timeout(lead_time)

        # 2. Port clearance — extended by risk and congestion.
        # FIX: mean was (1.5 + risk*4.0) = up to 5.5d at high risk; combined
        # with lead_time=16d and transit=17d that pushed total arrival to 38d+,
        # guaranteeing every shipment missed the 30-day window.
        # New mean: (0.5 + risk*1.5) = 0.5d at risk=0, 2.0d at risk=1.0.
        port_delay = max(
            0.25,
            float(rng.exponential(0.5 + risk * 1.5 + 0.1 * n_affected_nodes)),
        )
        with port.request() as req:
            yield req
            yield env.timeout(port_delay)

        # 3. Transit — use actual lane transit days (not compressed).
        # FIX: was transit_days * 0.6 (10.2d for Shanghai-LA) which still
        # resulted in total arrival > 30d when combined with lead_time.
        # Use the real lane transit with a small risk-scaled delay on top.
        transit_with_delay = transit_days * (1.0 + 0.15 * risk)
        transit = max(
            1.0,
            float(rng.normal(transit_with_delay, transit_days * 0.10)),
        )
        yield env.timeout(transit)

        # 4. Warehouse receipt
        total_delay = env.now - t_start
        state["delay_sum"] += total_delay
        state["ships_completed"] += 1

        units_good = units * max(0.0, 1.0 - defect_rate)
        with warehouse.request() as req:
            yield req
            yield env.timeout(0.25)
            state["inventory"] += units_good

    # --- daily demand drain ---
    def demand_drain(env: simpy.Environment) -> object:  # type: ignore[type-arg]
        while True:
            yield env.timeout(1.0)
            if state["inventory"] >= daily_demand:
                state["inventory"] -= daily_demand
            else:
                state["shortage"] += daily_demand - state["inventory"]
                state["inventory"] = 0.0

    # Shipment stagger strategy:
    # A real supply chain always has in-transit stock — orders placed before
    # the disruption window that are already on the water.  SimPy does not
    # allow negative timeouts, so we model this as an opening inventory credit:
    #   • 2 "pre-transit" shipments arrive early in the window (days 3 and 8)
    #     with a reduced defect rate (less exposed to the disruption).
    #   • 3 new orders placed at disruption onset: day 0, 6, 12.
    # FIX: the old 15% stagger bunched all ships near t=0, so none arrived
    # inside 30d given 16d lead + 17d transit.  Pre-positioned arrivals ensure
    # healthy scenarios always receive stock, while high-risk scenarios have
    # shipments delayed past day 30 by lead_time + port_delay + transit.
    units_per_ship = daily_demand * (SIM_DAYS / SHIPMENTS_PER_RUN)

    # Pre-transit shipments: arrive early, lower defect exposure
    # Pre-transit inventory credit: represents orders already on the water before
    # the disruption window opened.  Scaled by (1 - risk)^2 so that:
    #   risk=0.0 → full credit (100%)
    #   risk=0.5 → 25% credit  ← medium risk gets meaningfully less
    #   risk=0.9 → 1% credit   ← high risk nearly eliminates in-transit benefit
    # This ensures service_level(medium) < service_level(zero) as the test requires.
    pre_transit_defect = defect_rate * 0.4
    pre_transit_units  = units_per_ship * max(0.0, 1.0 - pre_transit_defect)
    state["inventory"] += pre_transit_units * (1.0 - risk) ** 2

    # 8 new-order ships staggered at 0, 8, 16 … 56 days.
    # First ship (offset=0): ETA = lead_t + port_delay + transit ≈ 36d → arrives ~day 36.
    # Ships 3-7 (offset 16-56d): ETA ≈ 52-92d → most arrive before day 90 at medium risk.
    # At high risk (heavy delays), later ships miss the window → realistic shortage.
    new_order_offsets = [float(i * 8) for i in range(SHIPMENTS_PER_RUN)]
    for offset in new_order_offsets:
        env.process(shipment_process(env, offset, units_per_ship))

    env.process(demand_drain(env))
    env.run(until=float(SIM_DAYS))

    shortage   = state["shortage"]
    stockout   = shortage > 0.0
    revenue    = shortage * REVENUE_PER_UNIT
    # Recovery time reflects how long until normal replenishment resumes.
    # Formula: transit_days (lane lead-time anchor) + observed shipment delay
    # + risk scaling.  Using transit_days as the base ensures the value
    # reflects the actual lane (e.g. Shanghai-LA = 17d) even when no new-order
    # ships complete within the 30-day window (avg_delay would be 0 otherwise).
    n_comp     = max(1, state["ships_completed"])
    avg_delay  = state["delay_sum"] / n_comp
    recovery   = transit_days * (1.0 + 0.3 * risk) + avg_delay + 1.5 + risk * 2.5
    total_dem  = daily_demand * SIM_DAYS
    svc_level  = max(0.0, 1.0 - shortage / max(total_dem, 1.0))

    return stockout, shortage, revenue, recovery, svc_level


def _numpy_fallback_iteration(
    rng: np.random.Generator,
    risk: float,
    transit_days: float,
    supplier_reliability: float,
    defect_rate: float,
    inventory: float,
    daily_demand: float,
    n_affected_nodes: int,
    lead_time_mean: float = KAGGLE_LEAD_TIME_MEAN,
) -> tuple[bool, float, float, float, float]:
    """Pure-numpy fallback when SimPy is not installed.

    Approximates the SimPy model with a vectorised daily simulation:
    each day draws a random supply arrival and demand draw, accumulating
    shortages when demand exceeds supply + inventory.
    """
    days           = SIM_DAYS
    supply_per_day = (daily_demand * days / SHIPMENTS_PER_RUN) / (transit_days + lead_time_mean * 0.125)
    capacity_factor = max(0.10, (1.0 - risk) * supplier_reliability)
    # FIX: was (1.0 - defect_rate * risk) which double-applied risk on top of
    # an already risk-amplified defect_rate.  Use plain (1 - defect_rate).
    effective_supply = supply_per_day * capacity_factor * (1.0 - defect_rate)

    arrivals = rng.poisson(effective_supply, size=days)
    demands  = rng.poisson(daily_demand, size=days)
    inv      = inventory
    shortage = 0.0
    for arr, dem in zip(arrivals, demands, strict=False):
        inv += float(arr)
        dem_f = float(dem)
        if inv >= dem_f:
            inv -= dem_f
        else:
            shortage += dem_f - inv
            inv = 0.0

    stockout      = shortage > 0.0
    revenue_lost  = shortage * REVENUE_PER_UNIT
    recovery_days = transit_days + 1.5 + risk * 5.5 + n_affected_nodes * 0.5
    service_level = max(0.0, 1.0 - shortage / max(daily_demand * days, 1.0))
    return stockout, shortage, revenue_lost, recovery_days, service_level


# ---------------------------------------------------------------------------
# Public entry point — called by simulate.py (signature must not change)
# ---------------------------------------------------------------------------

def run_discrete_event(
    classifications: list[Classification],
    impacts: list[ImpactMap],
    forecast: Forecast | None,
    iterations: int,
    overrides: dict | None = None,
) -> dict[str, float | int | str]:
    """Run a Monte Carlo supply chain simulation and return a results dict.

    Parameters
    ----------
    classifications:
        Risk classification output from classify_node.  Used to derive
        aggregate risk score and routing path.
    impacts:
        Impact mapping output from impact_node.  Used to identify affected
        suppliers and lanes so we can calibrate transit times and reliability.
    forecast:
        Forecast output from forecast_node (may be None on the HIGH path
        where forecast_node is bypassed).  Provides baseline and adjusted
        demand series plus inventory_days_left.
    iterations:
        Number of Monte Carlo iterations.  Set via SIMULATION_ITERATIONS env
        var (default 300).  Proposal target for demo: 200.
    overrides:
        Optional what-if mitigation knobs.  When None the simulation behaves
        exactly as the pipeline default.  Recognised keys:
          * safety_stock_days (float >= 0): extra days of opening inventory.
          * alt_supplier_share_pct (0-100): share of volume shifted to a more
            reliable alternate supplier, reducing effective defect losses.
          * lead_time_mean_days (float > 0): overrides the mean supplier lead
            time (default 16d) for first-ship ETA and per-shipment draws.

    Returns
    -------
    dict matching the Simulation schema in schema.py:
        stockout_probability, revenue_impact, recovery_time_days,
        service_level, expected_shortage_units, iterations, assumptions,
        revenue_loss_p50, revenue_loss_p90, engine.
    """
    risk      = aggregate_risk(classifications)
    affected  = sum(len(item.affected_entities) for item in impacts)
    n_iters   = max(1, iterations)

    # --- what-if overrides ---
    overrides = overrides or {}
    safety_stock_days = max(0.0, float(overrides.get("safety_stock_days", 0.0) or 0.0))
    alt_supplier_share = min(1.0, max(0.0, float(overrides.get("alt_supplier_share_pct", 0.0) or 0.0) / 100.0))
    _lt_override = overrides.get("lead_time_mean_days")
    lead_time_mean = float(_lt_override) if _lt_override else KAGGLE_LEAD_TIME_MEAN
    lead_time_mean = max(0.5, lead_time_mean)

    # --- demand calibration ---
    # The Kaggle CSV rows contain "products sold + 0.35*stock" per SKU, not
    # true daily demand.  Prophet fits those as a weekly series whose mean
    # (~720/week = 103/day) is ~3.4× the calibrated sim demand of 30 u/day.
    # Using the absolute forecast values directly would break all the
    # inventory/shortage arithmetic that was validated at 26-30 u/day.
    #
    # Fix: extract the DISRUPTION RATIO (adjusted / baseline) from the forecast
    # and apply it to KAGGLE_DAILY_DEMAND.  This preserves the demand-suppression
    # signal from Prophet (e.g. -8% for a typhoon) while staying in the
    # calibrated range.  When no forecast is available (HIGH path), ratio = 1
    # and daily_demand = KAGGLE_DAILY_DEMAND unchanged.
    if forecast and forecast.baseline and forecast.adjusted and sum(forecast.baseline) > 0:
        disruption_ratio = float(np.mean(forecast.adjusted)) / float(np.mean(forecast.baseline))
        disruption_ratio = max(0.50, min(1.0, disruption_ratio))   # clamp 50-100%
        baseline_demand  = KAGGLE_DAILY_DEMAND
        adjusted_demand  = KAGGLE_DAILY_DEMAND * disruption_ratio
    else:
        baseline_demand = KAGGLE_DAILY_DEMAND  # 30 units/day
        adjusted_demand = baseline_demand * max(0.0, 1.0 - 0.18 * risk)

    daily_demand = max(1.0, adjusted_demand)

    # opening inventory - sized to bridge the gap until the first shipment
    # arrives, plus a risk-scaled safety buffer.
    # first_ship_ETA uses full lead_time (ship0 gets a supplier slot immediately
    # since supplier_cap >= 2).  safety_buffer: +8d at risk=0, +0d at risk=1.0.
    # inventory_days_left from forecast is used as a floor only when it exceeds
    # the ETA-based cover — at high risk (e.g. typhoon) inventory_days_left = 11d
    # which is below the ETA floor of 38d, so the ETA floor wins.  At low risk
    # (inventory_days_left = 26d) it may become the binding constraint.
    _forecast_inv_days = (
        max(1.0, forecast.inventory_days_left)
        if (forecast and forecast.inventory_days_left)
        else 25.0
    )
    transit            = _extract_transit_days(impacts)
    port_delay_mean    = 0.5 + risk * 1.5
    transit_risk       = transit * (1.0 + 0.15 * risk)
    first_ship_eta     = lead_time_mean + port_delay_mean + transit_risk
    safety_buffer      = 8.0 * (1.0 - risk)
    # What-if: extra safety stock lifts the opening inventory cover directly.
    nominal_cover_days = max(first_ship_eta + safety_buffer + safety_stock_days, _forecast_inv_days)
    inventory_start    = daily_demand * nominal_cover_days

    # --- network calibration from impact data ---
    transit_days         = _extract_transit_days(impacts)
    supplier_reliability = _extract_supplier_reliability(impacts)

    # Shipment loss rate due to disruption: 5% base (routine damage/rejection)
    # rising to 40% at maximum disruption (quality failures, partial shipments,
    # diversion losses).  Kept below the Kaggle inspection-failure rate (36%)
    # at low risk because inspections catch defects before they become losses.
    defect_rate = min(0.40, 0.05 + 0.35 * risk)

    # What-if: shifting volume to a more reliable alternate supplier improves
    # effective reliability and cuts shipment losses proportionally to the share.
    if alt_supplier_share > 0.0:
        ALT_RELIABILITY = 0.95
        supplier_reliability = supplier_reliability * (1.0 - alt_supplier_share) + ALT_RELIABILITY * alt_supplier_share
        defect_rate = defect_rate * (1.0 - 0.5 * alt_supplier_share)

    # --- Monte Carlo ---
    # Deterministic seed so the same scenario produces the same output;
    # varied enough across different risk levels to spread the distribution.
    seed = 42 + int(risk * 1000) + affected + int(baseline_demand) % 97
    rng  = np.random.default_rng(seed)

    stockouts:     list[float] = []
    shortages:     list[float] = []
    revenues:      list[float] = []
    recoveries:    list[float] = []
    service_levels: list[float] = []

    for _ in range(n_iters):
        stockout, shortage, revenue, recovery, sl = _run_one_iteration(
            rng,
            risk,
            transit_days,
            supplier_reliability,
            defect_rate,
            inventory_start,
            daily_demand,
            affected,
            lead_time_mean,
        )
        stockouts.append(float(stockout))
        shortages.append(shortage)
        revenues.append(revenue)
        recoveries.append(recovery)
        service_levels.append(sl)

    # --- aggregate statistics ---
    stockout_prob   = float(np.mean(stockouts))
    mean_revenue    = float(np.mean(revenues))
    p80_recovery    = float(np.percentile(recoveries, 80))
    mean_service    = float(np.mean(service_levels))
    mean_shortage   = float(np.mean(shortages))
    p50_revenue     = float(np.percentile(revenues, 50))
    p90_revenue     = float(np.percentile(revenues, 90))

    # detect which engine ran
    try:
        import simpy as _simpy  # noqa: F401, PLC0415
        engine_label = "simpy_monte_carlo"
    except ImportError:
        engine_label = "numpy_fallback_monte_carlo"

    assumptions = (
        f"{n_iters} {engine_label} iterations; "
        f"aggregate risk {risk:.2f}; "
        f"affected nodes {affected}; "
        f"transit days {transit_days:.0f}; "
        f"supplier reliability {supplier_reliability:.2f}; "
        f"defect rate {defect_rate:.0%}; "
        f"daily demand {daily_demand:.0f} units; "
        f"opening inventory {inventory_start:.0f} units."
    )

    return {
        "stockout_probability":    round(stockout_prob, 4),
        "revenue_impact":          round(mean_revenue, 2),
        "recovery_time_days":      round(p80_recovery, 1),
        "service_level":           round(mean_service, 4),
        "expected_shortage_units": round(mean_shortage, 2),
        "iterations":              n_iters,
        "assumptions":             assumptions,
        "revenue_loss_p50":        round(p50_revenue, 2),
        "revenue_loss_p90":        round(p90_revenue, 2),
        "engine":                  engine_label,
    }
