"""Tests para la resiliencia de red y el decorador with_network_retry."""

from unittest.mock import patch
import ccxt
import pytest

from tradebot.exchange import with_network_retry


def test_retry_succeeds_after_transient_failure():
    calls = 0

    @with_network_retry(max_retries=3, initial_delay=0.01, jitter=False)
    def flaky_func():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ccxt.NetworkError("Connection timed out")
        return "success"

    result = flaky_func()
    assert result == "success"
    assert calls == 3


def test_retry_fails_after_max_retries():
    calls = 0

    @with_network_retry(max_retries=3, initial_delay=0.01, jitter=False)
    def always_failing():
        nonlocal calls
        calls += 1
        raise ccxt.RateLimitExceeded("Too many requests")

    with pytest.raises(ccxt.RateLimitExceeded):
        always_failing()

    assert calls == 3


def test_fatal_authentication_error_not_retried():
    calls = 0

    @with_network_retry(max_retries=3, initial_delay=0.01)
    def auth_failing():
        nonlocal calls
        calls += 1
        raise ccxt.AuthenticationError("Invalid API key")

    with pytest.raises(ccxt.AuthenticationError):
        auth_failing()

    assert calls == 1


def test_fatal_insufficient_funds_not_retried():
    calls = 0

    @with_network_retry(max_retries=3, initial_delay=0.01)
    def funds_failing():
        nonlocal calls
        calls += 1
        raise ccxt.InsufficientFunds("Balance too low")

    with pytest.raises(ccxt.InsufficientFunds):
        funds_failing()

    assert calls == 1


def test_fatal_invalid_order_not_retried():
    calls = 0

    @with_network_retry(max_retries=3, initial_delay=0.01)
    def order_failing():
        nonlocal calls
        calls += 1
        raise ccxt.InvalidOrder("Order size too small")

    with pytest.raises(ccxt.InvalidOrder):
        order_failing()

    assert calls == 1


def test_retry_decorator_without_parentheses():
    calls = 0

    @with_network_retry
    def simple_func():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("Socket reset")
        return "ok"

    with patch("time.sleep", return_value=None):
        result = simple_func()
    assert result == "ok"
    assert calls == 2
