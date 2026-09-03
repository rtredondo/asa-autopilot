"""Analyze keywords that experience dying_keyword events to verify behavior."""
import json
from collections import defaultdict

def load_data(filepath: str):
    with open(filepath, "r") as f:
        return json.load(f)

def find_dying_keyword_events(data):
    """Find keywords that likely experienced dying_keyword events by looking for:
    - Sustained period of high CPA or null CPA values
    - Evidence of spend continuing despite low/zero installs
    """
    keywords_by_id = defaultdict(list)

    # Group rows by keyword
    for row in data["keywords"]:
        keywords_by_id[row["keyword_id"]].append(row)

    # Find keywords with potential dying_keyword patterns
    dying_keywords = []

    for kw_id, rows in keywords_by_id.items():
        rows.sort(key=lambda r: r["date"])

        # Look for consecutive high CPA (>= 2x target) or null CPA values
        consecutive_high_or_null = 0
        high_or_null_window = []

        for i, row in enumerate(rows):
            target = row["target_cpa"]
            cpa = row["cpa"]
            is_high_or_null = (cpa is None) or (cpa >= target * 2)

            if is_high_or_null:
                consecutive_high_or_null += 1
                high_or_null_window.append((i, row))
            else:
                if consecutive_high_or_null >= 5:  # At least 5 days of high/null CPA
                    dying_keywords.append({
                        "keyword_id": kw_id,
                        "keyword_text": rows[0]["keyword_text"],
                        "campaign_name": rows[0]["campaign_name"],
                        "campaign_type": rows[0]["campaign_type"],
                        "target_cpa": target,
                        "event_window": high_or_null_window[:]
                    })
                consecutive_high_or_null = 0
                high_or_null_window = []

        # Check if the high/null period extends to the end
        if consecutive_high_or_null >= 5:
            dying_keywords.append({
                "keyword_id": kw_id,
                "keyword_text": rows[0]["keyword_text"],
                "campaign_name": rows[0]["campaign_name"],
                "campaign_type": rows[0]["campaign_type"],
                "target_cpa": target,
                "event_window": high_or_null_window[:]
            })

    return dying_keywords

if __name__ == "__main__":
    filepath = "mock_data/continuous_90day.json"
    print("Loading data...")
    data = load_data(filepath)

    print("Finding dying_keyword events...")
    dying_keywords = find_dying_keyword_events(data)

    print(f"\nFound {len(dying_keywords)} keywords with likely dying_keyword patterns")
    print("=" * 80)

    # Group by campaign type
    by_type = defaultdict(list)
    for dk in dying_keywords:
        by_type[dk["campaign_type"]].append(dk)

    for ctype in ["brand", "competitor", "generic", "discovery"]:
        if ctype in by_type:
            print(f"\n{ctype.upper()}: {len(by_type[ctype])} keywords")
            for dk in by_type[ctype][:3]:  # Show first 3 of each type
                print(f"  - {dk['keyword_text']} ({dk['campaign_name']}, target £{dk['target_cpa']:.2f})")

    # Pick one keyword from Discovery or Generic for detailed analysis
    target_keyword = None
    for dk in dying_keywords:
        if dk["campaign_type"] in ["discovery", "generic"]:
            target_keyword = dk
            break

    if target_keyword:
        print("\n" + "=" * 80)
        print("DETAILED ANALYSIS OF DYING_KEYWORD EVENT")
        print("=" * 80)
        print(f"\n{target_keyword['campaign_type'].upper()} - {target_keyword['keyword_text']}")
        print(f"Campaign: {target_keyword['campaign_name']}")
        print(f"Target CPA: £{target_keyword['target_cpa']:.2f}")
        print(f"Keyword ID: {target_keyword['keyword_id']}")

        # Get all rows for this keyword
        kw_rows = [r for r in data["keywords"] if r["keyword_id"] == target_keyword["keyword_id"]]
        kw_rows.sort(key=lambda r: r["date"])

        print(f"\nDaily Sequence (focusing on event window):")
        print(f"{'Day':<4} {'Date':<12} {'Imps':>6} {'Taps':>5} {'Installs':>8} {'Spend':>7} {'CPA':>8} {'CVR':>6}")
        print("-" * 75)

        for i, row in enumerate(kw_rows, 1):
            cpa_str = f"£{row['cpa']:.2f}" if row['cpa'] is not None else "   null"
            cvr_str = f"{row['cvr']:.4f}" if row['cvr'] > 0 else "  0.00"
            print(f"{i:<4} {row['date']:<12} {row['impressions']:>6} {row['taps']:>5} {row['installs']:>8} £{row['spend']:>6.2f} {cpa_str:>8} {cvr_str:>6}")
