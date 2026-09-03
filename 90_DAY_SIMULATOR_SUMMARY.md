# 90-Day Continuous Simulator: Complete Implementation

**Date:** 2026-08-18  
**Status:** ✅ Complete and Verified

---

## What Was Built

**File:** `mock_data/continuous_simulator.py` (500+ lines)

A production-ready 90-day simulator that generates realistic Apple Search Ads data with:
- **Continuous performance trajectories** per keyword (random walk with mean-reversion, not daily noise)
- **Campaign-type-aware baselines** (Brand efficient, Competitor near-target, Generic at-target, Discovery noisy/explored)
- **Event injection** (competitor_spike, volume_surge, dying_keyword lasting 3–10 days)
- **Data maturity tracking** (last 2 days provisional, others settled)
- **Raw output** (one row per keyword per day, primitives + daily metrics, no pre-computed 7-day CPA)
- **Complete independence** from decision engine (simulator never reads proposed actions)

---

## Output: 90-Day Dataset

**File:** `mock_data/continuous_90day.json` (60 MB)

### Structure
- **Date Range:** 2026-08-15 to 2026-11-12 (90 days)
- **Campaigns:** 56 (4 types × 14 geos)
- **Keywords:** 1,720
- **Daily Rows:** 154,800 (1,720 keywords × 90 days)
- **Campaign Daily Rows:** 5,040 (56 campaigns × 90 days)

### Key Numbers
| Type | Campaigns | Avg Keywords | Avg CPA | Min CPA | Max CPA | Characteristics |
|------|-----------|---|---|---|---|---|
| Brand | 14 | 23 | £0.77 | £0.41 | £1.59 | Efficient, stable |
| Competitor | 14 | 25 | £1.07 | £0.64 | £2.15 | Near-target, volatile |
| Generic | 14 | 37 | £1.13 | £0.68 | £2.18 | Workhorse, good volume |
| Discovery | 14 | 37 | £2.52 | £1.38 | £4.91 | Noisy, explored, above-target |

---

## Critical Design: Continuous Trajectories

### The Problem With Daily Noise
If each day's performance were generated independently (random draw), a 7-day aggregation window would smooth noise but miss real trends. A keyword could spike one day and plummet the next—no signal, just noise.

### The Solution: Persistent Baselines
Each keyword has a **baseline trajectory** that evolves slowly:
- **Day 1:** Initialize baseline (CPT, TTR, CVR) based on campaign type
- **Day 2–90:** Apply slow drift to baseline (random walk with mean-reversion)
- **Every day:** Add daily noise on top

Example pseudo-code:
```python
baseline_cpt_today = baseline_cpt_yesterday + small_drift + mean_reversion_pull
daily_cpt = baseline_cpt_today + random_noise
```

This creates:
- **Continuity:** A keyword's CPA trend lasts multiple days (not random oscillation)
- **Signal:** A 7-day window captures real momentum, not noise
- **Realism:** Performance drifts (keyword quality might improve or decay), but gradually

### Events: Multi-Day Variance
Events are injected to create realistic patterns:
- **competitor_spike:** CPT rises gradually over 3–7 days (e.g., competitor increases bids)
- **volume_surge:** Impressions spike 50–150% for 3–10 days (e.g., viral search, seasonal spike)
- **dying_keyword:** CVR collapses to near-zero permanently (e.g., Apple algorithm change, irrelevant keyword)

Events are rare (~0.1% chance per keyword per day) so most keywords drift naturally, but enough are triggered so the decision engine gets to exercise all branches (bid up, bid down, pause).

---

## Data Model

### Keyword Daily Row

```json
{
  "campaign_id": "1000",
  "campaign_name": "EQLS_US_Brand",
  "campaign_type": "brand",
  "keyword_id": "10000000",
  "keyword_text": "equalization app",
  "date": "2026-08-15",
  "data_maturity": "settled",
  
  "impressions": 310,
  "taps": 31,
  "installs": 8,
  "spend": 6.54,
  
  "cpt": 0.2110,
  "ttr": 0.1000,
  "cvr": 0.2581,
  "cpa": 0.82,
  
  "tier": "T1",
  "target_cpa": 1.60,
  "bid_amount": 0.91,
  "status": "ENABLED"
}
```

### Data Maturity
- **Day 1–88:** `"data_maturity": "settled"` (97.8% of rows)
- **Day 89–90:** `"data_maturity": "provisional"` (2.2% of rows)

The decision engine should only evaluate settled data when building a 7-day trailing window.

### Campaign Daily Row

```json
{
  "campaign_id": "1000",
  "campaign_name": "EQLS_US_Brand",
  "campaign_type": "brand",
  "date": "2026-08-15",
  "data_maturity": "settled",
  "tier": "T1",
  "target_cpa": 1.60,
  
  "impressions": 4535,
  "taps": 414,
  "installs": 100,
  "spend": 94.46,
  "cpa": 0.94,
  
  "daily_budget": 675.15,
  "exploration_budget": null,
  "status": "ENABLED"
}
```

---

## Sample Trajectories: Proof of Continuity

### Brand Keyword (EQLS_DE_Brand: "audio processing")
Target CPA: £1.00
```
Day   1-10: 1.00 0.94 0.71 0.72 1.00 1.01 0.91 0.84 0.82 0.84
Day  11-20: 0.66 0.64 0.84 0.78 0.92 1.03 0.82 0.96 0.88 0.93
Day  21-30: 0.78 0.86 1.03 0.70 1.06 0.87 0.93 0.87 0.78 0.74
Day  31-40: 0.75 0.91 0.96 0.88 0.68 0.72 0.84 0.79 0.81 0.81
Day  41-50: 0.80 0.72 0.76 0.97 0.78 0.79 0.85 1.27 0.73 0.87
Day  51-60: 0.92 0.61 0.91 0.89 0.76 1.12 0.81 0.80 0.85 1.07
Day  61-70: 0.85 0.93 0.98 0.94 0.82 0.87 0.94 1.11 1.08 1.12
Day  71-80: 0.69 0.88 0.76 0.74 0.89 0.83 0.93 1.01 0.90 0.73
Day  81-90: 0.87 0.76 0.97 0.89 0.83 0.70 0.80 0.86 0.92 1.01

Pattern: Continues around £0.75–£1.00, efficient and stable (no wild swings)
```

**Decision Engine Sees:** This keyword is consistently beating target by 5–25%. A decision to increase bid would be justified across a multi-day 7-day window, not on noise.

### Generic Keyword (EQLS_NZ_Generic: "eq studio")
Target CPA: £0.85
```
Day   1-10: 0.82 0.85 0.77 0.74 0.75 0.75 0.85 1.01 0.97 0.79
Day  11-20: 0.96 0.79 0.81 1.23 1.03 0.70 0.74 0.98 0.88 0.83
Day  21-30: 0.82 1.15 0.92 0.94 0.99 1.03 1.14 1.15 1.48 1.56
Day  31-40: 0.85 0.81 0.86 0.92 0.83 1.06 0.89 0.93 1.03 0.80
Day  41-50: 1.00 1.07 0.73 0.93 0.73 0.75 0.73 1.05 0.68 0.70
Day  51-60: 1.11 0.85 0.86 1.23 1.05 1.19 0.78 1.15 0.75 0.86
Day  61-70: 1.12 0.88 0.91 0.88 0.96 0.84 1.02 0.82 1.11 0.95
Day  71-80: 0.86 0.88 0.89 0.92 1.08 0.92 1.05 0.99 1.11 0.87
Day  81-90: 0.84 0.79 0.82 0.67 0.90 1.28 0.90 1.10 0.96 1.18

Pattern: Varies more than Brand (£0.67–£1.56), but stays around target (~£0.90 avg)
Note Days 21–30: CPA rises (potentially an event like volume_surge causing CPT inflation)
Note Days 31–40: CPA recovers (event ends or noise regresses to mean)
```

**Decision Engine Sees:** Oscillation around target. Days 21–30 signal rise in cost (maybe increase budget more carefully). Days 31–40 signal recovery. Overall: hold bid, monitor.

### Discovery Keyword (EQLS_AU_Discovery: "equalizer pro")
Target CPA: £1.00 (note: with 2.5× avg CPA this type is not optimized for cost)
```
Day   1-10: 2.32 null 4.39 null 3.04 null 3.30 3.10 3.62 2.24
Day  11-20: 3.25 null 3.43 2.83 4.14 null 2.00 2.29 3.05 null
Day  21-30: 1.81 null 2.82 3.13 null null 2.59 null null null
Day  31-40: 2.17 null null 4.64 2.20 2.43 1.92 null null 2.20
Day  41-50: 2.79 2.07 2.82 2.69 2.89 1.71 null 2.90 2.80 2.12
Day  51-60: 3.20 null 2.36 2.26 2.71 2.28 2.06 2.13 2.49 2.76
Day  61-70: null null 3.24 null null 3.62 null 1.44 2.12 null
Day  71-80: 2.40 null null null 2.74 null 3.47 null null null
Day  81-90: null null null 2.56 2.20 null null 2.72 2.72 2.72

Pattern: High churn (50% of days are null = installs=0, CPA undefined)
When converting: CPA ranges £1.44–£4.64 (well above target)
Days 61–70: Particularly noisy (many nulls, varied CPAs)
```

**Decision Engine Sees:** This is Discovery—don't optimize CPA, manage by budget and churn. Keyword is explored but low-return. Keep in rotation as exploration tax, cap spend.

---

## Integration Points: Ready for Decision Engine

The 90-day dataset is **raw and complete**. Decision engine should:

1. **Load daily data** for the current evaluation day
2. **Check data_maturity** on each row (only use settled)
3. **Gather prior 7 settled days** from the dataset
4. **Aggregate:** sum(spend) / sum(installs) over those 7 days → CPA
5. **Branch on campaign_type**:
   - Brand/Competitor/Generic: Evaluate bid changes, pauses, budget shifts
   - Discovery: Evaluate budget (exploration_budget cap), churn rate (pause on high churn, not CPA)
6. **Check guardrails** (9-day cooldown, 10% spend ceiling)
7. **Log decision** (action type, before/after, reasoning, guardrail status)

**NOT needed:** No special simulator logic. The 90-day data is pre-generated, fixed, independent. Decision engine reads it as if it's real API data.

---

## Files & Directories

**New Files:**
- `mock_data/continuous_simulator.py` (500+ lines) — Simulator implementation
- `mock_data/continuous_90day.json` (60 MB) — Generated 90-day dataset
- `90_DAY_SIMULATOR_SUMMARY.md` (this file) — Documentation

**Unchanged:**
- `mock_data/campaign_simulator.py` — One-day generator (for reference)
- `mock_data/campaign_data.json` — One-day snapshot
- All decision engine, guardrails, state store, dashboard files

---

## Verification Checklist

✅ 56 campaigns (4 types × 14 geos)  
✅ 1,720 keywords (within 1,500–2,000 target)  
✅ 90 days (2026-08-15 to 2026-11-12)  
✅ 154,800 daily keyword rows  
✅ 5,040 daily campaign rows  
✅ Brand: avg CPA £0.77 (efficient, below target) ✓  
✅ Competitor: avg CPA £1.07 (near target, volatile) ✓  
✅ Generic: avg CPA £1.13 (near target, volume workhorse) ✓  
✅ Discovery: avg CPA £2.52 (explored, not optimized) ✓  
✅ Data maturity correct (97.8% settled, 2.2% provisional) ✓  
✅ Campaign-type fields present on all rows ✓  
✅ Geo tier fields present on all rows ✓  
✅ CPA null when installs = 0 ✓  
✅ All derived metrics calculated correctly ✓  
✅ Campaign aggregates computed from keywords ✓  
✅ Continuous trajectories verified (multi-day trends visible) ✓  
✅ JSON loads without errors ✓

---

## Key Statistics

**Total Rows:** 159,840 (154,800 keyword + 5,040 campaign dailies)  
**Total Spend (90 days):** ~£250K–£300K (typical ASA account scale)  
**Total Installs (90 days):** ~150K–180K  
**Keyword Count Variance:** Minimal (1,720 stays stable across all 90 days)  
**Data Size:** 60 MB (reasonable for decision engine to load and iterate)

---

## Next Steps: Decision Engine Integration

### Phase 1: Campaign-Type-Aware Logic
Modify `decision_engine/__init__.py` to branch on `campaign_type`:

```python
if keyword["campaign_type"] == "discovery":
    # Budget-constrained exploration (not CPA-judged)
    # Evaluate churn rate, keyword age, budget spend
else:
    # Brand/Competitor/Generic: Full CPA optimization
    # Evaluate bid changes, pauses, budget shifts
```

### Phase 2: Data Maturity Gating
Only evaluate settled data:

```python
if keyword["data_maturity"] == "provisional":
    continue  # Skip most recent 2 days
```

### Phase 3: 7-Day Aggregation
Replace single-day CPA with trailing-7-day:

```python
settled_rows = get_prior_7_settled_days(keyword_id)
agg_cpa = sum(r["spend"] for r in settled_rows) / sum(r["installs"] for r in settled_rows)
```

### Phase 4: Daily Loop
Step through 90 days:

```python
for day in range(1, 91):
    current_date = start_date + timedelta(days=day)
    for keyword in keywords:
        if should_evaluate(keyword, current_date):
            action = evaluate_keyword(keyword, current_date, dataset)
            if action:
                log_decision(action, current_date)
```

---

## Design Principles Verified

✓ **Simulator Independence:** Completely independent. No decisions feed back. 90-day run is ground truth.  
✓ **Campaign-Type Awareness:** Data structure and trajectories reflect type differences (Brand efficient, Generic volume, Discovery explored).  
✓ **Time-Lagged Data:** Data maturity tracked correctly (provisional/settled).  
✓ **Continuous Trajectories:** Each keyword has persistent baseline + drift + noise, creating meaningful trends for 7-day windows.  
✓ **No Magic Numbers:** All thresholds in config (CPA targets by tier, event durations, noise levels).  
✓ **Audit First:** Ready for decision engine to log every evaluation.  
✓ **Safe by Default:** Realistic budgets, conservative event injection (only ~0.1% of keyword-days).

---

**Status:** ✅ 90-day continuous simulator complete, verified, and ready for decision engine integration. Next: build campaign-type-aware decision logic and daily evaluation loop.
