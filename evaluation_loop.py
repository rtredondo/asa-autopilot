#!/usr/bin/env python3
"""
90-day evaluation loop for ASA Autopilot.

Optimized version:
- Pre-computes windowed metrics for all keywords and dates
- Pre-indexes data by campaign and date
- Only evaluates keywords with data on each date
- Applies guardrails (cooldown, grace period) during iteration
"""

import json
import csv
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional, Tuple


def load_parameters():
    """Load parameters from config/parameters.json."""
    with open('config/parameters.json') as f:
        return json.load(f)


def load_90day_data():
    """Load 90-day simulation data from mock_data/continuous_90day.json."""
    with open('mock_data/continuous_90day.json') as f:
        return json.load(f)


class EvaluationLoop:
    def __init__(self, parameters, data):
        self.parameters = parameters
        self.data = data
        self.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        self.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
        self.observation_window = parameters['observation_window']['days']
        self.settling_lag = parameters['data_settling_lag']['days']
        self.cooldown_days = parameters['cooldown_days']['days']
        self.max_bid_change = parameters['bid_movement']['max_fraction']
        self.tolerance_pct = parameters['tolerance_band']['percent_of_target']

        # Build indices
        print("Indexing data...")
        self._build_indices()

        # Pre-compute windowed metrics
        print("Pre-computing windowed metrics for all keywords and dates...")
        self._precompute_windowed_metrics()

        # State: cooldown tracking and Discovery grace period
        self.cooldowns = defaultdict(lambda: None)
        self.discovery_underperformance = defaultdict(lambda: None)

        # Audit log
        self.verdicts = []

        # Statistics
        self.stats = {
            'total_verdicts': 0,
            'actions_by_type': defaultdict(int),
            'no_actions_by_reason': defaultdict(int),
            'actions_blocked_by_cooldown': 0,
            'actions_by_campaign_type': defaultdict(lambda: defaultdict(int)),
        }

    def _build_indices(self):
        """Build efficient indices."""
        # keywords_by_date[(campaign_id, keyword_id, date_str)] -> keyword row
        self.keywords_by_date = {}

        # keywords_by_campaign_date[date_str][campaign_id] -> list of keywords
        self.keywords_by_campaign_date = defaultdict(lambda: defaultdict(list))

        # Campaign lookup
        self.campaigns_by_id = {c['id']: c for c in self.data['campaigns']}

        # unique (campaign_id, keyword_id) pairs
        self.unique_keywords = set()

        for kw in self.data['keywords']:
            campaign_id = kw['campaign_id']
            keyword_id = kw['keyword_id']
            date_str = kw['date']

            key = (campaign_id, keyword_id, date_str)
            self.keywords_by_date[key] = kw

            self.keywords_by_campaign_date[date_str][campaign_id].append(kw)

            self.unique_keywords.add((campaign_id, keyword_id))

    def _precompute_windowed_metrics(self):
        """
        Pre-compute windowed metrics for all unique keywords and all dates.

        windowed_metrics[(campaign_id, keyword_id, date_str)] = {
            'spend': float,
            'installs': int,
            'cpa': float or None
        }
        """
        self.windowed_metrics = {}

        current = self.start_date
        date_count = 0

        while current <= self.end_date:
            date_count += 1
            if date_count % 10 == 0:
                print(f"  Processing date {date_count}/90...")

            date_str = current.strftime('%Y-%m-%d')

            # For this date, compute windowed metrics for all keywords
            for campaign_id, keyword_id in self.unique_keywords:
                spend, installs, cpa = self._compute_windowed_cpa(
                    campaign_id, keyword_id, current
                )
                key = (campaign_id, keyword_id, date_str)
                self.windowed_metrics[key] = {
                    'spend': spend,
                    'installs': installs,
                    'cpa': cpa
                }

            current += timedelta(days=1)

    def _compute_windowed_cpa(self, campaign_id, keyword_id, evaluation_date):
        """
        Compute aggregated CPA for a 7-day window ending at (evaluation_date - 2 days).

        Returns (total_spend, total_installs, windowed_cpa).
        windowed_cpa is None if total_installs == 0.
        """
        window_end = evaluation_date - timedelta(days=self.settling_lag)
        window_start = window_end - timedelta(days=self.observation_window - 1)

        total_spend = 0.0
        total_installs = 0

        current = window_start
        while current <= window_end:
            date_str = current.strftime('%Y-%m-%d')
            key = (campaign_id, keyword_id, date_str)

            if key in self.keywords_by_date:
                kw = self.keywords_by_date[key]
                if kw.get('data_maturity') == 'settled':
                    total_spend += kw.get('spend', 0.0)
                    total_installs += kw.get('installs', 0)

            current += timedelta(days=1)

        windowed_cpa = None
        if total_installs > 0:
            windowed_cpa = total_spend / total_installs

        return total_spend, total_installs, windowed_cpa

    def _get_campaign_windowed_spend(self, campaign_id, evaluation_date):
        """Get total windowed spend for a campaign."""
        window_end = evaluation_date - timedelta(days=self.settling_lag)
        window_start = window_end - timedelta(days=self.observation_window - 1)

        total_spend = 0.0
        current = window_start

        while current <= window_end:
            date_str = current.strftime('%Y-%m-%d')
            for kw in self.keywords_by_campaign_date[date_str][campaign_id]:
                if kw.get('data_maturity') == 'settled':
                    total_spend += kw.get('spend', 0.0)
            current += timedelta(days=1)

        return total_spend

    def evaluate_day(self, day_date):
        """Evaluate all keywords for a single day."""
        date_str = day_date.strftime('%Y-%m-%d')

        # Iterate over keywords that have data on this date
        for campaign_id, keywords_list in self.keywords_by_campaign_date[date_str].items():
            campaign = self.campaigns_by_id[campaign_id]
            campaign_type = campaign['campaign_type']
            target_cpa = campaign['target_cpa']

            for kw in keywords_list:
                keyword_id = kw['keyword_id']
                tier = campaign['tier']

                # Get pre-computed windowed metrics
                metric_key = (campaign_id, keyword_id, date_str)
                metrics = self.windowed_metrics.get(metric_key, {})
                spend = metrics.get('spend', 0.0)
                installs = metrics.get('installs', 0)
                windowed_cpa = metrics.get('cpa', None)

                # Check if entity is on cooldown
                cooldown_until = self.cooldowns[(campaign_id, keyword_id)]
                is_on_cooldown = (cooldown_until is not None and day_date <= cooldown_until)

                # Determine action and reason
                action, reason = self._decide_action(
                    campaign_type, windowed_cpa, target_cpa, spend, installs,
                    campaign_id, keyword_id, day_date, tier, campaign
                )

                # Check guardrails
                if action != 'no_action' and is_on_cooldown:
                    action = 'no_action'
                    reason = f'cooldown_active (until {cooldown_until})'
                    self.stats['actions_blocked_by_cooldown'] += 1

                # Compute after_value for bid adjustments (only for bid_increase/bid_decrease)
                after_value = ''  # Default: blank for all non-bid-action rows
                before_bid = float(kw.get('bid_amount', 0))

                if action == 'bid_decrease' and windowed_cpa is not None:
                    # bid_decrease: CPA is above target, reduce bid by the gap (capped at 20%)
                    pct_gap = (windowed_cpa - target_cpa) / target_cpa
                    capped_adjustment = min(pct_gap, self.max_bid_change)
                    new_bid = before_bid * (1.0 - capped_adjustment)
                    # Ensure minimum £0.01 visible change in the correct direction
                    if new_bid >= before_bid - 0.005:  # Would round to >= before_bid
                        new_bid = before_bid - 0.01
                    after_value = f'{new_bid:.2f}'

                elif action == 'bid_increase' and windowed_cpa is not None:
                    # bid_increase: CPA is below target, increase bid by the gap (capped at 20%)
                    pct_gap = (windowed_cpa - target_cpa) / target_cpa
                    capped_adjustment = min(abs(pct_gap), self.max_bid_change)
                    new_bid = before_bid * (1.0 + capped_adjustment)
                    # Ensure minimum £0.01 visible change in the correct direction
                    if new_bid <= before_bid + 0.005:  # Would round to <= before_bid
                        new_bid = before_bid + 0.01
                    after_value = f'{new_bid:.2f}'

                # Record verdict
                self.verdicts.append({
                    'date': date_str,
                    'campaign': campaign['name'],
                    'campaign_type': campaign_type,
                    'entity_id': keyword_id,
                    'keyword_text': kw.get('keyword_text', ''),
                    'tier': tier,
                    'action_type': action,
                    'reasoning': reason,
                    'before_value': f'{before_bid:.2f}',
                    'after_value': after_value,
                    'windowed_cpa': f'{windowed_cpa:.2f}' if windowed_cpa is not None else 'null',
                    'target_cpa': f'{target_cpa:.2f}',
                    'spend_in_window': f'{spend:.2f}',
                    'installs_in_window': installs,
                    'guardrail_status': 'cooldown_active' if is_on_cooldown else 'none',
                    'executed': 0
                })

                # Update state if action was taken
                if action != 'no_action' and not is_on_cooldown:
                    cooldown_until = day_date + timedelta(days=self.cooldown_days)
                    self.cooldowns[(campaign_id, keyword_id)] = cooldown_until

                # Update stats
                self.stats['total_verdicts'] += 1
                if action == 'no_action':
                    self.stats['no_actions_by_reason'][reason] += 1
                else:
                    self.stats['actions_by_type'][action] += 1
                    self.stats['actions_by_campaign_type'][campaign_type][action] += 1

    def _within_tolerance(self, cpa, target_cpa):
        """Check if CPA is within tolerance band of target."""
        if cpa is None:
            return False
        band = target_cpa * self.tolerance_pct
        return abs(cpa - target_cpa) <= band

    def _decide_action(self, campaign_type, windowed_cpa, target_cpa, spend, installs,
                      campaign_id, keyword_id, day_date, tier, campaign) -> Tuple[str, str]:
        """Determine the action for this entity."""

        if campaign_type in ['brand', 'competitor', 'generic']:
            return self._decide_core_campaign(windowed_cpa, target_cpa, spend, installs)
        elif campaign_type == 'discovery':
            return self._decide_discovery(campaign_id, keyword_id, windowed_cpa, target_cpa,
                                         spend, installs, day_date, campaign)
        else:
            return 'no_action', 'unknown_campaign_type'

    def _decide_core_campaign(self, windowed_cpa, target_cpa, spend, installs) -> Tuple[str, str]:
        """Decision logic for Brand/Competitor/Generic campaigns."""

        # Wasted spend pause
        if spend >= self.parameters['core_campaign_wasted_spend_pause_threshold']['gbp'] and installs == 0:
            return 'pause', 'wasted_spend_pause'

        # No data
        if windowed_cpa is None:
            return 'no_action', 'no_data_in_window'

        # Tolerance band
        if self._within_tolerance(windowed_cpa, target_cpa):
            return 'no_action', 'within_tolerance'

        # Above target: bid decrease
        if windowed_cpa > target_cpa:
            return 'bid_decrease', 'cpa_above_target'

        # Below target: bid increase
        if windowed_cpa < target_cpa:
            return 'bid_increase', 'cpa_below_target'

        return 'no_action', 'unknown_condition'

    def _decide_discovery(self, campaign_id, keyword_id, windowed_cpa, target_cpa,
                         spend, installs, day_date, campaign) -> Tuple[str, str]:
        """Decision logic for Discovery campaigns."""

        # Within or below target
        if windowed_cpa is not None and windowed_cpa <= target_cpa:
            # Graduate if sufficient volume
            if installs >= self.parameters['discovery_graduation']['min_installs_over_window']:
                return 'graduate', 'discovery_graduation'
            else:
                return 'no_action', 'discovery_hold_insufficient_volume'

        # Above target or no data: check for negativize
        campaign_spend = self._get_campaign_windowed_spend(campaign_id, day_date)
        spend_share = spend / campaign_spend if campaign_spend > 0 else 0
        negativize_threshold = self.parameters['discovery_negativize_threshold']['campaign_spend_share']

        if windowed_cpa is not None and windowed_cpa > target_cpa and spend_share >= negativize_threshold:
            reason = f'budget_cap_exceeded: spend_share={spend_share*100:.1f}% exceeds cap={negativize_threshold*100:.0f}%, cpa=£{windowed_cpa:.2f} vs target=£{target_cpa:.2f}'
            return 'negativize', reason

        # Check grace period for pause
        grace_period_days = self.parameters['discovery_pause_grace_period']['calendar_days']

        if windowed_cpa is None or windowed_cpa > target_cpa:
            if self.discovery_underperformance[(campaign_id, keyword_id)] is None:
                self.discovery_underperformance[(campaign_id, keyword_id)] = day_date

            underperf_start = self.discovery_underperformance[(campaign_id, keyword_id)]
            days_underperf = (day_date - underperf_start).days

            if days_underperf >= grace_period_days:
                return 'pause', 'discovery_pause_grace_expired'
            else:
                reason = f'discovery_grace_period_{days_underperf}_of_{grace_period_days}'
                return 'no_action', reason

        return 'no_action', 'discovery_unknown'

    def run(self):
        """Run the evaluation loop for all 90 days."""
        print("\nRunning daily evaluations...")
        current = self.start_date
        day_count = 0

        while current <= self.end_date:
            day_count += 1
            if day_count % 10 == 0:
                print(f"  Day {day_count}/90...")
            self.evaluate_day(current)
            current += timedelta(days=1)

    def export_csv(self, filepath):
        """Export verdicts to CSV."""
        print(f"Exporting {len(self.verdicts)} verdicts to {filepath}...")

        with open(filepath, 'w', newline='') as f:
            fieldnames = [
                'date', 'campaign', 'campaign_type', 'entity_id', 'keyword_text', 'tier',
                'action_type', 'reasoning', 'before_value', 'after_value',
                'windowed_cpa', 'target_cpa', 'spend_in_window', 'installs_in_window',
                'guardrail_status', 'executed'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.verdicts)

    def print_summary(self):
        """Print summary statistics."""
        print("\n" + "="*80)
        print("90-DAY EVALUATION LOOP SUMMARY")
        print("="*80)

        print(f"\nTotal verdicts logged: {self.stats['total_verdicts']}")

        print("\nAction type breakdown:")
        total_actions = sum(self.stats['actions_by_type'].values())
        for action_type in sorted(self.stats['actions_by_type'].keys()):
            count = self.stats['actions_by_type'][action_type]
            pct = (count / total_actions * 100) if total_actions > 0 else 0
            print(f"  {action_type}: {count} ({pct:.1f}%)")

        print("\nNo-action reasons (top 10):")
        sorted_reasons = sorted(self.stats['no_actions_by_reason'].items(),
                               key=lambda x: x[1], reverse=True)[:10]
        for reason, count in sorted_reasons:
            pct = (count / self.stats['total_verdicts'] * 100)
            print(f"  {reason}: {count} ({pct:.1f}%)")

        print(f"\nActions blocked by cooldown: {self.stats['actions_blocked_by_cooldown']}")

        print("\nActions by campaign type:")
        for campaign_type in sorted(self.stats['actions_by_campaign_type'].keys()):
            type_actions = self.stats['actions_by_campaign_type'][campaign_type]
            total_type_actions = sum(type_actions.values())
            print(f"\n  {campaign_type.upper()} ({total_type_actions} actions):")
            for action_type in sorted(type_actions.keys()):
                count = type_actions[action_type]
                pct = (count / total_type_actions * 100) if total_type_actions > 0 else 0
                print(f"    {action_type}: {count} ({pct:.1f}%)")

        print("\n" + "="*80)


def main():
    print("Loading parameters from config/parameters.json...")
    parameters = load_parameters()

    print("Loading 90-day data from mock_data/continuous_90day.json...")
    data = load_90day_data()

    print(f"\nDataset info:")
    print(f"  Date range: {data['start_date']} to {data['end_date']} ({data['num_days']} days)")
    print(f"  Total keywords: {len(data['keywords'])}")
    print(f"  Total campaigns: {len(data['campaigns'])}")

    loop = EvaluationLoop(parameters, data)
    loop.run()

    import os
    os.makedirs('results', exist_ok=True)
    loop.export_csv('results/audit_log.csv')

    loop.print_summary()


if __name__ == '__main__':
    main()
