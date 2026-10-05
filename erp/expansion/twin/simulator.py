#!/usr/bin/env python3
"""
Digital twin simulation engine.
Run product launches, campaigns, org changes and predict business + customer impact.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import json


@dataclass
class Department:
    name: str
    code: str
    capacity_hours_week: int
    members: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)


@dataclass
class SimulationScenario:
    scenario_type: str  # product_launch, campaign, org_change
    description: str
    budget_usd: Optional[float] = None
    launch_date: Optional[str] = None
    channels: List[str] = field(default_factory=list)
    target_market: str = "unknown"
    team_deployments: Dict[str, int] = field(default_factory=dict)
    duration_weeks: int = 24


@dataclass
class SimulationResult:
    trajectory: Dict[str, List[float]]
    impact_assessment: Dict[str, str]
    risk_flags: List[str]
    baseline_variant: bool = False

    def to_dict(self) -> Dict:
        return {
            "trajectory": self.trajectory,
            "impact_assessment": self.impact_assessment,
            "risk_flags": self.risk_flags,
            "baseline_variant": self.baseline_variant
        }


class DigitalTwinSimulator:
    """Core simulation engine — autonomous, non-blocking."""

    def __init__(self, departments: Optional[Dict[str, Department]] = None, baseline_model: bool = True):
        self.departments: Dict[str, Department] = departments if departments is not None else {}
        self._baseline_model: bool = baseline_model

    def simulate(self, scenario: SimulationScenario) -> SimulationResult:
        if scenario.scenario_type == "product_launch":
            return self._simulate_product_launch(scenario)
        elif scenario.scenario_type == "campaign":
            return self._simulate_campaign(scenario)
        elif scenario.scenario_type == "org_change":
            return self._simulate_org_change(scenario)
        else:
            raise ValueError(f"Unknown scenario type: {scenario.scenario_type}")

    def _simulate_product_launch(self, scenario: SimulationScenario) -> SimulationResult:
        """Predict revenue, headcount, deadline shifts, NPS for a product launch."""
        trajectory = {
            "revenue_usd": self._compute_revenue_curve(scenario),
            "headcount": self._compute_headcount_change(scenario),
            "deadline_shifts": self._compute_deadline_impact(scenario),
            "customer_nps_delta": self._compute_nps_delta(scenario)
        }
        impact = {
            "business": self._assess_business_impact(trajectory, scenario),
            "customer": self._assess_customer_impact(trajectory, scenario)
        }
        risks = self._assess_risks(trajectory, scenario)
        return SimulationResult(trajectory=trajectory, impact_assessment=impact, risk_flags=risks)

    def _compute_revenue_curve(self, scenario: SimulationScenario) -> List[float]:
        weeks = scenario.duration_weeks
        budget = scenario.budget_usd or 100000
        # Simplified logistic adoption curve
        rate = 0.15 if scenario.target_market in ("mid_market_saa", "enterprise") else 0.08
        curve = []
        for w in range(weeks + 1):
            revenue = budget * rate * (1 - 1 / (1 + 0.1 * w)) * (1 + 0.3 * min(w / 12, 1))
            curve.append(round(revenue, 2))
        return curve

    def _compute_headcount_change(self, scenario: SimulationScenario) -> List[float]:
        weeks = scenario.duration_weeks
        initial = 20
        growth = {
            "mid_market_saa": 0.15,
            "enterprise": 0.12,
            "small_business": 0.08,
            "unknown": 0.10
        }
        rate = growth.get(scenario.target_market, 0.10)
        return [round(initial * (1 + rate * (w / 12)), 1) for w in range(weeks + 1)]

    def _compute_deadline_impact(self, scenario: SimulationScenario) -> List[float]:
        """Returns projected deadline shift in weeks (positive = later)."""
        weeks = scenario.duration_weeks
        deployments = scenario.team_deployments
        eng_load = deployments.get("ENG", 0) * 1.5
        sls_load = deployments.get("SLS", 0) * 1.2
        base_shift = 0.5 if eng_load > 0 else 0
        return [round(base_shift + (eng_load * w / weeks), 2) for w in range(weeks + 1)]

    def _compute_nps_delta(self, scenario: SimulationScenario) -> List[float]:
        """Projected NPS delta over time."""
        weeks = scenario.duration_weeks
        peak = 15 if scenario.target_market == "enterprise" else 12
        curve = []
        for w in range(weeks + 1):
            nps = peak * min(1.0, w / 8)
            curve.append(round(nps, 1))
        return curve

    def _assess_business_impact(self, trajectory: Dict, scenario: SimulationScenario) -> str:
        final_revenue = trajectory["revenue_usd"][-1]
        initial_rev = trajectory["revenue_usd"][0] if trajectory["revenue_usd"][0] > 0 else 1
        return (f"Projected revenue +${final_revenue/1e6:.2f}M by end of cycle "
                f"({scenario.duration_weeks} weeks). Headcount growth ~{trajectory['headcount'][-1]}+ "
                f"team members. Revenue growth: +{final_revenue/initial_rev:.1f}x "
                f"from launch.")

    def _assess_customer_impact(self, trajectory: Dict, scenario: SimulationScenario) -> str:
        final_nps = trajectory["customer_nps_delta"][-1]
        return (f"Projected NPS delta: +{final_nps:.1f} pts by end of cycle. "
                f"Early-adopter satisfaction peaks in weeks 6-12, stabilizes at +{final_nps:.0f} pts.")

    def _assess_risks(self, trajectory: Dict, scenario: SimulationScenario) -> List[str]:
        risks = []
        max_shift = trajectory["deadline_shifts"][-1]
        if max_shift > 3:
            risks.append(f"Budget overrun risk >40% if deadlines shift >{max_shift} weeks")
        if trajectory["headcount"][-1] > 30:
            risks.append("Hiring ramp may exceed budget if team grows >30 people")
        if not risks:
            risks.append("No major risk flags; monitor weekly KPIs")
        return risks

    def is_baseline_variant(self) -> bool:
        return self._baseline_model

    def run_as_agent(self, scenario: Dict) -> SimulationResult:
        """Run simulation as autonomous Singularity agent (non-blocking)."""
        sc = SimulationScenario(**scenario)
        return self.simulate(sc)


def main():
    sim = DigitalTwinSimulator()
    scenario = {
        "scenario_type": "product_launch",
        "description": "Launch AI analytics product to enterprise tier",
        "budget_usd": 500000,
        "launch_date": "2025-12-01",
        "channels": ["email", "paid", "outbound"],
        "target_market": "enterprise",
        "team_deployments": {"ENG": 4, "SLS": 6, "MKT": 3},
        "duration_weeks": 24
    }
    result = sim.run_as_agent(scenario)
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
