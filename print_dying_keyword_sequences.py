"""Find and print keywords that experienced dying_keyword events with CPA and spend sequences."""
import json
from collections import defaultdict

def load_data(filepath: str):
    with open(filepath, "r") as f:
        return json.load(f)

def find_keywords_with_dying_pattern(data):
    """Find keywords that show dying_keyword pattern: CVR collapses then sustains low."""
    keywords_by_id = defaultdict(list)

    for row in data["keywords"]:
        keywords_by_id[row["keyword_id"]].append(row)

    candidates = []

    for kw_id, rows in keywords_by_id.items():
        rows.sort(key=lambda r: r["date"])

        # Look for: CVR drops from > 0.10 to near-zero, stays low, spend continues
        for i in range(10, len(rows)-15):
            # Check if CVR drops significantly at position i
            before_cvrs = [r["cvr"] for r in rows[max(0, i-5):i] if r["cvr"] > 0]
            at_and_after = rows[i:i+12]

            if not before_cvrs:
                continue

            avg_before = sum(before_cvrs) / len(before_cvrs)

            # Look for: CVR collapses to near-zero AND most of the next 12 days have CVR < 0.05
            # AND spend continues during this period
            if avg_before > 0.10:
                zero_or_low_days = sum(1 for r in at_and_after if r["cvr"] < 0.05)
                avg_spend = sum(r["spend"] for r in at_and_after) / len(at_and_after)
                zero_install_days = sum(1 for r in at_and_after if r["installs"] == 0)

                # Pattern: most days after collapse have low CVR, spend continues, some zero-install days
                if (zero_or_low_days >= 8 and avg_spend > 10 and zero_install_days >= 3):
                    candidates.append({
                        "keyword_id": kw_id,
                        "keyword_text": rows[0]["keyword_text"],
                        "campaign_name": rows[0]["campaign_name"],
                        "campaign_type": rows[0]["campaign_type"],
                        "target_cpa": rows[0]["target_cpa"],
                        "event_start_day": i,
                        "rows": rows
                    })
                    break  # Only count first event per keyword

    return candidates

if __name__ == "__main__":
    filepath = "mock_data/continuous_90day.json"
    print("Loading data...")
    data = load_data(filepath)

    print("Finding keywords with dying_keyword patterns...")
    candidates = find_keywords_with_dying_pattern(data)

    print(f"\nFound {len(candidates)} keywords with dying_keyword patterns")

    # Group by campaign type
    by_type = defaultdict(list)
    for c in candidates:
        by_type[c["campaign_type"]].append(c)

    print("\nDistribution by campaign type:")
    for ctype in ["brand", "competitor", "generic", "discovery"]:
        count = len(by_type.get(ctype, []))
        print(f"  {ctype:12s}: {count:3d} keywords")

    # Pick one from Generic or Discovery
    target_keyword = None
    for ctype in ["generic", "discovery"]:
        if by_type[ctype]:
            target_keyword = by_type[ctype][0]
            break

    if not target_keyword and candidates:
        target_keyword = candidates[0]

    if target_keyword:
        print("\n" + "=" * 110)
        print("DYING_KEYWORD EVENT - FULL SEQUENCE WITH DAILY CPA AND SPEND")
        print("=" * 110)
        print(f"\nKeyword: {target_keyword['keyword_text']}")
        print(f"Campaign: {target_keyword['campaign_name']} ({target_keyword['campaign_type'].upper()})")
        print(f"Target CPA: £{target_keyword['target_cpa']:.2f}")
        print(f"Keyword ID: {target_keyword['keyword_id']}\n")

        print(f"{'Day':<4} {'Date':<12} {'Imps':>6} {'Taps':>5} {'Installs':>9} {'Spend':>7} {'CVR':>8} {'CPA':>8}")
        print("-" * 110)

        rows = target_keyword['rows']
        for i, row in enumerate(rows, 1):
            cvr_str = f"{row['cvr']:.4f}"
            cpa_str = f"£{row['cpa']:.2f}" if row['cpa'] is not None else "   null"
            print(f"{i:<4} {row['date']:<12} {row['impressions']:>6} {row['taps']:>5} {row['installs']:>9} £{row['spend']:>6.2f} {cvr_str:>8} {cpa_str:>8}")

        # Analysis
        print("\n" + "=" * 110)
        print("EVENT PATTERN ANALYSIS")
        print("=" * 110)

        # Find collapse point
        for i in range(len(rows)-20):
            before = sum(1 for r in rows[max(0,i-5):i] if r["cvr"] > 0.10)
            at_and_after = rows[i:i+12]
            low_cvr_count = sum(1 for r in at_and_after if r["cvr"] < 0.05)

            if before >= 3 and low_cvr_count >= 8:
                print(f"\nEvent detected starting around day {i+1} ({rows[i]['date']})")
                baseline_cvrs = [f"{r['cvr']:.4f}" for r in rows[max(0,i-5):i]]
                print(f"  - Pre-event baseline CVR (days {i-4} to {i}): {baseline_cvrs}")
                print(f"  - Event begins: day {i+1} CVR {rows[i]['cvr']:.4f}")

                # Find sustained period
                sustained_start = i
                sustained_end = len(rows)
                for j in range(i+15, len(rows)):
                    if rows[j]["cvr"] > 0.08:  # Recovery threshold
                        sustained_end = j
                        break

                sustained_period = sustained_end - sustained_start
                print(f"\n  Sustained poor state (CVR < 5%): Days {sustained_start+1} to {sustained_end} ({sustained_period} days)")

                # Detailed stats
                poor_rows = rows[sustained_start:sustained_end]
                total_spend = sum(r['spend'] for r in poor_rows)
                total_installs = sum(r['installs'] for r in poor_rows)
                zero_spend_days = len([r for r in poor_rows if r['spend'] == 0])
                zero_install_days = len([r for r in poor_rows if r['installs'] == 0])
                spend_zero_install = len([r for r in poor_rows if r['spend'] > 0 and r['installs'] == 0])

                print(f"\n  Performance during sustained poor state:")
                print(f"    - Total spend: £{total_spend:.2f} (avg £{total_spend/len(poor_rows):.2f}/day)")
                print(f"    - Total installs: {total_installs} (avg {total_installs/len(poor_rows):.2f}/day)")
                print(f"    - Days with zero spend: {zero_spend_days}")
                print(f"    - Days with zero installs: {zero_install_days}")
                print(f"    - Days with spend > £0 but installs = 0: {spend_zero_install} *** KEY PATTERN FOR DECISION ENGINE ***")

                if total_installs > 0:
                    blowout_cpa = total_spend / total_installs
                    print(f"    - CPA during period: £{blowout_cpa:.2f} (vs target £{rows[0]['target_cpa']:.2f})")

                print(f"\n  Recovery: Day {sustained_end+1} onwards shows CVR {rows[sustained_end]['cvr']:.4f}")
                break
    else:
        print("\nNo keywords with dying_keyword patterns found")
