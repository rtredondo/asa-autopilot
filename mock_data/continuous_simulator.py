"""90-day continuous simulator for ASA Autopilot with realistic performance trajectories.

Generates realistic data where each keyword has a persistent underlying performance
trajectory across 90 days: a slowly drifting baseline (random walk with mean-reversion)
plus daily noise. Events (competitor_spike, volume_surge, dying_keyword) are injected
at random points to create realistic patterns that exercise decision engine branches.

Critical design: Simulator is COMPLETELY INDEPENDENT from the decision engine.
Proposed actions NEVER feed back into simulated data. The 90-day run is pre-generated
ground truth that the decision engine will later observe.

Data maturity is relative: at any evaluation day, the most recent 2 days are provisional,
older days are settled.

Output: Raw daily rows (one per keyword per day), with primitives and daily derived
metrics. Decision engine computes trailing-7-day aggregations itself at evaluation time.
"""

import random
import json
import math
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from collections import defaultdict


# ===== Configuration =====

GEO_LIST = ["US", "UK", "CA", "AU", "IE", "NZ", "NL", "SE", "NO", "DK", "FI", "DE", "FR", "IN"]

GEO_TIER_MAP = {
    "US": "T1", "UK": "T1",
    "CA": "T2", "AU": "T2", "DE": "T2", "FR": "T2",
    "IE": "T3", "NZ": "T3", "NL": "T3",
    "SE": "T4", "NO": "T4", "DK": "T4", "FI": "T4", "IN": "T4",
}

CPA_TARGETS = {
    "T1": 1.60,
    "T2": 1.00,
    "T3": 0.85,
    "T4": 0.60,
}

CAMPAIGN_TYPES = ["brand", "competitor", "generic", "discovery"]

KEYWORD_POOL = [
    "equalization app", "eq audio", "equalizer pro", "bass boost",
    "sound equalizer", "music eq", "audio enhancement", "frequency equalizer",
    "graphic equalizer", "tone control", "audio mixer", "sound effects",
    "music volume booster", "speaker equalizer", "headphone eq", "car audio eq",
    "voice enhancer", "audio effects", "stereo equalizer", "treble boost",
    "best equalizer app", "equalizer music player", "professional audio eq",
    "eq studio", "sound tuner", "audio calibration", "loudness enhancer",
    "equalizer app download", "free equalizer", "premium audio app", "music studio",
    "audio processing", "frequency adjustment", "bass management", "treble control",
]

# Keyword count ranges (adjusted to land in 1,500-2,000 total)
KEYWORDS_PER_TYPE = {
    "brand": (5, 12),
    "competitor": (15, 35),
    "generic": (35, 55),
    "discovery": (35, 55),
}

# Events that inject variance across multiple days
EVENTS = ["competitor_spike", "volume_surge", "dying_keyword"]


@dataclass
class KeywordTrajectory:
    """Persistent baseline for a keyword across the 90 days."""
    keyword_id: str
    campaign_type: str
    tier: str
    target_cpa: float

    # Baseline parameters (set at start, evolve via random walk with mean-reversion)
    baseline_cpt: float  # Cost per tap baseline
    baseline_ttr: float  # Tap-through rate baseline
    baseline_cvr: float  # Conversion rate baseline
    baseline_imps: int   # Average impressions per day

    # Event tracking (if active, overrides baseline)
    active_event: str = None
    event_remaining_days: int = 0
    event_start_day: int = 0
    event_decline_duration: int = 0  # For dying_keyword: days to deteriorate

    # Discovery special types: None (normal), "winner" (improves over time), or "budget_dominant" (high spend)
    discovery_type: str = None
    winner_improvement_start_day: int = None  # When winners start improving toward target

    def get_daily_cpt(self, day: int) -> float:
        """Get CPT for this day (baseline + event modulation + noise)."""
        cpt = self.baseline_cpt

        # Competitor spike: CPT rises gradually during event
        if self.active_event == "competitor_spike":
            days_into_event = day - self.event_start_day
            surge_multiplier = 1.0 + (0.3 * (days_into_event / max(1, self.event_remaining_days)))
            cpt = cpt * surge_multiplier

        # Add daily noise
        noise = random.gauss(0, cpt * 0.1)  # 10% std dev noise
        return max(0.01, cpt + noise)

    def get_daily_ttr(self, day: int) -> float:
        """Get TTR for this day (baseline + event modulation + noise)."""
        ttr = self.baseline_ttr

        # Volume surge: TTR increases (more clicks per impression)
        if self.active_event == "volume_surge":
            surge_multiplier = 1.3  # 30% boost during surge
            ttr = ttr * surge_multiplier

        # NOTE: Dying keyword does NOT collapse TTR (taps/clicks continue)
        # It only collapses CVR (installs drop), so spend continues but installs vanish

        # Add daily noise
        noise = random.gauss(0, ttr * 0.15)  # 15% std dev noise
        return max(0.001, min(1.0, ttr + noise))

    def get_daily_cvr(self, day: int) -> float:
        """Get CVR for this day (baseline + event modulation + noise)."""
        cvr = self.baseline_cvr

        # Discovery winners: CVR improves over time, moving CPA from above target toward at/below target
        if self.discovery_type == "winner" and self.winner_improvement_start_day is not None:
            days_since_start = day - self.winner_improvement_start_day
            if days_since_start >= 0:
                # Winners start high CVR baseline but improve over ~45 days
                # (CVR improves = installs increase while spend stays similar = CPA decreases)
                # Improvement factor: 1.0 (start) → 1.8 (day 45, effectively better conversion)
                improvement_duration = 45
                if days_since_start < improvement_duration:
                    # Gradual improvement in CVR (higher installs for same spend = lower CPA)
                    improvement_factor = 1.0 + (0.8 * (days_since_start / improvement_duration))
                    cvr = cvr * improvement_factor
                else:
                    # After improvement period, stay at improved level
                    cvr = cvr * 1.8

        # Dying keyword: CVR gradually collapses over 4-8 days (catchable deterioration)
        # Spend continues (taps still happen), installs drop to near-zero, making CPA blow out
        if self.active_event == "dying_keyword":
            days_into_event = day - self.event_start_day

            # Set decline duration on first day of event (4-8 day deterioration period)
            if self.event_decline_duration == 0:
                self.event_decline_duration = random.randint(4, 8)

            decline_duration = self.event_decline_duration

            if days_into_event < decline_duration:
                # Gradual collapse: 100% → 2% over decline_duration (steeper collapse for catchability)
                decline_factor = 1.0 - (0.98 * (days_into_event / decline_duration))
                cvr = cvr * decline_factor
            else:
                # After decline period: stay at 2% (continued poor performance, wasted spend)
                # Use lower sustained CVR so spend + zero installs pattern is more visible
                cvr = cvr * 0.02

        # Add daily noise
        # For dying keyword, use smaller noise to keep pattern consistent
        if self.active_event == "dying_keyword" and (day - self.event_start_day) >= self.event_decline_duration:
            noise = random.gauss(0, max(cvr * 0.08, 0.0005))  # Lower noise during sustained phase
        else:
            noise = random.gauss(0, cvr * 0.12)  # 12% std dev noise for other phases

        return max(0.001, min(1.0, cvr + noise))

    def get_daily_impressions(self, day: int) -> int:
        """Get impressions for this day (baseline + event modulation + noise)."""
        imps = self.baseline_imps

        # Discovery budget-dominant: high impressions/spend to consume 15%+ of campaign
        # Multiply by ~5-8x normal Discovery volume to ensure high spend share
        if self.discovery_type == "budget_dominant":
            imps = int(imps * random.uniform(5.0, 8.0))

        # Volume surge: impressions increase significantly
        if self.active_event == "volume_surge":
            surge_multiplier = random.uniform(1.5, 2.5)  # 50-150% boost
            imps = int(imps * surge_multiplier)

        # Add daily noise (±20% of baseline)
        noise = int(random.gauss(0, imps * 0.2))
        return max(1, imps + noise)


def initialize_keyword_trajectory(
    keyword_id: str,
    campaign_type: str,
    tier: str,
    target_cpa: float,
    discovery_type: str = None,
) -> KeywordTrajectory:
    """Initialize baseline parameters for a keyword based on campaign type.

    Each type has a target CPA range. We generate CVR and TTR, then compute CPT
    to achieve the desired CPA (since CPA = CPT / CVR).

    For Discovery type="winner": starts above target but will improve over time.
    For Discovery type="budget_dominant": high baseline impressions for high spend share.
    """

    if campaign_type == "brand":
        # Brand: efficient, well below target (CPA = 0.70-0.90 * target)
        desired_cpa = target_cpa * random.uniform(0.70, 0.90)
        baseline_cvr = random.uniform(0.25, 0.40)
        baseline_cpt = desired_cpa * baseline_cvr  # CPT = CPA * CVR
        baseline_ttr = random.uniform(0.04, 0.10)
        baseline_imps = random.randint(300, 600)

    elif campaign_type == "competitor":
        # Competitor: near target (CPA = 0.95-1.30 * target)
        desired_cpa = target_cpa * random.uniform(0.95, 1.30)
        baseline_cvr = random.uniform(0.15, 0.30)
        baseline_cpt = desired_cpa * baseline_cvr
        baseline_ttr = random.uniform(0.05, 0.12)
        baseline_imps = random.randint(400, 900)

    elif campaign_type == "generic":
        # Generic: at target (CPA = 0.95-1.40 * target)
        desired_cpa = target_cpa * random.uniform(0.95, 1.40)
        baseline_cvr = random.uniform(0.12, 0.28)
        baseline_cpt = desired_cpa * baseline_cvr
        baseline_ttr = random.uniform(0.03, 0.10)
        baseline_imps = random.randint(600, 1500)

    else:  # discovery
        # Discovery: above target (CPA = 1.50-3.00 * target), noisy and explored
        # Winners and budget-dominant keywords will be adjusted after initialization
        desired_cpa = target_cpa * random.uniform(1.50, 3.00)
        baseline_cvr = random.uniform(0.05, 0.20)
        baseline_cpt = desired_cpa * baseline_cvr
        baseline_ttr = random.uniform(0.02, 0.08)
        baseline_imps = random.randint(200, 700)

    return KeywordTrajectory(
        keyword_id=keyword_id,
        campaign_type=campaign_type,
        tier=tier,
        target_cpa=target_cpa,
        baseline_cpt=baseline_cpt,
        baseline_ttr=baseline_ttr,
        baseline_cvr=baseline_cvr,
        baseline_imps=baseline_imps,
        discovery_type=discovery_type,
    )


def generate_90_day_dataset(start_date_str: str = "2026-08-15", num_days: int = 90) -> Dict[str, Any]:
    """Generate complete 90-day continuous dataset with realistic trajectories and events.

    Args:
        start_date_str: Start date (YYYY-MM-DD)
        num_days: Number of days to simulate (default 90)

    Returns:
        Dictionary with campaigns, keywords (daily rows), and metadata.
    """

    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = start_date + timedelta(days=num_days - 1)

    # Create campaigns and initialize keyword trajectories
    campaigns = {}  # campaign_id -> campaign dict
    trajectories = {}  # keyword_id -> KeywordTrajectory

    campaign_id = 1000
    for geo in sorted(GEO_LIST):
        tier = GEO_TIER_MAP[geo]
        target_cpa = CPA_TARGETS[tier]

        for campaign_type in CAMPAIGN_TYPES:
            campaign_name = f"EQLS_{geo}_{campaign_type.capitalize()}"

            campaign = {
                "id": str(campaign_id),
                "name": campaign_name,
                "campaign_type": campaign_type,
                "tier": tier,
                "target_cpa": target_cpa,
                "daily_budget": round(random.uniform(400, 800), 2),
                "exploration_budget": round(random.uniform(100, 300), 2) if campaign_type == "discovery" else None,
                "geo": geo,
            }
            campaigns[str(campaign_id)] = campaign

            # Generate keywords for this campaign
            kw_count = random.randint(*KEYWORDS_PER_TYPE[campaign_type])
            base_kw_id = campaign_id * 10000

            for i in range(kw_count):
                keyword_id = str(base_kw_id + i)
                trajectory = initialize_keyword_trajectory(
                    keyword_id=keyword_id,
                    campaign_type=campaign_type,
                    tier=tier,
                    target_cpa=target_cpa,
                )
                trajectories[keyword_id] = trajectory

            campaign_id += 1

    # ===== Inject special Discovery keywords =====
    # 5-10% of Discovery keywords should be winners that improve over time
    # A few per Discovery campaign should be budget-dominant (high spend share)
    discovery_trajectories = [
        (kw_id, traj) for kw_id, traj in trajectories.items()
        if traj.campaign_type == "discovery"
    ]

    # Identify winners: 5-10% of Discovery keywords, spread qualification across 90 days
    num_winners = max(1, int(len(discovery_trajectories) * random.uniform(0.05, 0.10)))
    winner_indices = random.sample(range(len(discovery_trajectories)), num_winners)

    for idx in winner_indices:
        kw_id, traj = discovery_trajectories[idx]
        traj.discovery_type = "winner"
        # Spread improvement start days across 10-50 so qualifications spread across later half of 90 days
        # A winner starting improvement on day 20 should qualify (~day 20 + 45 days improvement = day 65)
        traj.winner_improvement_start_day = random.randint(10, 50)

    # Identify budget-dominant keywords: 1-2 per Discovery campaign
    budget_dominant_count = 0
    discovery_by_campaign = defaultdict(list)
    for kw_id, traj in discovery_trajectories:
        campaign_id = str(int(kw_id) // 10000)
        discovery_by_campaign[campaign_id].append((kw_id, traj))

    for campaign_id, kw_list in discovery_by_campaign.items():
        if len(kw_list) >= 3:  # Only if campaign has enough keywords
            # Pick 1-2 random keywords as budget-dominant
            num_bd = random.randint(1, min(2, len(kw_list) // 10))  # 1-2 per campaign, or fewer if small campaign
            bd_indices = random.sample(range(len(kw_list)), num_bd)
            for idx in bd_indices:
                kw_id, traj = kw_list[idx]
                traj.discovery_type = "budget_dominant"
                budget_dominant_count += 1

    print(f"\nInjected Discovery variations:")
    print(f"  Winners (improve over time): {num_winners}")
    print(f"  Budget-dominant (high spend share): {budget_dominant_count}")

    # Generate daily data for all keywords across 90 days
    daily_rows = []

    for day_offset in range(num_days):
        current_date = start_date + timedelta(days=day_offset)
        date_str = current_date.strftime("%Y-%m-%d")

        # Data maturity: most recent 2 days are provisional, older days settled
        days_from_end = num_days - 1 - day_offset
        data_maturity = "provisional" if days_from_end < 2 else "settled"

        for keyword_id, trajectory in trajectories.items():
            # Randomly inject events for some keywords
            if trajectory.active_event is None and random.random() < 0.0015:  # ~0.15% chance per day per keyword
                # Bias event selection by campaign type
                campaign_type = trajectory.campaign_type
                if campaign_type == "discovery":
                    # Discovery: dying_keyword most likely (high exploration churn), also volume_surge
                    event = random.choices(EVENTS, weights=[0.15, 0.25, 0.60])[0]  # competitor_spike, volume_surge, dying_keyword
                elif campaign_type == "generic":
                    # Generic: all events possible, dying_keyword somewhat common
                    event = random.choices(EVENTS, weights=[0.25, 0.35, 0.40])[0]
                else:
                    # Brand/Competitor: competitor_spike most likely, dying_keyword rare
                    event = random.choices(EVENTS, weights=[0.50, 0.45, 0.05])[0]

                event_duration = {
                    "competitor_spike": random.randint(3, 7),
                    "volume_surge": random.randint(3, 10),
                    "dying_keyword": random.randint(10, 60),  # 10-60 days: show deterioration + sustained poor state
                }[event]
                trajectory.active_event = event
                trajectory.event_remaining_days = event_duration
                trajectory.event_start_day = day_offset

            # Decrement event countdown
            if trajectory.active_event is not None:
                trajectory.event_remaining_days -= 1
                if trajectory.event_remaining_days <= 0:
                    trajectory.active_event = None

            # Generate daily metrics
            cpt = trajectory.get_daily_cpt(day_offset)
            ttr = trajectory.get_daily_ttr(day_offset)
            cvr = trajectory.get_daily_cvr(day_offset)
            impressions = trajectory.get_daily_impressions(day_offset)

            # Calculate derived metrics
            taps = max(1, int(impressions * ttr))
            installs = max(0, int(taps * cvr))
            spend = round(taps * cpt, 2) if taps > 0 else 0

            # Recalculate precise metrics from derived counts
            precise_cpt = round(spend / taps, 4) if taps > 0 else 0
            precise_ttr = round(taps / impressions, 4) if impressions > 0 else 0
            precise_cvr = round(installs / taps, 4) if taps > 0 else 0
            precise_cpa = round(spend / installs, 2) if installs > 0 else None

            campaign_id = str(int(keyword_id) // 10000)
            campaign = campaigns[campaign_id]

            keyword_row = {
                "campaign_id": campaign_id,
                "campaign_name": campaign["name"],
                "campaign_type": trajectory.campaign_type,
                "keyword_id": keyword_id,
                "keyword_text": random.choice(KEYWORD_POOL),
                "date": date_str,
                "data_maturity": data_maturity,

                "impressions": impressions,
                "taps": taps,
                "installs": installs,
                "spend": spend,

                "cpt": precise_cpt,
                "ttr": precise_ttr,
                "cvr": precise_cvr,
                "cpa": precise_cpa,

                "tier": trajectory.tier,
                "target_cpa": trajectory.target_cpa,
                "bid_amount": round(random.uniform(0.20, 5.00), 2),
                "status": random.choice(["ENABLED", "ENABLED", "ENABLED", "PAUSED"]),
            }
            daily_rows.append(keyword_row)

    # Generate campaign-level daily aggregates
    campaign_daily_rows = []
    for day_offset in range(num_days):
        current_date = start_date + timedelta(days=day_offset)
        date_str = current_date.strftime("%Y-%m-%d")

        days_from_end = num_days - 1 - day_offset
        data_maturity = "provisional" if days_from_end < 2 else "settled"

        for campaign_id, campaign in campaigns.items():
            # Aggregate keywords for this campaign on this day
            campaign_keywords = [
                row for row in daily_rows
                if row["campaign_id"] == campaign_id and row["date"] == date_str
            ]

            if campaign_keywords:
                total_imps = sum(kw.get("impressions", 0) for kw in campaign_keywords)
                total_taps = sum(kw.get("taps", 0) for kw in campaign_keywords)
                total_installs = sum(kw.get("installs", 0) for kw in campaign_keywords)
                total_spend = sum(kw.get("spend", 0) for kw in campaign_keywords)

                campaign_cpa = round(total_spend / total_installs, 2) if total_installs > 0 else None

                campaign_row = {
                    "campaign_id": campaign_id,
                    "campaign_name": campaign["name"],
                    "campaign_type": campaign["campaign_type"],
                    "date": date_str,
                    "data_maturity": data_maturity,
                    "tier": campaign["tier"],
                    "target_cpa": campaign["target_cpa"],

                    "impressions": total_imps,
                    "taps": total_taps,
                    "installs": total_installs,
                    "spend": round(total_spend, 2),
                    "cpa": campaign_cpa,

                    "daily_budget": campaign["daily_budget"],
                    "exploration_budget": campaign["exploration_budget"],
                    "status": "ENABLED",
                }
                campaign_daily_rows.append(campaign_row)

    # Compute summary stats
    keyword_count = len(trajectories)
    campaign_count = len(campaigns)
    total_rows = len(daily_rows)

    return {
        "start_date": start_date_str,
        "end_date": end_date.strftime("%Y-%m-%d"),
        "num_days": num_days,
        "campaigns": list(campaigns.values()),
        "keywords": daily_rows,
        "campaign_dailies": campaign_daily_rows,
        "generated_at": datetime.utcnow().isoformat(),
        "stats": {
            "total_keywords": keyword_count,
            "total_campaigns": campaign_count,
            "total_daily_rows": total_rows,
            "date_range": f"{start_date_str} to {end_date.strftime('%Y-%m-%d')}",
        },
    }


def save_to_file(data: Dict[str, Any], filepath: str) -> None:
    """Save dataset to JSON file."""
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def load_from_file(filepath: str) -> Dict[str, Any]:
    """Load dataset from JSON file."""
    with open(filepath, "r") as f:
        return json.load(f)


def print_keyword_trajectory_samples(data: Dict[str, Any]) -> None:
    """Print sample keyword trajectories to show continuity and events."""
    print("\n" + "="*80)
    print("SAMPLE KEYWORD TRAJECTORIES (Daily CPA across 90 days)")
    print("="*80)

    # Find diverse sample keywords
    keywords_by_type = {}
    for kw_row in data["keywords"]:
        if kw_row["date"] == data["start_date"]:  # First day only for sampling
            ctype = kw_row["campaign_type"]
            if ctype not in keywords_by_type:
                keywords_by_type[ctype] = []
            keywords_by_type[ctype].append(kw_row["keyword_id"])

    # Pick one from Brand, one from Generic, one from Discovery
    sample_keyword_ids = {}
    for ctype in ["brand", "generic", "discovery"]:
        if keywords_by_type.get(ctype):
            sample_keyword_ids[ctype] = random.choice(keywords_by_type[ctype])

    # For each sample, print daily CPA across 90 days
    for ctype in ["brand", "generic", "discovery"]:
        if ctype not in sample_keyword_ids:
            continue

        kw_id = sample_keyword_ids[ctype]
        rows_for_keyword = [
            row for row in data["keywords"]
            if row["keyword_id"] == kw_id
        ]

        if rows_for_keyword:
            first_row = rows_for_keyword[0]
            print(f"\n{ctype.upper()} - {first_row['keyword_text']} (ID: {kw_id})")
            print(f"  Campaign: {first_row['campaign_name']}, Target CPA: £{first_row['target_cpa']:.2f}")
            print(f"  Daily CPA progression (£, null where installs=0):")
            print(f"  Day   1-10: ", end="")

            cpa_sequence = []
            for i, row in enumerate(rows_for_keyword):
                cpa = row["cpa"]
                cpa_str = f"{cpa:.2f}" if cpa is not None else "  null"
                cpa_sequence.append(cpa_str)

                if (i + 1) % 10 == 0:
                    print(" ".join(cpa_sequence[(i - 9):(i + 1)]))
                    if i + 1 < len(rows_for_keyword):
                        print(f"  Day {i+2:2d}-{min(i+11, len(rows_for_keyword)):2d}: ", end="")

            # Print remaining days
            if len(rows_for_keyword) % 10 != 0:
                remaining_start = (len(rows_for_keyword) // 10) * 10
                print(" ".join(cpa_sequence[remaining_start:]))


if __name__ == "__main__":
    filepath = "mock_data/continuous_90day.json"
    print("Generating 90-day continuous dataset with realistic trajectories...")
    data = generate_90_day_dataset()
    save_to_file(data, filepath)

    print("\n" + "="*80)
    print("90-DAY CONTINUOUS SIMULATOR - SUMMARY")
    print("="*80)
    print(f"\nDate Range: {data['start_date']} to {data['end_date']} ({data['num_days']} days)")
    print(f"\nCampaigns: {data['stats']['total_campaigns']}")
    print(f"Keywords: {data['stats']['total_keywords']}")
    print(f"Total Daily Rows: {data['stats']['total_daily_rows']:,}")

    # Verify keyword counts by type
    types_count = {}
    for camp in data["campaigns"]:
        ctype = camp["campaign_type"]
        types_count[ctype] = types_count.get(ctype, 0) + 1

    print(f"\nCampaigns by Type:")
    for ctype in ["brand", "competitor", "generic", "discovery"]:
        print(f"  {ctype:12s}: {types_count.get(ctype, 0):2d} campaigns")

    print(f"\nData Maturity (First and Last Day):")
    first_row = data["keywords"][0]
    last_row = data["keywords"][-1]
    print(f"  {first_row['date']}: {first_row['data_maturity']}")
    print(f"  {last_row['date']}: {last_row['data_maturity']}")

    # Print trajectory samples
    print_keyword_trajectory_samples(data)

    print(f"\n✅ Data saved to {filepath}")
    print(f"   File size: {len(json.dumps(data)) / (1024*1024):.1f} MB")
