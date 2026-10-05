# Department Mapper — Real-World Company Structure

## Purpose
Map the real company into the digital twin at granular level so simulations reflect reality, not templates.

## Schema

```yaml
departments:
  - name: Engineering
    code: ENG
    head: <person_id>
    members: [<person_id>, ...]
    skills: [python, distributed_systems, ml]
    capacity_hours_week: 640
    cost_per_hour: 180
    reporting_to: CTO

  - name: Product
    code: PRD
    head: <person_id>
    members: [<person_id>, ...]
    skills: [strategy, design, data_analysis]
    capacity_hours_week: 320

  - name: Sales
    code: SLS
    head: <person_id>
    members: [<person_id>, ...]
    skills: [enterprise, negotiation, forecasting]

  - name: Marketing
    code: MKT
    head: <person_id>
    members: [<person_id>, ...]
    skills: [growth, campaigns, content]

  - name: Customer Success
    code: CS
    head: <person_id>
    members: [<person_id>, ...]
    skills: [support, onboarding, retention]

people:
  - id: p_001
    name: "Alex Voss"
    role: CEO / Head of Strategy
    department: EXEC
    skills: [executive_decision, growth, product_strategy]
    availability_hours_week: 40
    cost_per_hour: 0  # founder
    reports_to: null
    notes: "Owner — veto authority, direct escalation only"

  - id: p_002
    name: "COO"
    role: Chief Operating Officer
    department: OPS
    skills: [operations, scaling, compliance]
    availability_hours_week: 45
    reports_to: p_001
```

## Update Mechanism
- Config loaded at startup
- Can be edited via API (`PUT /api/dept/mapping`)
- Changes propagate immediately to simulation engine
- Historical versions preserved for audit