# ASA Autopilot: Autonomous Apple Search Ads Bid Management

A data-driven autonomous system for managing Apple Search Ads campaigns. It evaluates 90 days of simulated performance data daily, proposes statistically-grounded bid adjustments, and maintains strict operational guardrails—all proposal-only (`executed=0` for safety).

## What It Does

**Input:** 90 days of simulated Apple Search Ads performance data (mock_data/continuous_90day.json):
- 152,820 keyword-day rows (1,698 keywords × 90 days)
- Real-world distributions: impressions, taps, installs, spend, CPA per keyword per day
- Four campaign types (Brand, Competitor, Generic, Discovery) across 56 campaigns and 14 geos

**Processing:** Daily evaluation loop (evaluation_loop.py):
1. For each day, aggregate trailing 7 days of settled data (respecting Apple's 2-day reporting lag)
2. Calculate windowed CPA for each keyword: `sum(spend_7d) / sum(installs_7d)`
3. Apply decision logic tuned to campaign type
4. Enforce guardrails: 9-day cooldown, max 20% bid movement, wasted-spend pause triggers
5. Log every decision with reasoning and proposed bid values

**Output:** Audit log (results/audit_log.csv):
- 152,820 verdicts (one per keyword per day)
- Columns: action_type, before_value, after_value, windowed_cpa, target_cpa, reasoning, guardrail_status, executed=0

**Interface:** Streamlit dashboard (dashboard.py):
- Settings: Configure CPA targets, cooldown, bid movement cap, Discovery rules
- Evaluation viewer: Browse audit log by date, download full CSV
- Raw data viewer: Inspect simulated input, download CSV
- Spend allocation monitor: Track campaign-type spend share vs. strategic guidelines

## Core Logic

### Campaign-Type-Aware Decisions

**Brand, Competitor, Generic:** Optimize CPA against target

- CPA < target: bid increase (up to 20% cap)
- CPA > target: bid decrease (up to 20% cap)
- Within 4% tolerance of target: no action
- Zero installs + £20+ spend: pause (wasted spend)

**Discovery:** Exploration strategy, NOT optimized on CPA

- CPA ≤ target + ≥15 installs: graduate to core campaign
- CPA > target + consuming ≥15% of campaign spend: negativize
- CPA > target for ≥28 calendar days: pause (grace period expired)
- Otherwise: hold and monitor

### CPA-Proportional Bid Adjustment

For actions that change bids, the adjustment scales with distance from target:

```
pct_gap = (windowed_cpa - target_cpa) / target_cpa
adjustment = min(abs(pct_gap), 0.20)  # Capped at 20%
new_bid = current_bid × (1 ± adjustment)
```

**Examples:**
- CPA £1.10 vs target £1.00 (+10% gap) → reduce bid 10%
- CPA £1.40 vs target £1.00 (+40% gap) → capped, reduce bid 20%
- CPA £0.92 vs target £1.00 (-8% gap) → increase bid 8%

The cap prevents overshooting; changes converge over successive 9-day cycles.

### Data Maturity & Cooldown

- **Settling lag:** Only data ≥3 days old is "settled" and usable for decisions
- **Observation window:** 7 days of settled data, aggregated as sum/sum (not mean of means)
- **Decision lag:** On day N, evaluate using data through day N-2 (settled window)
- **Cooldown:** 9 days after any action (7-day window + 2-day lag = don't re-evaluate sooner)

### Geo-Tiered CPA Targets

| Tier | Geos | Target CPA |
|------|------|-----------|
| T1 | US, UK | £1.60 |
| T2 | CA, AU, DE, FR | £1.00 |
| T3 | IE, NZ, NL | £0.85 |
| T4 | SE, NO, DK, FI, IN | £0.60 |

## Configuration

All thresholds in config/parameters.json (no hardcoded values):

```json
{
  "cpa_targets": { "T1": 1.6, "T2": 1.0, "T3": 0.85, "T4": 0.6 },
  "observation_window": { "days": 7 },
  "data_settling_lag": { "days": 2 },
  "cooldown_days": { "days": 9 },
  "bid_movement": { "max_fraction": 0.2 },
  "tolerance_band": { "percent_of_target": 0.04 },
  "core_campaign_wasted_spend_pause_threshold": { "gbp": 20.0 },
  "discovery_graduation": { "min_installs_over_window": 15 },
  "discovery_negativize_threshold": { "campaign_spend_share": 0.15 },
  "discovery_pause_grace_period": { "calendar_days": 28 },
  "budget_allocation": { "brand": 0.12, "competitor": 0.23, "generic": 0.4, "discovery": 0.25 }
}
```

Edit and re-run `evaluation_loop.py` to regenerate audit log with new parameters.

## How to Run

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Launch Streamlit dashboard
streamlit run dashboard.py
```

Access at http://localhost:8502. Dashboard loads mock_data/continuous_90day.json and results/audit_log.csv.

### Regenerate Audit Log

```bash
# Run the evaluation loop (produces results/audit_log.csv)
python3 evaluation_loop.py
```

Outputs:
- results/audit_log.csv: All 152,820 verdicts
- Console: Summary statistics and action breakdown

### Verify Correctness

```bash
# Run verification suite (6 checks)
python3 verify_checks.py
```

Confirms:
- Simulator independence (raw data unaffected by audit log)
- Cooldown enforcement (≥9 days between actions)
- Geo-tier CPA mapping (correct targets used)
- Discovery logic (no CPA-vs-target reasoning in core optimization)
- Scale (56 campaigns, ~1,700 keywords/day, 90 days)

## Architecture

### Files

```
asa-autopilot/
├── evaluation_loop.py              # Core engine: 90-day simulation loop
├── dashboard.py                    # Streamlit UI
├── verify_checks.py                # 6-check verification suite
├── config/
│   └── parameters.json             # All tunable thresholds
├── mock_data/
│   └── continuous_90day.json       # Simulated 90-day dataset
├── results/
│   └── audit_log.csv               # Output verdicts (152,820 rows)
└── requirements.txt                # Dependencies
```

### Evaluation Loop Flow

1. **Load data:** mock_data/continuous_90day.json (1,698 unique keywords)
2. **Index:** Map keywords by date and campaign
3. **Pre-compute:** Calculate windowed CPA for all keyword-date combos
4. **Daily loop (90 iterations):**
   - For each keyword with data on that day:
     - Compute 7-day windowed CPA (if settled data exists)
     - Apply campaign-type decision logic
     - Check cooldown guardrail
     - Log verdict with reasoning and proposed values
5. **Export:** results/audit_log.csv with all verdicts

## Design Rationale

### Proposal-Only (executed=0)

All 152,820 audit log rows have `executed=0`. Why?

- Every decision is logged before anything is sent
- System can be audited, understood, and tuned without live consequences
- When real API integration begins, audit log becomes a clear hand-off to execution
- Prevents accidental harm from buggy logic

### Simulated Data

This is a decision engine, not a production API client. The simulator:
- Generates realistic 90-day trajectories (continuous, not random daily noise)
- Remains **completely independent** from decisions (no feedback loops)
- Allows thorough testing of optimization logic without real credentials
- Ideal for portfolio demonstration and further development

### Why These Numbers?

- **7-day observation window:** Balances responsiveness (shorter = more noise; longer = stale) with stability
- **2-day settling lag:** Reflects real Apple reporting finalization
- **9-day cooldown:** 7 days observation + 2 days lag = don't make overlapping decisions
- **20% bid cap:** Large enough to make progress, small enough to avoid ringing
- **15 install threshold for Discovery:** Minimum signal for "graduating" a keyword from exploration
- **28-day Discovery grace:** Long enough for new keywords to show signal, short enough to pause wasted spend
- **15% spend share for negativize:** High enough to ignore low-volume noise, low enough to catch waste

## What This Is NOT

- **Not a production API client:** No real Apple Search Ads credentials required; no live API calls
- **Not a real deployment:** All data is simulated; all decisions are proposals
- **Not decision advice:** The thresholds and logic are examples for demonstration, not real optimization settings
- **No real marketing impact:** This is a technical exercise in autonomous decision-making

## Next Steps (Future Work)

- Real Apple Search Ads API integration (read-only first)
- Execution module to send approved actions to API
- Approval workflow (human review before bid changes)
- Real-time monitoring dashboard with live performance
- Sensitivity analysis (what if we change thresholds?)

## Tech Stack

- **Python 3.9+**
- **Streamlit** (dashboard)
- **Pandas** (data manipulation)

---

**Built as a portfolio project demonstrating autonomous decision-making, data-driven optimization under constraints, and production-quality logging on simulated data.**
