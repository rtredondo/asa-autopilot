#!/usr/bin/env python3
"""Streamlit dashboard for ASA Autopilot decision engine.

Settings panel for viewing and editing config/parameters.json.
Run Evaluation button to trigger 90-day evaluation loop.
"""

import sys
import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from log_config import setup_logging

setup_logging(log_level="INFO")
logger = logging.getLogger(__name__)

# Streamlit config
st.set_page_config(
    page_title="ASA Autopilot Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# EQUALS-branded header
st.markdown("""
<style>
.equals-header {
    border-bottom: 3px solid #2400FF;
    padding-bottom: 8px;
    margin-bottom: 20px;
}
.equals-title {
    font-size: 32px;
    font-weight: 700;
    color: #2400FF;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", sans-serif;
    margin: 0;
    padding: 0;
    letter-spacing: -0.5px;
}
.equals-subtitle {
    font-size: 13px;
    color: #666;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", sans-serif;
    margin: 4px 0 0 0;
    padding: 0;
    font-weight: 500;
}
.success-box {
    background-color: #E8F5E9;
    border-left: 4px solid #4CAF50;
    padding: 12px;
    border-radius: 4px;
    margin: 10px 0;
}
.info-box {
    background-color: #E3F2FD;
    border-left: 4px solid #2196F3;
    padding: 12px;
    border-radius: 4px;
    margin: 10px 0;
}
</style>

<div class="equals-header">
<div class="equals-title">EQUALS · ASA Decision Engine</div>
<div class="equals-subtitle">Prepared by Rafael Redondo</div>
</div>
""", unsafe_allow_html=True)


def load_parameters():
    """Load parameters from config/parameters.json."""
    config_path = Path("config/parameters.json")
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return None


def save_parameters(params):
    """Safely save parameters to config/parameters.json."""
    config_path = Path("config/parameters.json")

    # Write to temp file first
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
        json.dump(params, tmp, indent=2)
        tmp_path = tmp.name

    # Replace original file
    Path(tmp_path).replace(config_path)
    logger.info(f"Parameters saved to {config_path}")


def run_evaluation_loop():
    """Run evaluation_loop.py and return True if successful."""
    try:
        result = subprocess.run(
            ["python3", "evaluation_loop.py"],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.error("Evaluation loop timed out after 10 minutes")
        return False
    except Exception as e:
        logger.error(f"Error running evaluation loop: {e}")
        return False


def render_settings_panel():
    """Render the settings panel for parameter editing."""

    st.header("⚙️ Settings")
    st.markdown("Configure ASA Autopilot decision engine parameters. Changes are saved to `config/parameters.json`.")

    params = load_parameters()
    if params is None:
        st.error("Could not load config/parameters.json")
        return

    # Create a copy for editing
    edited_params = json.loads(json.dumps(params))

    # ===== CPA TARGETS =====
    st.subheader("CPA Targets (GBP per install)")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        edited_params["cpa_targets"]["T1"] = st.number_input(
            "T1 (US, UK)",
            min_value=0.1,
            max_value=10.0,
            step=0.01,
            value=float(params["cpa_targets"]["T1"]),
            key="t1_target"
        )

    with col2:
        edited_params["cpa_targets"]["T2"] = st.number_input(
            "T2 (CA, AU, DE, FR)",
            min_value=0.1,
            max_value=10.0,
            step=0.01,
            value=float(params["cpa_targets"]["T2"]),
            key="t2_target"
        )

    with col3:
        edited_params["cpa_targets"]["T3"] = st.number_input(
            "T3 (IE, NZ, NL)",
            min_value=0.1,
            max_value=10.0,
            step=0.01,
            value=float(params["cpa_targets"]["T3"]),
            key="t3_target"
        )

    with col4:
        edited_params["cpa_targets"]["T4"] = st.number_input(
            "T4 (SE, NO, DK, FI, IN)",
            min_value=0.1,
            max_value=10.0,
            step=0.01,
            value=float(params["cpa_targets"]["T4"]),
            key="t4_target"
        )

    st.divider()

    # ===== TIMING WINDOWS =====
    st.subheader("Timing Windows")
    col1, col2, col3 = st.columns(3)

    with col1:
        edited_params["observation_window"]["days"] = st.number_input(
            "Observation Window (days)",
            min_value=1,
            max_value=30,
            value=int(params["observation_window"]["days"]),
            key="obs_window",
            help="Days of trailing settled data to aggregate for CPA calculation"
        )

    with col2:
        edited_params["data_settling_lag"]["days"] = st.number_input(
            "Data Settling Lag (days)",
            min_value=0,
            max_value=10,
            value=int(params["data_settling_lag"]["days"]),
            key="settling_lag",
            help="Most recent days excluded as provisional"
        )

    with col3:
        edited_params["cooldown_days"]["days"] = st.number_input(
            "Cooldown Period (days)",
            min_value=1,
            max_value=30,
            value=int(params["cooldown_days"]["days"]),
            key="cooldown",
            help="Days entity is ineligible for another action"
        )

    st.divider()

    # ===== BID RULES =====
    st.subheader("Bid Optimization Rules")
    col1, col2, col3 = st.columns(3)

    with col1:
        bid_frac = st.number_input(
            "Max Bid Movement (fraction)",
            min_value=0.01,
            max_value=1.0,
            step=0.01,
            value=float(params["bid_movement"]["max_fraction"]),
            key="max_bid_move",
            help="Maximum bid change per cycle (0.20 = 20%)"
        )
        edited_params["bid_movement"]["max_fraction"] = bid_frac

    with col2:
        tol_pct = st.number_input(
            "Tolerance Band (% of target)",
            min_value=0.0,
            max_value=20.0,
            step=0.5,
            value=float(params["tolerance_band"]["percent_of_target"]) * 100,
            key="tolerance",
            help="No action if CPA within this band of target"
        )
        edited_params["tolerance_band"]["percent_of_target"] = tol_pct / 100.0

    with col3:
        edited_params["core_campaign_wasted_spend_pause_threshold"]["gbp"] = st.number_input(
            "Wasted Spend Pause Threshold (£)",
            min_value=1.0,
            max_value=100.0,
            step=1.0,
            value=float(params["core_campaign_wasted_spend_pause_threshold"]["gbp"]),
            key="wasted_spend",
            help="Min spend with zero installs to trigger pause"
        )

    st.divider()

    # ===== DISCOVERY RULES =====
    st.subheader("Discovery Campaign Rules")
    col1, col2, col3 = st.columns(3)

    with col1:
        edited_params["discovery_graduation"]["min_installs_over_window"] = st.number_input(
            "Graduation Min Installs",
            min_value=1,
            max_value=100,
            value=int(params["discovery_graduation"]["min_installs_over_window"]),
            key="grad_installs",
            help="Min installs over window to qualify for graduation"
        )

    with col2:
        neg_share = st.number_input(
            "Negativize Spend Share Threshold",
            min_value=0.01,
            max_value=1.0,
            step=0.01,
            value=float(params["discovery_negativize_threshold"]["campaign_spend_share"]),
            key="neg_threshold",
            help="Campaign spend fraction to trigger negativize (0.15 = 15%)"
        )
        edited_params["discovery_negativize_threshold"]["campaign_spend_share"] = neg_share

    with col3:
        edited_params["discovery_pause_grace_period"]["calendar_days"] = st.number_input(
            "Pause Grace Period (calendar days)",
            min_value=1,
            max_value=60,
            value=int(params["discovery_pause_grace_period"]["calendar_days"]),
            key="grace_period",
            help="Days of underperformance before pause"
        )

    st.divider()

    # ===== BUDGET ALLOCATION =====
    st.subheader("Budget Allocation (Context Only)")
    st.caption("These values are informational and gate Discovery logic. Total should equal 1.0.")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        brand_alloc = st.number_input(
            "Brand",
            min_value=0.0,
            max_value=1.0,
            step=0.01,
            value=float(params["budget_allocation"]["brand"]),
            key="alloc_brand"
        )
        edited_params["budget_allocation"]["brand"] = brand_alloc

    with col2:
        comp_alloc = st.number_input(
            "Competitor",
            min_value=0.0,
            max_value=1.0,
            step=0.01,
            value=float(params["budget_allocation"]["competitor"]),
            key="alloc_comp"
        )
        edited_params["budget_allocation"]["competitor"] = comp_alloc

    with col3:
        gen_alloc = st.number_input(
            "Generic",
            min_value=0.0,
            max_value=1.0,
            step=0.01,
            value=float(params["budget_allocation"]["generic"]),
            key="alloc_gen"
        )
        edited_params["budget_allocation"]["generic"] = gen_alloc

    with col4:
        disc_alloc = st.number_input(
            "Discovery",
            min_value=0.0,
            max_value=1.0,
            step=0.01,
            value=float(params["budget_allocation"]["discovery"]),
            key="alloc_disc"
        )
        edited_params["budget_allocation"]["discovery"] = disc_alloc

    total_alloc = brand_alloc + comp_alloc + gen_alloc + disc_alloc
    st.caption(f"Total allocation: {total_alloc:.2f} (1.00 preferred)")

    st.divider()

    # ===== SAVE BUTTON =====
    col1, col2 = st.columns([3, 1])

    with col2:
        if st.button("💾 Save Settings", use_container_width=True, type="primary"):
            try:
                save_parameters(edited_params)
                st.markdown("""
                <div class="success-box">
                <strong>✓ Settings saved successfully</strong><br>
                Changes written to config/parameters.json
                </div>
                """, unsafe_allow_html=True)
                st.session_state.settings_saved = True
            except Exception as e:
                st.error(f"Failed to save settings: {e}")

    st.divider()


def render_evaluation_panel():
    """Render the evaluation run panel."""

    st.header("🚀 Run Evaluation")
    st.markdown("Execute the 90-day evaluation loop using current parameters.")

    audit_log_path = Path("results/audit_log.csv")

    col1, col2 = st.columns([1, 3])

    with col1:
        if st.button("▶️ Run Evaluation", use_container_width=True, type="primary", key="run_eval"):
            st.session_state.running_eval = True

    if st.session_state.get("running_eval"):
        progress_bar = st.progress(0)
        status_text = st.empty()

        status_text.text("⏳ Starting evaluation loop (this takes ~30-60 seconds)...")
        progress_bar.progress(20)

        status_text.text("⏳ Processing 90 days of data across all keywords...")
        progress_bar.progress(50)

        start_time = time.time()
        success = run_evaluation_loop()
        elapsed = time.time() - start_time

        if success:
            progress_bar.progress(100)
            status_text.empty()

            st.markdown(f"""
            <div class="success-box">
            <strong>✓ Evaluation completed successfully</strong><br>
            Completed in {elapsed:.1f} seconds<br>
            Audit log regenerated: {audit_log_path}
            </div>
            """, unsafe_allow_html=True)

            # Show audit log summary
            if audit_log_path.exists():
                df = pd.read_csv(audit_log_path)
                st.subheader("Audit Log Summary")

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Verdicts", len(df))
                with col2:
                    action_count = len(df[df["action_type"] != "no_action"])
                    st.metric("Actions", action_count)
                with col3:
                    pause_count = len(df[df["action_type"] == "pause"])
                    st.metric("Pauses", pause_count)
                with col4:
                    grad_count = len(df[df["action_type"] == "graduate"])
                    st.metric("Graduations", grad_count)

                st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            progress_bar.progress(100)
            status_text.empty()
            st.error("❌ Evaluation failed. Check logs for details.")

        st.session_state.running_eval = False

    st.divider()

    # ===== AUDIT LOG SECTION =====
    if audit_log_path.exists():
        st.subheader("📋 Audit Log (Decision Verdicts)")

        file_size_mb = audit_log_path.stat().st_size / (1024*1024)
        st.caption(f"File: {audit_log_path} | Size: {file_size_mb:.1f} MB | ~159,000 rows (90 days × ~1,700 keywords)")

        # Load full audit log
        audit_df = pd.read_csv(audit_log_path)
        audit_df["date"] = pd.to_datetime(audit_df["date"])

        # Date picker for preview
        col1, col2 = st.columns([1, 3])
        with col1:
            preview_date_str = st.selectbox(
                "Preview date:",
                sorted(audit_df["date"].dt.date.unique(), reverse=True),
                format_func=lambda x: str(x),
                key="audit_preview_date"
            )
            preview_date = pd.to_datetime(preview_date_str)

        # Show preview of selected date
        preview_df = audit_df[audit_df["date"] == preview_date].copy()
        st.dataframe(
            preview_df[["date", "campaign", "keyword_text", "action_type", "windowed_cpa", "target_cpa", "reasoning"]].head(15),
            use_container_width=True,
            hide_index=True
        )
        st.caption(f"Showing {len(preview_df)} verdicts for {preview_date_str} (preview limited to 15 rows)")

        # Download button for complete audit log
        with open(audit_log_path, "rb") as f:
            csv_bytes = f.read()

        st.download_button(
            label="⬇️ Download Full Audit Log (CSV)",
            data=csv_bytes,
            file_name=f"audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.divider()

    # ===== RAW DATA SECTION =====
    raw_data_path = Path("mock_data/continuous_90day.json")
    if raw_data_path.exists():
        st.subheader("📊 Raw Simulated Data (90-Day Input)")
        st.caption("Underlying simulated dataset that the decision engine reads from")

        # Load raw data
        with open(raw_data_path) as f:
            raw_data_json = json.load(f)

        keywords = raw_data_json["keywords"]

        # Convert to DataFrame for easier handling
        raw_df = pd.DataFrame(keywords)
        raw_df["date"] = pd.to_datetime(raw_df["date"])

        file_size_mb = raw_data_path.stat().st_size / (1024*1024)
        st.caption(f"File: {raw_data_path} | Size: {file_size_mb:.1f} MB | {len(keywords):,} keyword-days")

        # Date picker for preview
        col1, col2 = st.columns([1, 3])
        with col1:
            preview_date_str = st.selectbox(
                "Preview date:",
                sorted(raw_df["date"].dt.date.unique(), reverse=True),
                format_func=lambda x: str(x),
                key="raw_preview_date"
            )
            preview_date = pd.to_datetime(preview_date_str)

        # Show preview of selected date with key columns
        preview_cols = ["date", "campaign_name", "keyword_text", "impressions", "taps", "installs", "spend", "cpa", "data_maturity"]
        preview_raw_df = raw_df[raw_df["date"] == preview_date][preview_cols].head(15)

        st.dataframe(preview_raw_df, use_container_width=True, hide_index=True)
        st.caption(f"Showing {len(raw_df[raw_df['date'] == preview_date])} keyword rows for {preview_date_str} (preview limited to 15 rows)")

        # Convert and download full raw data as CSV
        @st.cache_data
        def convert_raw_to_csv():
            """Convert raw JSON data to CSV bytes."""
            csv_df = pd.DataFrame(keywords)
            return csv_df.to_csv(index=False).encode('utf-8')

        csv_bytes = convert_raw_to_csv()

        st.download_button(
            label="⬇️ Download Raw Data (CSV)",
            data=csv_bytes,
            file_name=f"continuous_90day_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.divider()

    # ===== SPEND ALLOCATION SECTION =====
    render_spend_allocation_panel()


def render_spend_allocation_panel():
    """
    Display observed spend allocation by campaign type from simulated account data.
    This panel shows what the market allocated under existing bids before any autopilot actions.
    """
    st.subheader("💰 Observed Spend Allocation")

    st.markdown("""
    **Spend the simulated market recorded under existing bids, before any autopilot action.**
    The autopilot system makes proposal-only decisions (no actions executed yet, executed=0 for all verdicts).
    This panel shows the allocation the simulated market produced independently; the system did not drive this distribution.
    """)

    # Load simulated data
    with open('mock_data/continuous_90day.json') as f:
        raw_data = json.load(f)

    keywords_df = pd.DataFrame(raw_data['keywords'])
    keywords_df['date'] = pd.to_datetime(keywords_df['date'])

    # Map campaign IDs to types
    campaigns = raw_data['campaigns']
    campaign_types = {c['id']: c['campaign_type'] for c in campaigns}
    keywords_df['campaign_type'] = keywords_df['campaign_id'].map(campaign_types)

    # Window selection
    selected_window = st.radio(
        "Select period:",
        options=["Full 90 days", "Last 30 days"],
        horizontal=True,
        key="spend_window"
    )

    # Filter data by window
    if selected_window == "Last 30 days":
        max_date = keywords_df['date'].max()
        cutoff_date = max_date - pd.Timedelta(days=29)
        window_df = keywords_df[keywords_df['date'] >= cutoff_date]
        period_label = f"{cutoff_date.date()} to {max_date.date()}"
    else:
        window_df = keywords_df
        min_date = keywords_df['date'].min()
        max_date = keywords_df['date'].max()
        period_label = f"{min_date.date()} to {max_date.date()}"

    # Calculate totals
    total_spend = window_df['spend'].sum()
    total_installs = window_df['installs'].sum()

    # Display summary metrics
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Account Spend", f"£{total_spend:,.0f}")
    with col2:
        st.metric("Total Installs", f"{total_installs:,}")

    st.caption(f"Period: {period_label}")
    st.divider()

    # Breakdown by campaign type
    st.subheader("Spend by Campaign Type")

    spend_by_type = window_df.groupby('campaign_type').agg({
        'spend': 'sum',
        'installs': 'sum'
    }).sort_values('spend', ascending=False)

    # Calculate percentages and CPA
    spend_by_type['pct_of_total'] = (spend_by_type['spend'] / total_spend * 100).round(1)
    spend_by_type['cpa'] = (spend_by_type['spend'] / spend_by_type['installs']).round(2)

    # Format for display
    display_df = spend_by_type.copy()
    display_df.columns = ['Spend (£)', 'Installs', '% of Total', 'Avg CPA (£)']
    display_df['Spend (£)'] = display_df['Spend (£)'].apply(lambda x: f"£{x:,.0f}")
    display_df['Installs'] = display_df['Installs'].apply(lambda x: f"{x:,}")
    display_df['% of Total'] = display_df['% of Total'].apply(lambda x: f"{x:.1f}%")
    display_df['Avg CPA (£)'] = display_df['Avg CPA (£)'].apply(lambda x: f"£{x:.2f}")

    st.dataframe(display_df, use_container_width=True)

    # Discovery callout
    st.divider()
    st.subheader("Discovery Campaign Allocation")

    discovery_spend = spend_by_type.loc['discovery', 'spend'] if 'discovery' in spend_by_type.index else 0
    discovery_pct = (discovery_spend / total_spend * 100) if total_spend > 0 else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Discovery Spend", f"£{discovery_spend:,.0f}")
    with col2:
        st.metric("Discovery % of Total", f"{discovery_pct:.1f}%")
    with col3:
        st.metric("Strategic Guideline", "~25%")

    st.caption(
        "Strategic allocation guideline: Discovery campaigns typically receive ~25% of account budget for exploration. "
        "Actual allocation is determined by the simulated market performance under current bids and is monitored here for human review."
    )


def main():
    """Main dashboard app."""

    # Initialize session state
    if "settings_saved" not in st.session_state:
        st.session_state.settings_saved = False
    if "running_eval" not in st.session_state:
        st.session_state.running_eval = False

    # Create tabs
    tab1, tab2 = st.tabs(["⚙️ Settings", "🚀 Evaluation"])

    with tab1:
        render_settings_panel()

    with tab2:
        render_evaluation_panel()


if __name__ == "__main__":
    main()
