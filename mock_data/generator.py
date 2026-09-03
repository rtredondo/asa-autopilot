"""Generates realistic synthetic Apple Search Ads data for testing decision engine.

Creates ~56 campaigns across 4 themes and 14 storefronts, 1,500-2,000 keywords
with realistic performance variation (some beating CPI targets, some missing,
some borderline, some with low volume).
"""

import random
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any


# Geo-to-tier mapping
GEO_TIER_MAP = {
    "US": "T1",
    "UK": "T1",
    "CA": "T2",
    "AU": "T2",
    "IE": "T2",
    "NZ": "T2",
    "DE": "T2",
    "FR": "T2",
    "SE": "T2",
    "NL": "T3",
    "NO": "T3",
    "DK": "T3",
    "FI": "T3",
    "IN": "T4",
}

CPI_TARGETS = {
    "T1": 1.60,
    "T2": 1.00,
    "T3": 0.85,
    "T4": 0.60,
}

THEMES = ["brand", "competitors", "generic", "discovery"]

# Keywords for mock data (realistic app-related search terms)
KEYWORD_POOL = [
    "equalization app", "eq audio", "equalizer pro", "bass boost",
    "sound equalizer", "music eq", "audio enhancement", "frequency equalizer",
    "graphic equalizer", "tone control", "audio mixer", "sound effects",
    "music volume booster", "speaker equalizer", "headphone eq", "car audio eq",
    "voice enhancer", "audio effects", "stereo equalizer", "treble boost",
    "best equalizer app", "equalizer music player", "professional audio eq",
    "eq studio", "sound tuner", "audio calibration", "loudness enhancer",
    "equalizer app download", "free equalizer", "premium audio app", "music studio",
]

# Some legacy campaign names for variety
LEGACY_CAMPAIGN_NAMES = [
    "US - Brand",
    "US - Competitors",
    "UK - Brand",
    "UK - Competitors",
]


def generate_campaign_name(geo: str, theme: str, use_legacy: bool = False) -> str:
    """Generate a campaign name in new or legacy format."""
    if use_legacy:
        return f"{geo} - {theme.capitalize()}"
    return f"EQLS_{geo}_{theme.capitalize()}"


def generate_campaigns() -> List[Dict[str, Any]]:
    """Generate ~56 campaigns across 4 themes and 14 geos.

    Budgets are set generously large (£400-800/day) to reflect the intended
    operating model: budget is not the control lever, target CPI is. Generous
    budgets ensure campaigns never hit the budget ceiling under normal operation.
    """
    campaigns = []
    campaign_id = 1000

    for geo in sorted(GEO_TIER_MAP.keys()):
        for theme in THEMES:
            # Occasionally use legacy format for variety
            use_legacy = random.random() < 0.15  # 15% legacy names
            campaign_name = generate_campaign_name(geo, theme, use_legacy)

            campaigns.append({
                "id": str(campaign_id),
                "name": campaign_name,
                "status": random.choice(["ENABLED", "ENABLED", "ENABLED", "PAUSED"]),
                "dailyBudget": round(random.uniform(400, 800), 2),  # Generous, non-binding budget
                "orgId": 1,
                "countryOrRegion": geo,
                "servingStateReasons": [],
                "modificationTime": datetime.utcnow().isoformat(),
            })
            campaign_id += 1

    return campaigns


def generate_keywords_for_campaign(
    campaign_id: str, campaign_name: str, target_count: int = None
) -> List[Dict[str, Any]]:
    """Generate keywords for a single campaign with realistic performance."""
    if target_count is None:
        target_count = random.randint(20, 50)

    keywords = []
    base_keyword_id = int(campaign_id) * 10000

    # Determine tier and CPI target from campaign name (used for all keywords in this campaign)
    if campaign_name.startswith("EQLS_"):
        parts = campaign_name.split("_")
        geo = parts[1]
    else:
        # Legacy format: "GEO - Theme"
        geo = campaign_name.split(" - ")[0]

    tier = GEO_TIER_MAP.get(geo, "T1")
    target_cpi = CPI_TARGETS[tier]

    for i in range(target_count):
        keyword_text = random.choice(KEYWORD_POOL)
        keyword_id = str(base_keyword_id + i)

        # Vary performance: some excel, some struggle, some low volume, and a few with wasted spend
        # Bias toward high performers so campaign aggregates meet or beat CPI targets for budget shift testing
        if i < 8:
            # First 8 keywords of each campaign are high performers (more than low performers)
            performance_profile = random.choices(
                ["high_performer", "meeting_target"],
                weights=[0.70, 0.30],
                k=1,
            )[0]
        else:
            # Remaining keywords have normal distribution
            performance_profile = random.choices(
                ["high_performer", "meeting_target", "below_target", "low_volume", "wasted_spend"],
                weights=[0.10, 0.25, 0.40, 0.10, 0.15],  # 15% have wasted spend for more test cases
                k=1,
            )[0]

        if performance_profile == "high_performer":
            impressions = random.randint(500, 2000)
            cpi_variance = random.uniform(0.70, 0.95)  # 70-95% of target
            installs = max(1, int(random.randint(20, 100) * random.uniform(0.15, 0.45)))
        elif performance_profile == "meeting_target":
            impressions = random.randint(300, 1500)
            cpi_variance = random.uniform(0.95, 1.10)  # ~at target
            installs = max(1, int(random.randint(15, 80) * random.uniform(0.15, 0.45)))
        elif performance_profile == "below_target":
            impressions = random.randint(200, 1000)
            cpi_variance = random.uniform(1.10, 1.40)  # above target
            installs = max(1, int(random.randint(10, 60) * random.uniform(0.15, 0.45)))
        elif performance_profile == "low_volume":
            impressions = random.randint(5, 100)
            cpi_variance = random.uniform(0.5, 1.5)  # all over the place
            installs = max(0, int(random.randint(1, 10) * random.uniform(0.15, 0.45)))
        else:  # wasted_spend: zero installs but meaningful spend (to test pause logic)
            impressions = random.randint(50, 300)
            cpi_variance = random.uniform(0.8, 1.5)
            installs = 0  # Zero conversions despite impressions
            # Spend is set below independent of installs for wasted spend case

        taps = max(1, int(impressions * random.uniform(0.02, 0.08)))

        actual_cpi = round(target_cpi * cpi_variance, 2)

        # For wasted spend: set spend independent of installs, always positive
        if performance_profile == "wasted_spend":
            # Generate spend without conversions: £20-60 is "meaningful wasted spend"
            spend = round(random.uniform(20.0, 60.0), 2)
        else:
            spend = round(installs * actual_cpi, 2) if installs > 0 else 0

        keywords.append({
            "id": keyword_id,
            "text": keyword_text,
            "status": random.choice(["ENABLED", "ENABLED", "ENABLED", "PAUSED"]),
            "bidAmount": {
                "amount": str(round(random.uniform(0.20, 5.00), 2)),
                "currency": "GBP",
            },
            "modificationTime": datetime.utcnow().isoformat(),
            # Performance metrics (normally would come from separate API call)
            "performance": {
                "impressions": impressions,
                "taps": taps,
                "installs": installs,
                "spend": spend,
                "cpi": actual_cpi,
                "tier": tier,
                "target_cpi": target_cpi,
            },
        })

    return keywords


def generate_synthetic_dataset() -> Dict[str, Any]:
    """Generate complete synthetic dataset with campaigns and keywords."""
    campaigns = generate_campaigns()

    # Calculate total keywords to distribute ~1,500-2,000 across campaigns
    total_keywords_target = random.randint(1500, 2000)
    keywords_per_campaign = total_keywords_target // len(campaigns)
    remainder = total_keywords_target % len(campaigns)

    all_keywords = []
    campaign_keyword_map = {}  # Track keywords per campaign for spend calculation

    for idx, campaign in enumerate(campaigns):
        # Distribute remainder unevenly for realism
        kw_count = keywords_per_campaign + (1 if idx < remainder else 0)
        keywords = generate_keywords_for_campaign(campaign["id"], campaign["name"], kw_count)
        all_keywords.extend(keywords)
        campaign_keyword_map[campaign["id"]] = keywords

    # Calculate campaign-level performance and add prior week spend variance
    for campaign in campaigns:
        campaign_keywords = campaign_keyword_map.get(campaign["id"], [])

        if campaign_keywords:
            # Calculate total spend from keywords
            total_spend = sum(kw.get("performance", {}).get("spend", 0) for kw in campaign_keywords)
            total_installs = sum(kw.get("performance", {}).get("installs", 0) for kw in campaign_keywords)

            # Daily spend is approximately 1/7th of total 7-day spend
            daily_spend = total_spend / 7.0

            # Prior week spend variance: some campaigns are ramping up (current > prior)
            # This tests the spend ceiling guardrail: if current is 10%+ more than prior, reject
            # Create realistic distribution: -30% to +100% of current spend (some growing fast)
            spend_variance = random.uniform(-0.30, 1.00)
            prior_7day_spend = total_spend * (1 + spend_variance)
            prior_7day_spend = max(0.01, prior_7day_spend)  # Ensure positive to avoid division by zero

            avg_cpi = total_spend / total_installs if total_installs > 0 else 0

            campaign["performance"] = {
                "installs": total_installs,
                "spend": total_spend,
                "daily_spend": daily_spend,
                "cpi": avg_cpi,
                "target_cpi": campaign_keywords[0].get("performance", {}).get("target_cpi", 1.0),
                "prior_7day_spend": prior_7day_spend,  # For spend ceiling check
            }
        else:
            campaign["performance"] = {
                "installs": 0,
                "spend": 0,
                "daily_spend": 0,
                "cpi": 0,
                "target_cpi": 1.0,
                "prior_7day_spend": 0,
            }

    return {
        "campaigns": campaigns,
        "keywords": all_keywords,
        "generated_at": datetime.utcnow().isoformat(),
        "total_keywords": len(all_keywords),
        "total_campaigns": len(campaigns),
    }


def save_to_file(data: Dict[str, Any], filepath: str) -> None:
    """Save generated dataset to JSON file."""
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def load_from_file(filepath: str) -> Dict[str, Any]:
    """Load dataset from JSON file."""
    with open(filepath, "r") as f:
        return json.load(f)


if __name__ == "__main__":
    import sys

    filepath = "mock_data/synthetic_data.json"
    dataset = generate_synthetic_dataset()
    save_to_file(dataset, filepath)
    print(f"Generated {dataset['total_campaigns']} campaigns with {dataset['total_keywords']} keywords")
    print(f"Saved to {filepath}")
