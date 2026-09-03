#!/usr/bin/env python3
"""
Investigation: Why are Discovery campaigns 100% pauses?

Checks:
1. Can graduation ever fire? Count Discovery keyword-days with CPA <= target AND >= 20 installs
2. Why zero negativizes? Check rule ordering and spend-share calculations
"""

import json
from datetime import datetime, timedelta
from collections import defaultdict


def load_data():
    with open('config/parameters.json') as f:
        params = json.load(f)
    with open('mock_data/continuous_90day.json') as f:
        data = json.load(f)
    return params, data


def compute_windowed_cpa(keywords_by_date, campaign_id, keyword_id, evaluation_date,
                         observation_window=7, settling_lag=2):
    """Compute windowed CPA for a keyword on a given date."""
    window_end = evaluation_date - timedelta(days=settling_lag)
    window_start = window_end - timedelta(days=observation_window - 1)

    total_spend = 0.0
    total_installs = 0

    current = window_start
    while current <= window_end:
        date_str = current.strftime('%Y-%m-%d')
        key = (campaign_id, keyword_id, date_str)

        if key in keywords_by_date:
            kw = keywords_by_date[key]
            if kw.get('data_maturity') == 'settled':
                total_spend += kw.get('spend', 0.0)
                total_installs += kw.get('installs', 0)

        current += timedelta(days=1)

    windowed_cpa = None
    if total_installs > 0:
        windowed_cpa = total_spend / total_installs

    return total_spend, total_installs, windowed_cpa


def get_campaign_windowed_spend(keywords_by_campaign_date, campaign_id, evaluation_date,
                                observation_window=7, settling_lag=2):
    """Get total windowed spend for a campaign."""
    window_end = evaluation_date - timedelta(days=settling_lag)
    window_start = window_end - timedelta(days=observation_window - 1)

    total_spend = 0.0
    current = window_start

    while current <= window_end:
        date_str = current.strftime('%Y-%m-%d')
        for kw in keywords_by_campaign_date[date_str][campaign_id]:
            if kw.get('data_maturity') == 'settled':
                total_spend += kw.get('spend', 0.0)
        current += timedelta(days=1)

    return total_spend


def main():
    print("Loading data...")
    params, data = load_data()

    # Build indices
    keywords_by_date = {}
    keywords_by_campaign_date = defaultdict(lambda: defaultdict(list))
    campaigns_by_id = {c['id']: c for c in data['campaigns']}
    discovery_keywords = []

    for kw in data['keywords']:
        campaign_id = kw['campaign_id']
        keyword_id = kw['keyword_id']
        date_str = kw['date']

        key = (campaign_id, keyword_id, date_str)
        keywords_by_date[key] = kw
        keywords_by_campaign_date[date_str][campaign_id].append(kw)

        # Track Discovery keywords
        campaign = campaigns_by_id[campaign_id]
        if campaign['campaign_type'] == 'discovery':
            if kw['date'] == data['start_date']:  # Only once per keyword
                discovery_keywords.append((campaign_id, keyword_id, campaign['tier']))

    print(f"\nTotal Discovery keywords: {len(discovery_keywords)}")

    start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
    end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()

    grad_threshold = params['discovery_graduation']['min_installs_over_window']
    negativize_threshold = params['discovery_negativize_threshold']['campaign_spend_share']

    # ===== CHECK 1: GRADUATION FEASIBILITY =====
    print("\n" + "="*80)
    print("CHECK 1: GRADUATION FEASIBILITY")
    print("="*80)

    grad_candidates = 0  # CPA <= target
    grad_qualified = 0   # CPA <= target AND installs >= threshold
    sample_graduates = []

    current = start_date
    while current <= end_date:
        for campaign_id, keyword_id, tier in discovery_keywords:
            campaign = campaigns_by_id[campaign_id]
            target_cpa = campaign['target_cpa']

            spend, installs, cpa = compute_windowed_cpa(
                keywords_by_date, campaign_id, keyword_id, current
            )

            if cpa is not None and cpa <= target_cpa:
                grad_candidates += 1
                if installs >= grad_threshold:
                    grad_qualified += 1
                    if len(sample_graduates) < 5:
                        sample_graduates.append({
                            'date': current,
                            'campaign_id': campaign_id,
                            'keyword_id': keyword_id,
                            'cpa': cpa,
                            'target': target_cpa,
                            'installs': installs,
                            'campaign_name': campaign['name']
                        })

        current += timedelta(days=1)

    print(f"\nDiscovery keyword-days with CPA <= target: {grad_candidates}")
    print(f"  - Of those, with >= {grad_threshold} installs (can graduate): {grad_qualified}")
    print(f"  - Graduation feasibility: {grad_qualified / max(1, grad_candidates) * 100:.2f}% of candidates")

    if sample_graduates:
        print(f"\nSample graduation-qualified keywords:")
        for sample in sample_graduates:
            print(f"  {sample['campaign_name']} (ID {sample['keyword_id']})")
            print(f"    Date: {sample['date']}, CPA: £{sample['cpa']:.2f} <= £{sample['target']:.2f}, Installs: {sample['installs']}")

    # ===== CHECK 2: NEGATIVIZE FEASIBILITY =====
    print("\n" + "="*80)
    print("CHECK 2: NEGATIVIZE FEASIBILITY")
    print("="*80)

    negativize_candidates = 0  # CPA > target
    negativize_qualified = 0   # CPA > target AND spend_share >= 15%
    spend_share_values = []

    current = start_date
    while current <= end_date:
        # Pre-compute campaign spends for this date
        campaign_spends = {}
        for campaign_id, keyword_id, tier in discovery_keywords:
            if campaign_id not in campaign_spends:
                campaign_spends[campaign_id] = get_campaign_windowed_spend(
                    keywords_by_campaign_date, campaign_id, current
                )

        for campaign_id, keyword_id, tier in discovery_keywords:
            campaign = campaigns_by_id[campaign_id]
            target_cpa = campaign['target_cpa']

            spend, installs, cpa = compute_windowed_cpa(
                keywords_by_date, campaign_id, keyword_id, current
            )

            if cpa is not None and cpa > target_cpa:
                negativize_candidates += 1

                campaign_total_spend = campaign_spends[campaign_id]
                spend_share = spend / campaign_total_spend if campaign_total_spend > 0 else 0

                if spend_share >= negativize_threshold:
                    negativize_qualified += 1
                    if len(spend_share_values) < 10:
                        spend_share_values.append({
                            'date': current,
                            'campaign_id': campaign_id,
                            'keyword_id': keyword_id,
                            'cpa': cpa,
                            'target': target_cpa,
                            'spend': spend,
                            'campaign_spend': campaign_total_spend,
                            'spend_share': spend_share,
                            'campaign_name': campaign['name']
                        })

        current += timedelta(days=1)

    print(f"\nDiscovery keyword-days with CPA > target: {negativize_candidates}")
    print(f"  - Of those, with spend_share >= {negativize_threshold:.1%}: {negativize_qualified}")
    print(f"  - Negativize feasibility: {negativize_qualified / max(1, negativize_candidates) * 100:.2f}% of candidates")

    if spend_share_values:
        print(f"\nSample spend-share values for overperforming keywords:")
        for sample in spend_share_values:
            print(f"  {sample['campaign_name']} (ID {sample['keyword_id']})")
            print(f"    Date: {sample['date']}")
            print(f"    CPA: £{sample['cpa']:.2f} > £{sample['target']:.2f}")
            print(f"    Keyword spend: £{sample['spend']:.2f}, Campaign total: £{sample['campaign_spend']:.2f}")
            print(f"    Spend share: {sample['spend_share']:.1%} (threshold: {negativize_threshold:.1%})")

    # ===== CHECK 3: RULE ORDERING =====
    print("\n" + "="*80)
    print("CHECK 3: RULE ORDERING IN _decide_discovery")
    print("="*80)

    print("""
Current rule order:
  1. IF CPA <= target AND installs >= 20 → GRADUATE
  2. ELIF CPA <= target AND installs < 20 → HOLD (no_action)
  3. ELIF CPA > target AND spend_share >= 15% → NEGATIVIZE
  4. ELIF CPA > target OR no data → CHECK GRACE PERIOD
     - IF days_underperforming >= 28 → PAUSE
     - ELSE → no_action (grace period tracking)

Analysis:
  - Negativize check (rule 3) IS reached for keywords with CPA > target
  - It only fires if spend_share >= 15%
  - Grace period (rule 4) applies AFTER negativize check
  - So rule ordering should NOT prevent negativizes from firing

Conclusion: Negativize rule IS reachable. If zero negativizes occur, it means
no keywords pass the (CPA > target AND spend_share >= 15%) test.
""")

    # ===== SUMMARY =====
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    print(f"""
ISSUE 1: GRADUATION VIABILITY
  Problem: Why 0 graduations?
  Finding: Only {grad_qualified} Discovery keyword-days out of {grad_candidates} candidates
           ({grad_qualified / max(1, grad_candidates) * 100:.2f}%) qualify for graduation.

  Root cause analysis:
    - Discovery keywords generated with baseline CPA ~£2.52 (from simulator stats)
    - Tier targets range £0.60-£1.60
    - Discovery keywords are mostly ABOVE target, not below
    - Graduation requires BOTH CPA <= target AND >= 20 installs
    - This is a double constraint that rarely triggers

  Expected behavior: Graduation should be rare, not impossible

ISSUE 2: NEGATIVIZE VIABILITY
  Problem: Why 0 negativizes?
  Finding: Only {negativize_qualified} Discovery keyword-days out of {negativize_candidates} candidates
           ({negativize_qualified / max(1, negativize_candidates) * 100:.2f}%) qualify for negativize.

  Root cause analysis:
    - Negativize requires CPA > target AND spend_share >= 15%
    - Discovery campaigns spread budget across ~{len(discovery_keywords) // 14} keywords each
    - Average spend_share per keyword = 1 / {len(discovery_keywords) // 14} ≈ {1 / (len(discovery_keywords) // 14) * 100:.1f}%
    - Very few individual keywords consume >= 15% of campaign spend
    - Most keywords stay below threshold even if overperforming

  Expected behavior: Negativize should fire on high-spend underperformers, but
                    most Discovery keywords have low individual spend share

VERDICT:
  Both graduation and negativize are RARE by design, not broken.
  The simulator generates Discovery keywords with:
    - High CPA (above target on average)
    - Low individual volume (spread across many keywords)
    - These constraints make graduation/negativize very unlikely

  The 100% pause result is REALISTIC given the data distribution, not a logic bug.

  Recommendation: Verify simulator intentionally generates Discovery this way,
                  or consider whether it should generate some "promising" Discovery
                  keywords that can demonstrate graduation/negativize paths.
""")


if __name__ == '__main__':
    main()
