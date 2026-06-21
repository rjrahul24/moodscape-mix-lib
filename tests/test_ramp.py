"""Tests for the _ramp_factor helper in meditation_mixer.tts.

Verifies the progressive pause ramp-down multiplier used for sleep stories.
When end_scale == 1.0 (meditation default) the factor must be exactly 1.0
for every index, preserving byte-identical output on the meditation path.
"""
import pytest

from meditation_mixer.tts import _ramp_factor


class TestRampFactorIdentity:
    """When end_scale=1.0, factor is always exactly 1.0."""

    @pytest.mark.parametrize("total", [1, 2, 5, 11, 100])
    def test_first_index(self, total):
        assert _ramp_factor(0, total, 1.0) == 1.0

    @pytest.mark.parametrize("total", [2, 5, 11, 100])
    def test_last_index(self, total):
        assert _ramp_factor(total - 1, total, 1.0) == 1.0

    @pytest.mark.parametrize("total", [5, 11, 100])
    def test_middle_index(self, total):
        mid = total // 2
        assert _ramp_factor(mid, total, 1.0) == 1.0


class TestRampFactorScaling:
    """When end_scale > 1.0, interpolation is correct."""

    def test_first_index_is_one(self):
        assert _ramp_factor(0, 11, 1.6) == 1.0

    def test_last_index_is_end_scale(self):
        assert _ramp_factor(10, 11, 1.6) == pytest.approx(1.6)

    def test_midpoint(self):
        assert _ramp_factor(5, 11, 1.6) == pytest.approx(1.3)

    def test_quarter_point(self):
        # index 2 of 9 total => frac = 2/8 = 0.25, factor = 1 + 0.6*0.25 = 1.15
        assert _ramp_factor(2, 9, 1.6) == pytest.approx(1.15)


class TestRampFactorEdgeCases:
    """Edge cases: single-chunk or zero-chunk scripts."""

    def test_total_one_returns_one(self):
        assert _ramp_factor(0, 1, 1.6) == 1.0

    def test_total_zero_returns_one(self):
        assert _ramp_factor(0, 0, 1.6) == 1.0

    def test_total_one_end_scale_two(self):
        assert _ramp_factor(0, 1, 2.0) == 1.0


class TestRampFactorMonotonic:
    """Factor is non-decreasing across indices when end_scale > 1.0."""

    @pytest.mark.parametrize("end_scale", [1.2, 1.6, 2.0, 3.0])
    def test_monotonic_non_decreasing(self, end_scale):
        total = 20
        factors = [_ramp_factor(i, total, end_scale) for i in range(total)]
        for a, b in zip(factors, factors[1:]):
            assert b >= a
