"""Regression tests for meditation_mixer.presets module.

Ensures that content presets are correctly defined and that the MEDITATION
preset matches today's documented app defaults exactly.
"""
import pytest

from meditation_mixer.presets import MEDITATION, SLEEP_STORY, PRESETS


class TestPresetsRegistry:
    """Tests for the PRESETS registry structure."""

    def test_presets_has_exactly_two_entries(self):
        """PRESETS dict contains exactly 2 presets."""
        assert len(PRESETS) == 2

    def test_presets_order_meditation_first(self):
        """PRESETS keys are in order: Meditation, Sleep Story."""
        keys = list(PRESETS.keys())
        assert keys == ["Meditation", "Sleep Story"]

    def test_presets_values_are_instances(self):
        """Both PRESETS values are the correct instances."""
        assert PRESETS["Meditation"] is MEDITATION
        assert PRESETS["Sleep Story"] is SLEEP_STORY


class TestMeditationPreset:
    """Regression guard: MEDITATION field values must match documented defaults."""

    def test_meditation_key(self):
        """MEDITATION.key == 'meditation'."""
        assert MEDITATION.key == "meditation"

    def test_meditation_label(self):
        """MEDITATION.label == 'Meditation'."""
        assert MEDITATION.label == "Meditation"

    def test_meditation_guide_file(self):
        """MEDITATION.guide_file == 'docs/MEDITATION_GUIDE.md'."""
        assert MEDITATION.guide_file == "docs/MEDITATION_GUIDE.md"

    def test_meditation_render_prefix(self):
        """MEDITATION.render_prefix == 'meditation'."""
        assert MEDITATION.render_prefix == "meditation"

    def test_meditation_pause_scale(self):
        """MEDITATION.pause_scale == 2.0."""
        assert MEDITATION.pause_scale == 2.0

    def test_meditation_tone_preset(self):
        """MEDITATION.tone_preset == '[soft][slowly]'."""
        assert MEDITATION.tone_preset == "[soft][slowly]"

    def test_meditation_inter_chunk_silence_ms(self):
        """MEDITATION.inter_chunk_silence_ms == 300.0."""
        assert MEDITATION.inter_chunk_silence_ms == 300.0

    def test_meditation_max_chunk_chars(self):
        """MEDITATION.max_chunk_chars == None (uses config default)."""
        assert MEDITATION.max_chunk_chars is None

    def test_meditation_stability(self):
        """MEDITATION.stability == 0.50."""
        assert MEDITATION.stability == 0.50

    def test_meditation_ramp_pause_end_scale(self):
        """MEDITATION.ramp_pause_end_scale == 1.0 (ramp OFF)."""
        assert MEDITATION.ramp_pause_end_scale == 1.0

    def test_meditation_bg_gain_db(self):
        """MEDITATION.bg_gain_db == -13.0."""
        assert MEDITATION.bg_gain_db == -13.0

    def test_meditation_duck_range_db(self):
        """MEDITATION.duck_range_db == -7.0."""
        assert MEDITATION.duck_range_db == -7.0

    def test_meditation_duck_release_ms(self):
        """MEDITATION.duck_release_ms == 1200.0."""
        assert MEDITATION.duck_release_ms == 1200.0

    def test_meditation_duck_lift_db(self):
        """MEDITATION.duck_lift_db == 2.0."""
        assert MEDITATION.duck_lift_db == 2.0

    def test_meditation_placeholder_is_string(self):
        """MEDITATION.placeholder is a non-empty string."""
        assert isinstance(MEDITATION.placeholder, str)
        assert len(MEDITATION.placeholder) > 0

    def test_meditation_placeholder_contains_key_phrases(self):
        """MEDITATION.placeholder contains expected phrases from current app default."""
        assert "Welcome" in MEDITATION.placeholder
        assert "[soft]" in MEDITATION.placeholder
        assert "[gentle]" in MEDITATION.placeholder
        assert "[breathes]" in MEDITATION.placeholder
        assert "[calm]" in MEDITATION.placeholder
        assert "[exhales]" in MEDITATION.placeholder


class TestSleepStoryPreset:
    """Tests for the SLEEP_STORY preset values."""

    def test_sleep_story_key(self):
        """SLEEP_STORY.key == 'sleep_story'."""
        assert SLEEP_STORY.key == "sleep_story"

    def test_sleep_story_label(self):
        """SLEEP_STORY.label == 'Sleep Story'."""
        assert SLEEP_STORY.label == "Sleep Story"

    def test_sleep_story_guide_file(self):
        """SLEEP_STORY.guide_file == 'docs/SLEEP_STORY_GUIDE.md'."""
        assert SLEEP_STORY.guide_file == "docs/SLEEP_STORY_GUIDE.md"

    def test_sleep_story_render_prefix(self):
        """SLEEP_STORY.render_prefix == 'sleep_story'."""
        assert SLEEP_STORY.render_prefix == "sleep_story"

    def test_sleep_story_pause_scale(self):
        """SLEEP_STORY.pause_scale == 1.1."""
        assert SLEEP_STORY.pause_scale == 1.1

    def test_sleep_story_tone_preset(self):
        """SLEEP_STORY.tone_preset == '[calm][soft]'."""
        assert SLEEP_STORY.tone_preset == "[calm][soft]"

    def test_sleep_story_inter_chunk_silence_ms(self):
        """SLEEP_STORY.inter_chunk_silence_ms == 200.0."""
        assert SLEEP_STORY.inter_chunk_silence_ms == 200.0

    def test_sleep_story_max_chunk_chars(self):
        """SLEEP_STORY.max_chunk_chars == 1600."""
        assert SLEEP_STORY.max_chunk_chars == 1600

    def test_sleep_story_stability(self):
        """SLEEP_STORY.stability == 0.50."""
        assert SLEEP_STORY.stability == 0.50

    def test_sleep_story_ramp_pause_end_scale(self):
        """SLEEP_STORY.ramp_pause_end_scale == 1.6."""
        assert SLEEP_STORY.ramp_pause_end_scale == 1.6

    def test_sleep_story_bg_gain_db(self):
        """SLEEP_STORY.bg_gain_db == -17.0."""
        assert SLEEP_STORY.bg_gain_db == -17.0

    def test_sleep_story_duck_range_db(self):
        """SLEEP_STORY.duck_range_db == -4.0."""
        assert SLEEP_STORY.duck_range_db == -4.0

    def test_sleep_story_duck_release_ms(self):
        """SLEEP_STORY.duck_release_ms == 1500.0."""
        assert SLEEP_STORY.duck_release_ms == 1500.0

    def test_sleep_story_duck_lift_db(self):
        """SLEEP_STORY.duck_lift_db == 0.75."""
        assert SLEEP_STORY.duck_lift_db == 0.75

    def test_sleep_story_placeholder_is_string(self):
        """SLEEP_STORY.placeholder is a non-empty string."""
        assert isinstance(SLEEP_STORY.placeholder, str)
        assert len(SLEEP_STORY.placeholder) > 0


class TestRampPauseEndScale:
    """Tests validating ramp_pause_end_scale semantics across presets."""

    def test_meditation_ramp_pause_off(self):
        """MEDITATION has ramp_pause_end_scale == 1.0 (feature OFF)."""
        assert MEDITATION.ramp_pause_end_scale == 1.0

    def test_sleep_story_ramp_pause_enabled(self):
        """SLEEP_STORY has ramp_pause_end_scale > 1.0 (feature ON)."""
        assert SLEEP_STORY.ramp_pause_end_scale > 1.0

    def test_sleep_story_ramp_pause_is_1_6(self):
        """SLEEP_STORY ramp specifically is 1.6 (extends pauses 60%)."""
        assert SLEEP_STORY.ramp_pause_end_scale == 1.6


class TestGuideFilesAndPrefixes:
    """Verify guide file and render prefix strings across all presets."""

    def test_meditation_guide_and_prefix(self):
        """MEDITATION guide and prefix are documented strings."""
        assert MEDITATION.guide_file == "docs/MEDITATION_GUIDE.md"
        assert MEDITATION.render_prefix == "meditation"

    def test_sleep_story_guide_and_prefix(self):
        """SLEEP_STORY guide and prefix are documented strings."""
        assert SLEEP_STORY.guide_file == "docs/SLEEP_STORY_GUIDE.md"
        assert SLEEP_STORY.render_prefix == "sleep_story"


class TestPresetImmutability:
    """Verify that presets are frozen and cannot be mutated."""

    def test_meditation_is_frozen(self):
        """MEDITATION is frozen; attempting mutation raises error."""
        with pytest.raises(AttributeError):
            MEDITATION.pause_scale = 3.0  # type: ignore

    def test_sleep_story_is_frozen(self):
        """SLEEP_STORY is frozen; attempting mutation raises error."""
        with pytest.raises(AttributeError):
            SLEEP_STORY.pause_scale = 2.0  # type: ignore
