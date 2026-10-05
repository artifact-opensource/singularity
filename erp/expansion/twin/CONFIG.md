# Digital Twin Engine — What-If Simulation & Impact Prediction

## Purpose
Run product launches, campaigns, org changes and predict business + customer impact in real time.

## Core Interfaces

### `POST /api/twin/simulate`
```json
{
  "scenario": "product_launch",          // or "campaign", "org_change"
  "description": "Launch new AI analytics product to enterprise tier",
  "variables": {
    "budget_usd": 500000,
    "launch_date": "2025-12-01",
    "channels": ["email", "paid", "outbound"],
    "target_market": "mid_market_saa",
    "team_deployments": {
      "ENG": 4,
      "SLS": 6,
      "MKT": 3
    }
  },
  "duration_weeks": 24
}
```

### Returns
```json
{
  "trajectory": {
    "revenue_usd": [0, 50k, 120k, 250k, ...],
    "headcount": [20, 22, 25, 27, ...],
    "deadline_shifts": ["ENG: +2 weeks on feature X"],
    "customer_nps_delta": "+15 pts projected"
  },
  "impact_assessment": {
    "business": "high confidence +30% ARR, +12% churn reduction",
    "customer": "adoption curve 40% within 3 months, NPS +15"
  },
  "risk_flags": ["budget overrun >40% if delays >4 weeks"]
}
```

## Simulation Modules

| Module | Inputs | Outputs |
|--------|--------|---------|
| `MarketResponse` | spend, channels, target, competitor activity | adoption_rate, revenue_curve |
| `ResourceCapacity` | department assignments, headcount, capacity_hours_week | workload_balance, bottleneck_alert |
| `DeadlineEstimator` | task breakdown, team availability, priority shifts | due_dates, shift_warnings |
| `CustomerNPSModel` | product features, onboarding experience, support quality | expected_NPS_delta, retention_forecast |

## Redundancy & Autonomy
- Simulations run as Singularity agents (autonomous, no blocking)
- Result cache with TTL; re-runs auto-incremental if inputs change
- Fallback baseline model if primary model unavailable