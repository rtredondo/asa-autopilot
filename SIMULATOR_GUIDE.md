# Campaign-Type-Aware Simulator: Quick Start Guide

This guide shows how to generate and use the new campaign-type-aware synthetic data.

---

## Quick Start

### Generate One Day of Data

```bash
cd /Users/rredondo/asa-autopilot
python3 -m mock_data.campaign_simulator
```

**Output:**
- Generates `mock_data/campaign_data.json` with 2,185 keywords across 56 campaigns
- Prints detailed summary: campaign counts by type, sample keywords, aggregate performance
- Date: 3 days old (settled data, safe for decisions)

---

## What Gets Generated

**One complete day at full scale:**
- 56 campaigns: 4 types (Brand, Competitor, Generic, Discovery) × 14 storefronts
- ~2,185 keywords (target 1,500–2,000)
- Full data: impressions, taps, installs, spend → derived CPA, CPT, TTR, CVR
- Data marked `"data_maturity": "settled"` (3+ days old, ready for decisions)

**By campaign type:**
- **Brand:** ~11 keywords/campaign, CPA £0.89 (efficient, stable)
- **Competitor:** ~30 keywords/campaign, CPA £1.35 (near target, volatile)
- **Generic:** ~56 keywords/campaign, CPA £1.33 (workhorse, moderate variance)
- **Discovery:** ~57 keywords/campaign, CPA £3.06 (noisy, explored, not optimized)

---

## Data Model

### Keyword Row

```json
{
  "campaign_id": "1000",
  "campaign_name": "EQLS_US_Brand",
  "campaign_type": "brand",          // ← Type for decision branching
  "keyword_id": "10000000",
  "keyword_text": "equalizer app",
  "date": "2026-08-15",
  "data_maturity": "settled",        // ← Data ready for decisions
  
  "impressions": 754,
  "taps": 41,
  "installs": 10,
  "spend": 7.50,
  
  "cpt": 0.1829,                     // Cost per tap
  "ttr": 0.0544,                     // Tap-through rate
  "cvr": 0.2439,                     // Conversion rate (tap to install)
  "cpa": 0.75,                       // Cost per action (null if installs=0)
  
  "tier": "T1",
  "target_cpa": 1.60,
  "bid_amount": 0.91,
  "status": "ENABLED"
}
```

### Campaign Row

```json
{
  "id": "1000",
  "name": "EQLS_US_Brand",
  "campaign_type": "brand",
  "daily_budget": 500.00,            // Non-binding, generous
  "exploration_budget": null,        // Set only for Discovery type
  "tier": "T1",
  "target_cpa": 1.60,
  
  "performance": {
    "impressions": 6559,             // Aggregated from keywords
    "taps": 414,
    "installs": 120,
    "spend": 110.51,
    "cpa": 0.92
  }
}
```

### Key Fields for Decision Engine

- **`campaign_type`:** Determines logic branch (Brand/Competitor/Generic get CPA optimization; Discovery is budget-constrained)
- **`data_maturity`:** Current implementation uses "settled"; future: implement gating so only settled data triggers decisions
- **`exploration_budget`:** Discovery campaigns only; represents capped "spend to learn" allowance
- **`cpa`:** `null` when `installs=0` (no division by zero)

---

## Geo Tiers & CPA Targets

```
Tier  Storefronts              Target CPA
─────────────────────────────────────────
T1    US, UK                   £1.60/install
T2    CA, AU, DE, FR           £1.00/install
T3    IE, NZ, NL, SE, NO, DK, FI  £0.85/install
T4    IN                       £0.60/install
```

Every keyword inherits its tier and target from its campaign's geography.

---

## Integration: Decision Engine

### Current Behavior (Decision Engine)
The existing `decision_engine/__init__.py` evaluates keywords without campaign-type awareness. It works on the new data, but doesn't distinguish types.

### Next Phase
Modify decision logic to branch on `campaign_type`:

```python
if keyword["campaign_type"] == "discovery":
    # Budget-constrained exploration
    # Prune by volume/churn, NOT by CPA
    # Respect exploration_budget cap
else:
    # Brand/Competitor/Generic: Full CPA optimization
    # Evaluate bid changes, pauses, budget shifts
    # Judge against target_cpa
```

---

## Loading Data Programmatically

### In Python

```python
from mock_data.campaign_simulator import load_from_file

data = load_from_file("mock_data/campaign_data.json")

# Access campaigns and keywords
campaigns = data["campaigns"]
keywords = data["keywords"]

# Filter by type
brand_keywords = [kw for kw in keywords if kw["campaign_type"] == "brand"]

# Get stats
print(f"Total keywords: {data['stats']['total_keywords']}")
print(f"Keywords by type: {data['stats']['keywords_by_type']}")
```

### In Streamlit Dashboard
The dashboard can be updated to load the new data structure and branch decision logic by campaign type:

```python
data = load_from_file("mock_data/campaign_data.json")

for keyword in data["keywords"]:
    if keyword["data_maturity"] == "settled":  # Only settled data
        if keyword["campaign_type"] == "discovery":
            # Discovery: budget-aware, not CPA-optimized
            evaluate_discovery_keyword(keyword)
        else:
            # Brand/Competitor/Generic: CPA-optimized
            evaluate_standard_keyword(keyword)
```

---

## 90-Day Loop (Next Phase)

Currently, the simulator generates **one day** of data. To build a 90-day loop:

1. **Extend generator:** Create multiple days with time progression
   - Each keyword has one row per day
   - `date` field increments daily
   - `data_maturity` transitions: provisional (days 0–1) → settled (day 3+)

2. **Simulator loop:**
   ```
   for day in range(1, 91):
       data = generate_one_day()        # One day's keywords
       evaluate_decisions(data)          # Run decision engine
       record_verdict(data)              # Log to state store
       output_metrics(data)              # Track CPA trends
   ```

3. **Historical tracking:**
   - State store already captures decision history
   - Next: capture performance history (CPA trends over 90 days)
   - Enable analysis: "How many keywords dropped CPA after a bid increase?"

---

## File Structure

```
mock_data/
├── __init__.py                      # Package marker
├── campaign_simulator.py            # ← Main simulator (NEW)
├── campaign_data.json               # ← Generated one-day data (NEW)
├── generator.py                     # Old generator (pre-campaign-types)
└── synthetic_data.json              # Old generated data
```

**Note:** The old `generator.py` and `synthetic_data.json` are still present for reference. The new `campaign_simulator.py` is the production version.

---

## Performance Characteristics (Verified)

### Brand Campaigns (Stable, Efficient)
```
Aggregate CPA: £0.89 (vs. T2 target £1.00)
Margin: -11% below target ✓
Bid Action: INCREASE (capitalize on efficiency)
```

### Competitor Campaigns (Near Target, Volatile)
```
Aggregate CPA: £1.35 (vs. T2 target £1.00)
Margin: +35% above target
Bid Action: DECREASE (control cost)
Variance: Higher (40% below target, sometimes 30% above)
```

### Generic Campaigns (Workhorse, Moderate Variance)
```
Aggregate CPA: £1.33 (vs. T2 target £1.00)
Margin: +33% above target
Bid Action: DECREASE (pull to target)
Volume: Highest (942K impressions across 14 campaigns)
```

### Discovery Campaigns (Noisy, Exploration)
```
Aggregate CPA: £3.06 (vs. T2 target £1.00)
Margin: +206% above target
Bid Action: NONE (not CPA-judged; budget-constrained instead)
Churn: High (65% of keywords have zero installs)
Rationale: Search Match / broad-match exploration; poor history by design
```

---

## Testing the New Data

### Verify Structure

```bash
python3 -c "
import json
with open('mock_data/campaign_data.json', 'r') as f:
    data = json.load(f)
    
# Check campaign types
for ctype in ['brand', 'competitor', 'generic', 'discovery']:
    count = sum(1 for c in data['campaigns'] if c['campaign_type'] == ctype)
    print(f'{ctype}: {count} campaigns')

# Verify data maturity
maturities = set(kw['data_maturity'] for kw in data['keywords'])
print(f'Data maturities: {maturities}')

# Verify exploration_budget
discovery_with_budget = sum(1 for c in data['campaigns'] 
                            if c['campaign_type'] == 'discovery' 
                            and c['exploration_budget'] is not None)
print(f'Discovery campaigns with exploration_budget: {discovery_with_budget}')
"
```

### Verify Performance by Type

```bash
python3 -c "
import json
with open('mock_data/campaign_data.json', 'r') as f:
    data = json.load(f)

for ctype in ['brand', 'competitor', 'generic', 'discovery']:
    campaigns = [c for c in data['campaigns'] if c['campaign_type'] == ctype]
    total_spend = sum(c['performance']['spend'] for c in campaigns)
    total_installs = sum(c['performance']['installs'] for c in campaigns)
    cpa = total_spend / total_installs if total_installs else 0
    print(f'{ctype:12s}: {len(campaigns)} campaigns, CPA £{cpa:.2f}')
"
```

---

## Next Steps

1. **Inspect the generated data:**
   ```bash
   python3 -m mock_data.campaign_simulator
   ```

2. **Load into decision engine:**
   - Modify `decision_engine/__init__.py` to branch on `campaign_type`
   - Add data_maturity gating (only evaluate "settled" data)

3. **Extend to 90-day loop:**
   - Generate multiple days with time progression
   - Track CPA trends, guardrail blocks, action execution rates

4. **Run simulations:**
   - Execute 90-day loop
   - Observe decision behavior by type
   - Tune bid change % and guardrail thresholds

---

**Status:** One day of campaign-type-aware data is generated and verified. Ready to extend to multi-day simulations and campaign-type-aware decision logic.
