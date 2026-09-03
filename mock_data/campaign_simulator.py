"""Campaign-type-aware synthetic data generator for ASA Autopilot.

Generates realistic Apple Search Ads data with explicit campaign types (Brand,
Competitor, Generic, Discovery). Each campaign type has distinct performance
characteristics:

- Brand: Few keywords (~5–15), low volume, high CVR, CPA << target
- Competitor: Moderate keywords (~20–40), CPA near target, higher volatility
- Generic: High keywords (~40–70), highest volume, CPA ~ target
- Discovery: High keywords (~40–70), noisy/low history, NOT judged on CPA

Data includes campaign_type and data_maturity on every keyword row. Discovery
campaigns include exploration_budget (capped spend-to-learn). Generates one
day of complete data, ready for inspection before 90-day loop.
"""

import random
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass


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

# Keywords for mock data
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


@dataclass
class CampaignTypeConfig:
    """Configuration for each campaign type."""
    name: str
    keywords_min: int
    keywords_max: int
    impressions_min: int
    impressions_max: int
    high_performer_weight: float
    meeting_target_weight: float
    below_target_weight: float
    low_volume_weight: float
    wasted_spend_weight: float


# Campaign type configurations: keywords per campaign and performance distribution
CAMPAIGN_TYPE_CONFIGS = {
    "brand": CampaignTypeConfig(
        name="brand",
        keywords_min=5, keywords_max=12,
        impressions_min=100, impressions_max=800,
        high_performer_weight=0.60,
        meeting_target_weight=0.35,
        below_target_weight=0.03,
        low_volume_weight=0.01,
        wasted_spend_weight=0.01,
    ),
    "competitor": CampaignTypeConfig(
        name="competitor",
        keywords_min=15, keywords_max=35,
        impressions_min=150, impressions_max=1500,
        high_performer_weight=0.15,
        meeting_target_weight=0.35,
        below_target_weight=0.40,
        low_volume_weight=0.05,
        wasted_spend_weight=0.05,
    ),
    "generic": CampaignTypeConfig(
        name="generic",
        keywords_min=35, keywords_max=55,
        impressions_min=200, impressions_max=2500,
        high_performer_weight=0.10,
        meeting_target_weight=0.30,
        below_target_weight=0.45,
        low_volume_weight=0.10,
        wasted_spend_weight=0.05,
    ),
    "discovery": CampaignTypeConfig(
        name="discovery",
        keywords_min=35, keywords_max=55,
        impressions_min=100, impressions_max=1200,
        high_performer_weight=0.05,
        meeting_target_weight=0.10,
        below_target_weight=0.50,
        low_volume_weight=0.20,
        wasted_spend_weight=0.15,
    ),
}


def generate_campaign_name(geo: str, campaign_type: str) -> str:
    """Generate campaign name in new format: EQLS_{GEO}_{Type}"""
    type_formatted = campaign_type.capitalize() if campaign_type != "discovery" else "Discovery"
    return f"EQLS_{geo}_{type_formatted}"


def generate_campaigns() -> List[Dict[str, Any]]:
    """Generate 56 campaigns: 4 types × 14 geos.

    Returns campaigns with performance aggregates (calculated from keywords later).
    """
    campaigns = []
    campaign_id = 1000

    for geo in sorted(GEO_LIST):
        for campaign_type in CAMPAIGN_TYPES:
            campaign_name = generate_campaign_name(geo, campaign_type)
            tier = GEO_TIER_MAP[geo]
            target_cpa = CPA_TARGETS[tier]

            campaign = {
                "id": str(campaign_id),
                "name": campaign_name,
                "campaign_type": campaign_type,
                "status": random.choice(["ENABLED", "ENABLED", "ENABLED", "PAUSED"]),
                "daily_budget": round(random.uniform(400, 800), 2),
                "exploration_budget": round(random.uniform(100, 300), 2) if campaign_type == "discovery" else None,
                "tier": tier,
                "target_cpa": target_cpa,
                "geo": geo,
                "org_id": 1,
                "modification_time": datetime.utcnow().isoformat(),
                # Performance will be computed from keywords
                "performance": {
                    "impressions": 0,
                    "taps": 0,
                    "installs": 0,
                    "spend": 0.0,
                    "cpa": None,
                },
            }
            campaigns.append(campaign)
            campaign_id += 1

    return campaigns


def choose_performance_profile(config: CampaignTypeConfig) -> str:
    """Choose performance profile based on campaign type distribution."""
    profiles = ["high_performer", "meeting_target", "below_target", "low_volume", "wasted_spend"]
    weights = [
        config.high_performer_weight,
        config.meeting_target_weight,
        config.below_target_weight,
        config.low_volume_weight,
        config.wasted_spend_weight,
    ]
    return random.choices(profiles, weights=weights, k=1)[0]


def generate_keyword_performance(
    profile: str,
    config: CampaignTypeConfig,
    target_cpa: float,
) -> Tuple[int, int, int, float]:
    """Generate impressions, taps, installs, spend for a keyword based on profile."""

    if profile == "high_performer":
        impressions = random.randint(config.impressions_min, config.impressions_max)
        cpa_variance = random.uniform(0.70, 0.95)
        taps = max(1, int(impressions * random.uniform(0.03, 0.10)))
        installs = max(1, int(taps * random.uniform(0.20, 0.50)))
    elif profile == "meeting_target":
        impressions = random.randint(config.impressions_min, config.impressions_max)
        cpa_variance = random.uniform(0.95, 1.10)
        taps = max(1, int(impressions * random.uniform(0.02, 0.08)))
        installs = max(1, int(taps * random.uniform(0.15, 0.45)))
    elif profile == "below_target":
        impressions = random.randint(config.impressions_min, config.impressions_max)
        cpa_variance = random.uniform(1.10, 1.40)
        taps = max(1, int(impressions * random.uniform(0.02, 0.08)))
        installs = max(1, int(taps * random.uniform(0.10, 0.35)))
    elif profile == "low_volume":
        impressions = random.randint(max(10, config.impressions_min // 5), config.impressions_min)
        cpa_variance = random.uniform(0.50, 1.50)
        taps = max(1, int(impressions * random.uniform(0.01, 0.05)))
        installs = max(0, int(taps * random.uniform(0.05, 0.25)))
    else:  # wasted_spend: impressions but no installs
        impressions = random.randint(config.impressions_min // 2, config.impressions_max // 3)
        cpa_variance = random.uniform(0.8, 1.5)
        taps = max(1, int(impressions * random.uniform(0.02, 0.08)))
        installs = 0

    actual_cpa = round(target_cpa * cpa_variance, 2)
    spend = round(installs * actual_cpa, 2) if installs > 0 else round(random.uniform(5, 50), 2)

    return impressions, taps, installs, spend


def generate_keywords_for_campaign(
    campaign_id: str,
    campaign_name: str,
    campaign_type: str,
    geo: str,
    tier: str,
    target_cpa: float,
    date: str,
    data_maturity: str,
) -> List[Dict[str, Any]]:
    """Generate keywords for a single campaign with type-specific characteristics."""

    config = CAMPAIGN_TYPE_CONFIGS[campaign_type]
    keyword_count = random.randint(config.keywords_min, config.keywords_max)

    keywords = []
    base_keyword_id = int(campaign_id) * 10000

    for i in range(keyword_count):
        keyword_text = random.choice(KEYWORD_POOL)
        keyword_id = str(base_keyword_id + i)

        profile = choose_performance_profile(config)
        impressions, taps, installs, spend = generate_keyword_performance(profile, config, target_cpa)

        # Calculate derived metrics
        cpt = round(spend / taps, 4) if taps > 0 else 0
        ttr = round(taps / impressions, 4) if impressions > 0 else 0
        cvr = round(installs / taps, 4) if taps > 0 else 0
        cpa = round(spend / installs, 2) if installs > 0 else None

        keyword = {
            "campaign_id": campaign_id,
            "campaign_name": campaign_name,
            "campaign_type": campaign_type,
            "keyword_id": keyword_id,
            "keyword_text": keyword_text,
            "date": date,
            "data_maturity": data_maturity,

            # Primitives
            "impressions": impressions,
            "taps": taps,
            "installs": installs,
            "spend": round(spend, 2),

            # Derived metrics
            "cpt": cpt,
            "ttr": ttr,
            "cvr": cvr,
            "cpa": cpa,

            # Target and tier info
            "tier": tier,
            "target_cpa": target_cpa,

            # Bid and status
            "bid_amount": round(random.uniform(0.20, 5.00), 2),
            "status": random.choice(["ENABLED", "ENABLED", "ENABLED", "PAUSED"]),
        }
        keywords.append(keyword)

    return keywords


def generate_one_day_dataset() -> Dict[str, Any]:
    """Generate complete one-day dataset with campaigns and keywords."""

    # Use yesterday's date as settled data
    date = (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d")
    data_maturity = "settled"  # Data from 3 days ago is fully settled

    campaigns = generate_campaigns()
    all_keywords = []
    campaign_keyword_map = {}

    # Generate keywords for each campaign
    for campaign in campaigns:
        campaign_type = campaign["campaign_type"]
        geo = campaign["geo"]
        tier = campaign["tier"]
        target_cpa = campaign["target_cpa"]

        keywords = generate_keywords_for_campaign(
            campaign_id=campaign["id"],
            campaign_name=campaign["name"],
            campaign_type=campaign_type,
            geo=geo,
            tier=tier,
            target_cpa=target_cpa,
            date=date,
            data_maturity=data_maturity,
        )
        all_keywords.extend(keywords)
        campaign_keyword_map[campaign["id"]] = keywords

    # Aggregate campaign-level performance from keywords
    for campaign in campaigns:
        campaign_keywords = campaign_keyword_map.get(campaign["id"], [])

        if campaign_keywords:
            total_impressions = sum(kw.get("impressions", 0) for kw in campaign_keywords)
            total_taps = sum(kw.get("taps", 0) for kw in campaign_keywords)
            total_installs = sum(kw.get("installs", 0) for kw in campaign_keywords)
            total_spend = sum(kw.get("spend", 0) for kw in campaign_keywords)

            campaign_cpa = round(total_spend / total_installs, 2) if total_installs > 0 else None

            campaign["performance"] = {
                "impressions": total_impressions,
                "taps": total_taps,
                "installs": total_installs,
                "spend": round(total_spend, 2),
                "cpa": campaign_cpa,
            }

    # Count keywords by type
    keyword_counts_by_type = {}
    for campaign_type in CAMPAIGN_TYPES:
        keyword_counts_by_type[campaign_type] = sum(
            len(campaign_keyword_map.get(c["id"], []))
            for c in campaigns if c["campaign_type"] == campaign_type
        )

    return {
        "date": date,
        "data_maturity": data_maturity,
        "campaigns": campaigns,
        "keywords": all_keywords,
        "generated_at": datetime.utcnow().isoformat(),
        "stats": {
            "total_keywords": len(all_keywords),
            "total_campaigns": len(campaigns),
            "keywords_by_type": keyword_counts_by_type,
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


def print_summary(data: Dict[str, Any]) -> None:
    """Print human-readable summary of generated data."""
    print("\n" + "="*70)
    print("CAMPAIGN-TYPE-AWARE DATA GENERATOR - ONE DAY SUMMARY")
    print("="*70)

    print(f"\nDate: {data['date']}")
    print(f"Data Maturity: {data['data_maturity']}")
    print(f"Generated: {data['generated_at']}\n")

    stats = data['stats']
    print(f"Total Campaigns: {stats['total_campaigns']}")
    print(f"Total Keywords: {stats['total_keywords']}\n")

    print("Keywords by Type:")
    for ctype in CAMPAIGN_TYPES:
        count = stats['keywords_by_type'].get(ctype, 0)
        pct = (count / stats['total_keywords']) * 100 if stats['total_keywords'] > 0 else 0
        print(f"  {ctype:12s}: {count:4d} ({pct:5.1f}%)")

    # Sample data from each campaign type
    print("\n" + "="*70)
    print("SAMPLE KEYWORDS (First 3 of each type)")
    print("="*70)

    for campaign_type in CAMPAIGN_TYPES:
        type_keywords = [kw for kw in data['keywords'] if kw['campaign_type'] == campaign_type][:3]

        print(f"\n{campaign_type.upper()}:")
        for kw in type_keywords:
            cpa_str = f"£{kw['cpa']:.2f}" if kw['cpa'] is not None else "null"
            print(f"  Campaign: {kw['campaign_name']}")
            print(f"    Keyword: {kw['keyword_text']}")
            print(f"    Impressions: {kw['impressions']}, Taps: {kw['taps']}, Installs: {kw['installs']}")
            print(f"    Spend: £{kw['spend']:.2f}, CPA: {cpa_str}, Target: £{kw['target_cpa']:.2f}")
            print()

    # Campaign summary by type
    print("="*70)
    print("CAMPAIGN SUMMARY (Aggregate Performance)")
    print("="*70)

    for campaign_type in CAMPAIGN_TYPES:
        campaigns_of_type = [c for c in data['campaigns'] if c['campaign_type'] == campaign_type][:2]

        print(f"\n{campaign_type.upper()} (First 2 campaigns shown):")
        for campaign in campaigns_of_type:
            perf = campaign['performance']
            cpa_str = f"£{perf['cpa']:.2f}" if perf['cpa'] is not None else "null"
            exploration = f" (exploration_budget: £{campaign['exploration_budget']:.2f})" if campaign['exploration_budget'] else ""
            print(f"  {campaign['name']}{exploration}")
            print(f"    Daily Budget: £{campaign['daily_budget']:.2f}, Target CPA: £{campaign['target_cpa']:.2f}")
            print(f"    Impressions: {perf['impressions']}, Installs: {perf['installs']}, Spend: £{perf['spend']:.2f}")
            print(f"    Aggregate CPA: {cpa_str}")

    print("\n" + "="*70)


if __name__ == "__main__":
    filepath = "mock_data/campaign_data.json"
    print("Generating one-day campaign-type-aware dataset...")
    data = generate_one_day_dataset()
    save_to_file(data, filepath)
    print_summary(data)
    print(f"\n✅ Data saved to {filepath}")
