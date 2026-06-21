"""Tests for the _with_retries helper in meditation_mixer.tts.

Validates retry/backoff logic: transient failures retry, client errors
(4xx) fail immediately, and success-on-first-try returns without delay.
"""
import pytest

from meditation_mixer.tts import _with_retries


class _ApiError(Exception):
    """Fake exception with a status_code attribute for testing."""

    def __init__(self, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(f"status={status_code}")


class TestWithRetriesSuccess:
    """fn succeeds on the first call."""

    def test_returns_value(self, monkeypatch):
        monkeypatch.setattr("meditation_mixer.tts.time.sleep", lambda _: None)
        calls = []

        def fn():
            calls.append(1)
            return "ok"

        assert _with_retries(fn) == "ok"
        assert len(calls) == 1


class TestWithRetriesTransientThenSuccess:
    """Transient failures (no status_code) retry and eventually succeed."""

    def test_succeeds_after_transient(self, monkeypatch):
        monkeypatch.setattr("meditation_mixer.tts.time.sleep", lambda _: None)
        calls = []

        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("connection reset")
            return "recovered"

        assert _with_retries(fn) == "recovered"
        assert len(calls) == 3


class TestWithRetriesClientError:
    """HTTP 4xx (client error) raises immediately without retry."""

    def test_no_retry_on_400(self, monkeypatch):
        monkeypatch.setattr("meditation_mixer.tts.time.sleep", lambda _: None)
        calls = []

        def fn():
            calls.append(1)
            raise _ApiError(status_code=400)

        with pytest.raises(_ApiError):
            _with_retries(fn)
        assert len(calls) == 1

    def test_no_retry_on_422(self, monkeypatch):
        monkeypatch.setattr("meditation_mixer.tts.time.sleep", lambda _: None)
        calls = []

        def fn():
            calls.append(1)
            raise _ApiError(status_code=422)

        with pytest.raises(_ApiError):
            _with_retries(fn)
        assert len(calls) == 1


class TestWithRetriesExhausted:
    """All attempts fail with a transient error — raises after N attempts."""

    def test_raises_after_attempts(self, monkeypatch):
        monkeypatch.setattr("meditation_mixer.tts.time.sleep", lambda _: None)
        calls = []

        def fn():
            calls.append(1)
            raise _ApiError(status_code=502)

        with pytest.raises(_ApiError):
            _with_retries(fn, attempts=4)
        assert len(calls) == 4

    def test_raises_network_error_after_attempts(self, monkeypatch):
        monkeypatch.setattr("meditation_mixer.tts.time.sleep", lambda _: None)
        calls = []

        def fn():
            calls.append(1)
            raise OSError("network timeout")

        with pytest.raises(OSError):
            _with_retries(fn, attempts=3)
        assert len(calls) == 3


class TestWithRetriesBackoff:
    """Verify exponential backoff delays."""

    def test_delays_are_exponential(self, monkeypatch):
        delays = []
        monkeypatch.setattr("meditation_mixer.tts.time.sleep", lambda d: delays.append(d))
        calls = []

        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise _ApiError(status_code=500)
            return "done"

        _with_retries(fn, base_delay=2.0)
        assert delays == [2.0, 4.0]
