"""Tests for _calculate_recommended_trus function."""

import pytest
from src.activities.namespace_ops import _calculate_recommended_trus, calculate_minimum_charged_aps


class TestCalculateMinimumChargedAps:
    """Tests for calculate_minimum_charged_aps helper function."""
    
    def test_zero_trus(self):
        """Test that 0 TRUs has no minimum."""
        assert calculate_minimum_charged_aps(0) == 0
    
    def test_one_tru(self):
        """Test that 1 TRU has no minimum."""
        assert calculate_minimum_charged_aps(1) == 0
    
    def test_two_trus(self):
        """Test that 2 TRUs has 100 APS minimum."""
        assert calculate_minimum_charged_aps(2) == 100
    
    def test_five_trus(self):
        """Test that 5 TRUs has 400 APS minimum."""
        assert calculate_minimum_charged_aps(5) == 400
    
    def test_ten_trus(self):
        """Test that 10 TRUs has 900 APS minimum."""
        assert calculate_minimum_charged_aps(10) == 900


class TestCalculateRecommendedTrusFromZero:
    """Tests for recommendations when starting from 0 TRUs (not provisioned)."""
    
    def test_zero_usage_zero_limit(self):
        """Test when namespace has no usage and no provisioning."""
        result = _calculate_recommended_trus(action_limit=0.0, action_count=0.0)
        assert result == 0
    
    def test_low_usage_zero_limit(self):
        """Test when namespace has low usage but no provisioning."""
        # Base capacity (500 APS) is sufficient
        result = _calculate_recommended_trus(action_limit=0.0, action_count=50.0)
        assert result == 0  # No provisioning needed
    
    def test_high_usage_zero_limit(self):
        """Test when namespace has high usage but no provisioning."""
        # Needs more than base capacity (500 APS)
        result = _calculate_recommended_trus(action_limit=0.0, action_count=750.0)
        assert result == 2  # Needs 2 TRUs (never recommends 1)
    
    def test_exact_tru_boundary_zero_limit(self):
        """Test when usage is exactly on TRU boundary."""
        # Exactly at base capacity limit
        result = _calculate_recommended_trus(action_limit=0.0, action_count=500.0)
        assert result == 0  # Base capacity is sufficient
    
    def test_just_over_tru_boundary_zero_limit(self):
        """Test when usage is just over TRU boundary."""
        result = _calculate_recommended_trus(action_limit=0.0, action_count=501.0)
        assert result == 2  # Needs provisioning (minimum 2 TRUs)


class TestCalculateRecommendedTrusScaleUp:
    """Tests for scaling up scenarios (utilization >= 80%)."""
    
    def test_scale_up_at_80_percent(self):
        """Test scaling up when at exactly 80% utilization."""
        # 1 TRU treated as 0, with 400 APS usage (80% of base)
        # This triggers scale-up from 0 since usage > 500 is false
        # So we stay at 0, but we need to re-check...
        # Actually 1 TRU with 400 APS: base provides 500, so 0 TRUs is sufficient
        result = _calculate_recommended_trus(action_limit=500.0, action_count=400.0)
        assert result == 0  # Base capacity (500 APS) is sufficient
    
    def test_scale_up_at_90_percent(self):
        """Test scaling up when at 90% utilization."""
        # 2 TRUs = 1000 APS max, 90% = 900 APS
        result = _calculate_recommended_trus(action_limit=1000.0, action_count=900.0)
        assert result == 3  # Scale up from 2 to 3 TRUs
    
    def test_scale_up_at_100_percent(self):
        """Test scaling up when at 100% utilization."""
        # 5 TRUs = 2500 APS max
        result = _calculate_recommended_trus(action_limit=2500.0, action_count=2500.0)
        assert result == 6  # Scale up from 5 to 6 TRUs
    
    def test_scale_up_just_below_threshold(self):
        """Test no scale up when just below 80% threshold."""
        # 1 TRU = 500 APS max, 79% = 395 APS
        # Base capacity is sufficient
        result = _calculate_recommended_trus(action_limit=500.0, action_count=395.0)
        assert result == 0  # Base capacity is sufficient


class TestCalculateRecommendedTrusScaleDown:
    """Tests for scaling down scenarios (usage below minimum charged)."""
    
    def test_scale_down_from_two_trus(self):
        """Test scaling down from 2 TRUs to 0."""
        # 2 TRUs = 100 APS minimum, current usage = 50 APS
        # optimal = floor(50/100) + 1 = 1 TRU
        # max(1, 2-1) = 1, but 1 TRU with 50 APS < 500 means we can use base
        result = _calculate_recommended_trus(action_limit=1000.0, action_count=50.0)
        assert result == 0  # Scale down to 0 (base capacity sufficient)
    
    def test_scale_down_from_five_trus(self):
        """Test scaling down from 5 TRUs."""
        # 5 TRUs = 400 APS minimum, current usage = 250 APS
        # optimal = floor(250/100) + 1 = 3 TRUs
        # But max reduction is 1 TRU per check, so 5 -> 4
        result = _calculate_recommended_trus(action_limit=2500.0, action_count=250.0)
        assert result == 4  # Scale down by 1 from 5 to 4 TRUs
    
    def test_scale_down_multiple_steps_needed(self):
        """Test scaling down when multiple TRUs could be removed."""
        # 10 TRUs = 900 APS minimum, current usage = 150 APS
        # optimal = floor(150/100) + 1 = 2 TRUs
        # But max reduction is 1 TRU per check, so 10 -> 9
        result = _calculate_recommended_trus(action_limit=5000.0, action_count=150.0)
        assert result == 9  # Scale down by 1 from 10 to 9 TRUs
    
    def test_scale_down_to_zero_from_one_tru(self):
        """Test scaling down to 0 TRUs when usage is very low."""
        # 1 TRU = 500 APS max, using < 20% = < 100 APS
        result = _calculate_recommended_trus(action_limit=500.0, action_count=50.0)
        assert result == 0  # Scale down from 1 to 0 TRUs
    
    def test_stay_at_zero_trus_within_base_capacity(self):
        """Test staying at 0 TRUs when usage is within base capacity."""
        # 1 TRU (treated as 0) with 150 APS usage
        # Base capacity is sufficient
        result = _calculate_recommended_trus(action_limit=500.0, action_count=150.0)
        assert result == 0  # Base capacity is sufficient
    
    def test_at_base_capacity_percentage(self):
        """Test when at 20% of base capacity."""
        # 1 TRU (treated as 0) with 100 APS usage
        # Base capacity is sufficient
        result = _calculate_recommended_trus(action_limit=500.0, action_count=100.0)
        assert result == 0  # Base capacity is sufficient
    
    def test_scale_down_just_below_20_percent(self):
        """Test scaling to 0 when just below 20% of 1 TRU."""
        # 1 TRU = 500 APS max, just below 20% = 99 APS
        result = _calculate_recommended_trus(action_limit=500.0, action_count=99.0)
        assert result == 0  # Scale down to 0 TRUs


class TestCalculateRecommendedTrusNoChange:
    """Tests for scenarios where no change is needed (efficient zone)."""
    
    def test_no_change_within_base_capacity(self):
        """Test no change when usage is within base capacity."""
        # 1 TRU (treated as 0) = 500 APS base, 50% = 250 APS
        result = _calculate_recommended_trus(action_limit=500.0, action_count=250.0)
        assert result == 0  # Base capacity is sufficient
    
    def test_no_change_two_trus_efficient_usage(self):
        """Test no change when at 2 TRUs with efficient usage."""
        # 2 TRUs = 1000 APS max, minimum = 100 APS, current = 300 APS
        result = _calculate_recommended_trus(action_limit=1000.0, action_count=300.0)
        assert result == 2  # No change (above minimum, below 80%)
    
    def test_no_change_five_trus_at_minimum(self):
        """Test no change when exactly at minimum charged threshold."""
        # 5 TRUs = 400 APS minimum, current = 400 APS
        result = _calculate_recommended_trus(action_limit=2500.0, action_count=400.0)
        assert result == 5  # No change (at minimum boundary)
    
    def test_no_change_three_trus_just_above_minimum(self):
        """Test no change when just above minimum charged threshold."""
        # 3 TRUs = 200 APS minimum, current = 250 APS
        result = _calculate_recommended_trus(action_limit=1500.0, action_count=250.0)
        assert result == 3  # No change
    
    def test_no_change_four_trus_just_below_scale_up(self):
        """Test no change when just below scale-up threshold."""
        # 4 TRUs = 2000 APS max, 79% = 1580 APS
        result = _calculate_recommended_trus(action_limit=2000.0, action_count=1580.0)
        assert result == 4  # No change


class TestCalculateRecommendedTrusEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_fractional_action_limit(self):
        """Test with fractional action limit values."""
        # 1.5 TRUs worth of limit (should floor to 1 TRU, treated as 0)
        result = _calculate_recommended_trus(action_limit=750.0, action_count=200.0)
        assert result == 0  # Base capacity is sufficient
    
    def test_very_small_values(self):
        """Test with very small action counts."""
        result = _calculate_recommended_trus(action_limit=500.0, action_count=0.1)
        assert result == 0  # Too small to need provisioning
    
    def test_very_large_values(self):
        """Test with very large action counts."""
        # 100 TRUs = 50000 APS max, 80% = 40000 APS
        result = _calculate_recommended_trus(action_limit=50000.0, action_count=40000.0)
        assert result == 101  # Scale up from 100 to 101 TRUs
    
    def test_zero_action_limit_with_usage(self):
        """Test edge case with 0 limit but positive usage."""
        result = _calculate_recommended_trus(action_limit=0.0, action_count=1000.0)
        assert result == 2  # Need 2 TRUs for 1000 APS
    
    def test_action_count_exceeds_limit(self):
        """Test when action count somehow exceeds the limit."""
        # This shouldn't happen but test it anyway
        # 2 TRUs = 1000 APS limit, but somehow using 1200 APS
        result = _calculate_recommended_trus(action_limit=1000.0, action_count=1200.0)
        assert result == 3  # Scale up (120% utilization)


class TestCalculateRecommendedTrusRealWorldScenarios:
    """Tests based on realistic usage patterns."""
    
    def test_startup_phase(self):
        """Test namespace in startup phase with growing usage."""
        # Starting from scratch with low usage
        # Base capacity is sufficient
        result = _calculate_recommended_trus(action_limit=0.0, action_count=25.0)
        assert result == 0  # Base capacity is sufficient
    
    def test_production_steady_state(self):
        """Test production namespace in steady state."""
        # 10 TRUs provisioned, using 4500 APS (90% utilization)
        result = _calculate_recommended_trus(action_limit=5000.0, action_count=4500.0)
        assert result == 11  # Scale up due to 90% utilization
    
    def test_traffic_spike_scenario(self):
        """Test handling a traffic spike."""
        # 5 TRUs, suddenly at 85% utilization
        result = _calculate_recommended_trus(action_limit=2500.0, action_count=2125.0)
        assert result == 6  # Scale up to handle spike
    
    def test_overnight_low_usage(self):
        """Test overnight when usage drops significantly."""
        # 10 TRUs but only using 500 APS (below 900 minimum)
        result = _calculate_recommended_trus(action_limit=5000.0, action_count=500.0)
        assert result == 9  # Scale down gradually
    
    def test_weekend_shutdown(self):
        """Test weekend when dev namespace is idle."""
        # 3 TRUs but near-zero usage
        result = _calculate_recommended_trus(action_limit=1500.0, action_count=5.0)
        assert result == 2  # Scale down by 1
    
    def test_decommissioned_namespace(self):
        """Test decommissioned namespace with no traffic."""
        # 2 TRUs but zero usage (below minimum)
        # optimal = 1, next_trus = 1, but 0 < 500 so scale to 0
        result = _calculate_recommended_trus(action_limit=1000.0, action_count=0.0)
        assert result == 0  # Scale down to 0 (no usage)
