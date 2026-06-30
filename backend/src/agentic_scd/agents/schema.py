from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class EventAnalysis(BaseModel):
    signal_id: str
    event_type: str
    entities: list[str] = Field(default_factory=list)
    extracted_region: str | None = None
    severity_hint: str | None = None
    summary: str = ""


class Classification(BaseModel):
    signal_id: str
    category: str
    risk_score: float = Field(default=0.0, ge=0, le=1)
    severity: float = Field(default=0.0, ge=0, le=10)
    confidence: float = Field(default=0.75, ge=0, le=1)
    risk_level: str = "LOW"
    route: str = "monitor_only"
    rationale: str = ""

    @model_validator(mode="after")
    def fill_derived_fields(self):
        if not self.severity and self.risk_score:
            self.severity = round(self.risk_score * 10, 2)
        if not self.risk_level or self.risk_level == "LOW":
            if self.severity > 7:
                self.risk_level = "HIGH"
                self.route = "high_path_simulation_first"
            elif self.severity >= 4:
                self.risk_level = "MEDIUM"
                self.route = "full_path"
            else:
                self.risk_level = "LOW"
                self.route = "monitor_only"
        return self


class ImpactMap(BaseModel):
    signal_id: str
    affected_entities: list[str] = Field(default_factory=list)
    affected_suppliers: list[str] = Field(default_factory=list)
    affected_lanes: list[str] = Field(default_factory=list)
    affected_facilities: list[str] = Field(default_factory=list)
    product_categories: list[str] = Field(default_factory=list)
    retrieved_context: list[str] = Field(default_factory=list)
    reasoning: str = ""

    @model_validator(mode="after")
    def fill_entities(self):
        merged = list(self.affected_entities)
        merged.extend(self.affected_suppliers)
        merged.extend(self.affected_lanes)
        merged.extend(self.affected_facilities)
        self.affected_entities = list(dict.fromkeys(item for item in merged if item))
        return self


class Forecast(BaseModel):
    dates: list[str] = Field(default_factory=list)
    baseline: list[float] = Field(default_factory=list)
    adjusted: list[float] = Field(default_factory=list)
    demand_deviation_pct: float = 0.0
    inventory_days_left: float = 0.0
    predicted_delay_days: float = 0.0
    mape_estimate: float = 0.0
    note: str = ""


class Simulation(BaseModel):
    stockout_probability: float = Field(default=0.0, ge=0, le=1)
    revenue_impact: float = 0.0
    recovery_time_days: float = 0.0
    service_level: float = Field(default=1.0, ge=0, le=1)
    expected_shortage_units: float = 0.0
    iterations: int = 0
    assumptions: str = ""
    revenue_loss_p50: float = 0.0
    revenue_loss_p90: float = 0.0


class MitigationAction(BaseModel):
    action: str
    urgency: str
    expected_impact: str
    owner: str


class Recommendation(BaseModel):
    actions: list[str] = Field(default_factory=list)
    structured_actions: list[MitigationAction] = Field(default_factory=list)
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)
