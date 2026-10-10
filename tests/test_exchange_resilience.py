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


KUCOIN_429 = 'kucoin {"code":"429000","msg":"Too many requests. System-level rate limit exceeded."}'


def test_kucoin_429000_is_retried_although_ccxt_raises_a_generic_error():
    calls = 0

    @with_network_retry(max_retries=3, initial_delay=0.01, jitter=False)
    def throttled_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ccxt.ExchangeError(KUCOIN_429)      # ccxt no lo reconoce como RateLimitExceeded
        return "ok"

    assert throttled_once() == "ok"
    assert calls == 2


def test_other_exchange_errors_are_not_retried():
    calls = 0

    @with_network_retry(max_retries=3, initial_delay=0.01)
    def broken():
        nonlocal calls
        calls += 1
        raise ccxt.ExchangeError('kucoin {"code":"400100","msg":"Parameter error"}')

    with pytest.raises(ccxt.ExchangeError):
        broken()
    assert calls == 1


def test_is_rate_limited():
    from tradebot.exchange import is_rate_limited

    assert is_rate_limited(ccxt.ExchangeError(KUCOIN_429))
    assert is_rate_limited(Exception("429 Client Error: Too Many Requests for url: https://api.kucoin.com"))
    assert not is_rate_limited(ccxt.ExchangeError("kucoin Parameter error"))
