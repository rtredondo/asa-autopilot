# ASA Autopilot: Project State & Design Decisions

**Updated:** 2026-09-02  
**Phase:** Settings panel complete; next: results visualization

---

## What This Project Is

**ASA Autopilot** is an autonomous bidding system for Apple Search Ads. It evaluates campaign and keyword performance daily, proposes bid adjustments, budget shifts, and keyword pruning—all within strict guardrails to prevent runaway spend.

**Key Principle:** The system runs on **simulated data**, not real Apple API credentials. Simulations are completely independent from the decision algorithm—the system's proposed actions are never fed back into the simulator. This independence is deliberate and core to the design.

---

## The Pivot: Why Simulated Data

**Problem:** Apple's API is read-write only (no read-only mode), and the CEO will not hand over production credentials. This blocks real API integration.

**Solution:** Build the system against a high-fidelity simulator that generates realistic ASA data independently, with natural variation. The decision engine is thoroughly tested in simulation before any real credential work.

**Non-Negotiable:** The simulator must remain completely independent. Proposed actions NEVER influence future simulated data—this prevents false confidence from positive feedback loops and ensures the decision engine is evaluated on its actual logic, not on gaming the simulation.

---

## Core Design Decisions

### 1. Campaign-Type-Aware Modeling
The account structure explicitly accounts for different campaign purposes:

- **Brand:** 5–15 keywords per campaign, low volume, high CVR, CPA typically well below target (stable, efficient)
- **Competitor:** 20–40 keywords per campaign, CPA near or above target, moderate volatility
- **Generic:** 40–70 keywords per campaign, highest volume, CPA at target with real variance (the account workhorse)
- **Discovery:** 40–70 keywords per campaign of low-history, noisy, poor-CPA terms with high churn (Search Match / broad-match exploration)

Every keyword row includes a `campaign_type` field so the decision engine can branch logic per type.

### 2. Explicit Campaign-Type Logic
Decision engine behavior differs by type:

- **Brand, Competitor, Generic:** Full CPA-vs-target optimization (bid changes, pauses, budget shifts)
- **Discovery:** Treated as budget-contained exploration. NOT judged or paused on CPA. Keywords pruned on volume/churn, not cost-per-action. Managed via explicit `exploration_budget` field (capped spend-to-learn allowance)

### 3. Data Maturity & Settling Lag
Performance data is time-sensitive in ASA—Apple finalizes install and cost data with a ~2-day lag:

- **Provisional:** Most recent 2 days (data still settling, unreliable)
- **Settled:** Days 3+ back (finalized, safe to trust)

Every keyword row includes a `data_maturity` field. Decision engine uses ONLY settled data.

### 4. Decision Window: 7-Day Aggregation
Decisions are based on a **trailing 7 settled days**, aggregated as:

```
CPA = sum(spend over 7 days) / sum(installs over 7 days)
```

NOT the mean of daily CPAs (mean of means is wrong). This prevents noisy single-day outliers from triggering false decisions.

### 5. Cooldown: 9 Days Total
After a change, cooldown = 7-day decision window + 2-day settling lag = 9 days. A re-evaluation window never straddles a prior change.

### 6. Campaign Structure
**Account: 56 campaigns** = 4 types × 14 storefronts

**Storefronts:** US, UK, CA, AU, IE, NZ, NL, SE, NO, DK, FI, DE, FR, IN

**Geo Tiers & CPA Targets:**
- T1 (US, UK): £1.60/install
- T2 (CA, AU, DE, FR): £1.00/install
- T3 (IE, NZ, NL): £0.85/install
- T4 (SE, NO, DK, FI, IN): £0.60/install

**Keyword Distribution:** 1,500–2,000 total keywords, ~30 per campaign average. Brand campaigns skew low, Generic/Discovery skew high.

### 7. Daily Cycle
Each simulated day at ~15:00 UTC:
1. Pull latest data
2. Evaluate (apply decision logic to settled data only)
3. Propose action OR explicit no-action
4. Check guardrails
5. Record verdict (action type, reasoning, guardrail status, timestamp)

### 8. Run Duration & Continuous Trajectories
Simulations span **90 daily cycles** (2026-06-03 to 2026-08-31). Long enough to see CPA trends, seasonal variation, and decision impact; short enough to iterate.

**Critical:** Each keyword has a **persistent underlying trajectory** across 90 days. Baselines follow a gentle random walk (baseline metric today = baseline metric yesterday + drift + mean-reversion). Daily noise is layered on top. This creates continuity: a trending keyword stays in its trend for multiple days (not random day-to-day swings). Events (competitor_spike, volume_surge, dying_keyword) are injected randomly to last 3–10 days, exercising decision engine branches without dominating the run.

**Why:** A trailing-7-day aggregation window is meaningless on random noise. Continuous trajectories make the window powerful—the 7-day CPA reflects real performance momentum, not noise. The decision engine sees real optimization opportunities: trending-up keywords to bid on, deteriorating ones to pause, Budget spikes to scale.

---

## Data Model

### Keyword Row (One Per Day Per Keyword)

```python
{
  "campaign_id": "1000",           # Stable across days
  "campaign_name": "EQLS_US_Brand", # Stable
  "campaign_type": "brand",         # One of: brand, competitor, generic, discovery
  "keyword_id": "10000000",
  "keyword_text": "equalization app",
  "date": "2026-08-18",            # Day of this data
  "data_maturity": "settled",      # settled | provisional
  
  # Primitives (what Apple reports)
  "impressions": 150,
  "taps": 12,
  "installs": 3,
  "spend": 2.85,                  # GBP
  
  # Derived metrics
  "cpt": 0.19,                    # Cost per tap = spend / taps
  "ttr": 0.08,                    # Tap-through rate = taps / impressions
  "cvr": 0.25,                    # Click-to-install = installs / taps
  "cpa": 0.95,                    # Cost per action = spend / installs (null if installs=0)
  
  "tier": "T1",                   # Geo tier
  "target_cpa": 1.60,             # CPA target for this tier
  "bid_amount": 0.80,             # Current bid (GBP)
  "status": "enabled"             # enabled | paused
}
```

### Campaign Row (Aggregate Per Day)

```python
{
  "campaign_id": "1000",
  "campaign_name": "EQLS_US_Brand",
  "campaign_type": "brand",
  "date": "2026-08-18",
  "tier": "T1",
  "target_cpa": 1.60,
  
  # Aggregates from keywords
  "impressions": 1500,
  "taps": 120,
  "installs": 35,
  "spend": 45.00,
  "cpa": 1.29,                   # Calculated: spend / installs
  
  # Budget & constraints
  "daily_budget": 500.00,         # Generous, non-binding (£400–800)
  "exploration_budget": null,     # For discovery only; capped 'learn' allowance
  "status": "enabled"
}
```

---

## Current Build Status

### What Exists (v1 Foundation)

✅ **Core modules:** auth, API client, decision engine, guardrails, state store, logging  
✅ **Dashboard:** Streamlit UI with action proposals and guardrail status  
✅ **Campaign-type-aware simulator:** One day of data (56 campaigns, 1,726 keywords)  
✅ **90-day continuous simulator:** Full 90-day run with persistent trajectories (1,720 keywords, 159,030 daily rows)  
✅ **Central parameter config:** `config/parameters.json` with all tunable thresholds (CPA targets, cooldown, observation window, Discovery rules, etc.)  
✅ **90-day evaluation loop:** `evaluation_loop.py` with campaign-type-aware decision logic and full audit logging to CSV

### Parameter Config & Evaluation Loop (This Session)

✅ **Completed This Session**

**Part 1: Central Parameter Config**
- ✅ Created `config/parameters.json`: single source of truth for all tunable thresholds including:
  - Budget allocation splits (brand 12%, competitor 23%, generic 40%, discovery 25%)
  - CPA targets by tier (T1 £1.60, T2 £1.00, T3 £0.85, T4 £0.60)
  - Observation window: 7 days of settled data
  - Data settling lag: 2 days
  - Cooldown: 9 days after any action
  - Max bid movement: 20% per cycle
  - Wasted spend threshold: £20 (pause trigger for core campaigns)
  - Discovery graduation: min 20 installs + CPA at or below target
  - Discovery negativize: 15% campaign spend share at above-target CPA
  - Discovery pause grace: 28 calendar days underperforming

**Part 2: 90-Day Evaluation Loop**
- ✅ Built `evaluation_loop.py`: complete daily evaluation system
  - Steps through 90 days (2026-06-03 to 2026-08-31)
  - Evaluates all 1,720 keywords using settled data only (7-day window ending D-2)
  - Computes windowed CPA as sum(spend)/sum(installs), not mean of daily CPAs
  - Campaign-type-aware logic:
    - **Brand/Competitor/Generic:** Full CPA-vs-target optimization (bid changes, pauses)
    - **Discovery:** Exploration logic (graduate/hold/negativize/pause) with 28-day grace period
  - Enforces guardrails: 9-day cooldown, data maturity gating
  - Logs all verdicts: 159,030 total (1 per keyword per day)
  - Exports audit log to CSV: `results/audit_log.csv`

**Verification Results (90-day run)**
- Total verdicts: 159,030
- Action breakdown:
  - **bid_decrease**: 8,099 (56.8% of actions) — core campaigns over target
  - **bid_increase**: 1,430 (10.0% of actions) — Brand campaigns under target
  - **pause**: 4,721 (33.1% of actions) — wasted spend + Discovery grace expired
- Actions blocked by cooldown: 111,705 (preventing rapid re-optimization)
- Campaign-type correctness:
  - **Brand** (986 actions): 96% bid increases, 4% bid decreases ✓ (efficient, below target)
  - **Competitor** (2,783 actions): 92.8% bid decreases, 7.2% bid increases ✓ (near/above target)
  - **Discovery** (4,676 actions): 100% pauses ✓ (exploratory terms underperforming after grace period)
  - **Generic** (5,805 actions): 94.4% bid decreases, 4.9% bid increases, 0.8% pauses ✓ (workhorse, near target)

### Settings Panel (This Session)

✅ **Completed: Streamlit settings UI for `config/parameters.json`**
- **dashboard.py**: Settings panel + Run Evaluation interface
- **Settings tab** displays all parameters grouped logically:
  - CPA Targets (T1-T4, GBP per install)
  - Timing Windows (observation window, settling lag, cooldown days)
  - Bid Rules (max movement, tolerance band, wasted-spend pause threshold)
  - Discovery Rules (graduation installs, negativize spend share, pause grace period)
  - Budget Allocation (brand/competitor/generic/discovery splits, context only)
- **Editing** with appropriate input widgets (number inputs, sliders)
- **Save button** writes changes to `config/parameters.json` safely (temp file → replace)
- **Run Evaluation button** triggers `evaluation_loop.py` with progress indication
- **Audit log preview** shows metrics and latest verdicts

**Verification (all three confirmations passed)**:
- ✓ (a) Panel loads current values from config/parameters.json
- ✓ (b) Editing and saving actually changes the file on disk
- ✓ (c) Run Evaluation successfully regenerates audit log

### What's Next

🔲 **Planned (Next Phase)**
- Build results visualization (Evaluation tab):
  - Time-series plots: CPA vs. target over 90 days per campaign type
  - Action distribution by type and campaign
  - Cooldown impact analysis
  - Discovery vs. core performance trends
- Optional: sensitivity analysis (what if we change thresholds?)

🔲 **Future**
- Real API integration (when credentials available)
- Execution module (send actions to Apple API)
- Audit workflow (approval gates before execution)
- Performance dashboards (propose vs. actual impact)

---

## Testing & Verification Checklist

When new data simulator launches:

- [ ] Brand campaigns: ~5–15 keywords, high CVR, CPA <<< target (low variance)
- [ ] Generic campaigns: ~40–70 keywords, high volume, CPA near target (moderate variance)
- [ ] Competitor campaigns: ~20–40 keywords, CPA ≈ target (higher variance)
- [ ] Discovery campaigns: ~40–70 keywords, low history, noisy (high variance), include exploration_budget
- [ ] Total keywords: 1,500–2,000
- [ ] Total campaigns: 56 (4 types × 14 geos)
- [ ] All keyword rows include: campaign_type, data_maturity, CPA (null if installs=0)
- [ ] Campaign rows correctly aggregate keywords
- [ ] One day of complete data saves/loads without errors

---

## Key Files

- **`mock_data/campaign_simulator.py`** — Campaign-type-aware data generator (new)
- **`decision_engine/__init__.py`** — Decision logic (evaluate_bid_change, evaluate_keyword_pause, etc.)
- **`guardrails/__init__.py`** — Cooldown, spend ceiling checks
- **`state/__init__.py`** — SQLite persistence for decisions
- **`dashboard.py`** — Streamlit UI
- **`config/guardrails.py`** — All named constants (no magic numbers)
- **`config/campaign_parser.py`** — Campaign name → theme, geo parsing

---

## Design Philosophy

1. **Simulator Independence:** Proposed actions never feed back into simulator data.
2. **Campaign-Type Awareness:** Different campaign purposes → different logic.
3. **Time-Lagged Data:** Respect Apple's 2-day settling lag; only use settled data for decisions.
4. **No Magic Numbers:** All thresholds in config files, not buried in code.
5. **Audit First:** Record all decisions (approved, blocked, reasoning) from day one.
6. **Safe by Default:** Guardrails are conservative; generous budgets prevent false scarcity.

---

## Metrics & Jargon

- **Impressions (Imps):** Ad was shown
- **Taps:** User clicked ad (link click)
- **Installs:** User downloaded app after click (tap-attributed only)
- **Spend:** GBP cost to Apple
- **CPT:** Cost per tap = spend / taps
- **TTR:** Tap-through rate = taps / impressions
- **CVR:** Conversion rate = installs / taps (install rate)
- **CPA/CPI:** Cost per action/install = spend / installs (Apple calls it CPA; earlier code called it CPI)
- **CPA is null** when installs = 0 (no denominator)

---

This is the single source of truth for project direction, design decisions, and status. Update this file whenever a major design decision is made or pivoted.
