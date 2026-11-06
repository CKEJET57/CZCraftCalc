from unittest.mock import Mock

import pytest

from api.errors import ApiAuthError, ApiRateLimitError
from services.price import PriceService


def _resp(status: int = 200, data: dict | None = None) -> Mock:
    r = Mock()
    r.status_code = status
    r.text = ""
    r.headers = {}
    r.json = Mock(return_value=data or {})
    return r


def test_history_median_basic(make_price_service):
    ps = make_price_service(use_history=True, fallback_to_lots=False)
    ps._session = Mock()
    # 10 сделок с unit-ценой 100
    deals = [{"price": 100 * (i + 1), "amount": i + 1} for i in range(10)]
    ps._session.get = Mock(return_value=_resp(200, {"prices": deals}))

    info = ps.get("x")
    assert info.source == "history"
    assert info.unit_price == 100.0


def test_history_below_min_samples_falls_to_lots(make_price_service):
    ps = make_price_service(
        use_history=True, fallback_to_lots=True, min_samples=5
    )
    ps._session = Mock()

    history_resp = _resp(200, {"prices": [{"price": 100, "amount": 1}] * 3})
    lots_resp = _resp(200, {"lots": [
        {"amount": 1, "buyoutPrice": 50},
        {"amount": 2, "buyoutPrice": 120},  # unit 60
    ]})
    ps._session.get = Mock(side_effect=[history_resp, lots_resp])

    info = ps.get("x")
    assert info.source == "lots"
    assert info.unit_price == 50.0  # min(buyout/amount)


def test_no_fallback(make_price_service):
    ps = make_price_service(
        use_history=True, fallback_to_lots=False, min_samples=5
    )
    ps._session = Mock()
    ps._session.get = Mock(return_value=_resp(200, {"prices": []}))

    info = ps.get("x")
    assert info.source == "none"
    assert info.unit_price is None


def test_budget_exhausted(make_price_service):
    ps = make_price_service(max_requests=0)
    ps._session = Mock()
    ps._session.get = Mock(side_effect=AssertionError("не должен вызваться"))

    info = ps.get("x")
    assert info.source == "none"
    assert info.unit_price is None


def test_cache_hit(make_price_service):
    ps = make_price_service(use_history=True, fallback_to_lots=False)
    ps._session = Mock()
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        return _resp(200, {"prices": [{"price": 100, "amount": 1}] * 10})

    ps._session.get = fake_get
    ps.get("x")
    ps.get("x")
    assert calls["n"] == 1


def test_api_401_raises_auth_error(make_price_service):
    ps = make_price_service()
    ps._session = Mock()
    ps._session.get = Mock(return_value=_resp(401, {}))

    with pytest.raises(ApiAuthError, match="401"):
        ps.get_history("x")


def test_retry_after_is_not_shortened(make_price_service):
    ps = make_price_service(max_retry_delay=5)
    response = _resp(429, {})
    response.headers["Retry-After"] = "45"

    assert ps._retry_delay(0, response) == 45.0


def test_429_retries_and_honors_retry_after(make_price_service, monkeypatch):
    ps = make_price_service(max_retries=2, retry_backoff=0)
    ps._session = Mock()
    limited = _resp(429, {})
    limited.headers["Retry-After"] = "0"
    ok = _resp(200, {"prices": [{"price": 100, "amount": 1}]})
    ps._session.get = Mock(side_effect=[limited, ok])
    sleeps = []
    monkeypatch.setattr("services.price.time.sleep", lambda delay: sleeps.append(delay))

    result = ps.get_history("x")

    assert len(result) == 1
    assert ps._session.get.call_count == 2
    assert sleeps == [0.0]


def test_429_raises_after_retries(make_price_service, monkeypatch):
    ps = make_price_service(max_retries=2, retry_backoff=0)
    ps._session = Mock()
    limited = _resp(429, {})
    limited.headers["Retry-After"] = "0"
    ps._session.get = Mock(return_value=limited)
    monkeypatch.setattr("services.price.time.sleep", lambda delay: None)

    with pytest.raises(ApiRateLimitError, match="429"):
        ps.get_history("x")

    assert ps._session.get.call_count == 2


def test_5xx_retries_before_returning_success(make_price_service, monkeypatch):
    ps = make_price_service(max_retries=2, retry_backoff=0)
    ps._session = Mock()
    ok = _resp(200, {"prices": [{"price": 100, "amount": 1}]})
    ps._session.get = Mock(side_effect=[_resp(503, {}), ok])
    sleeps = []
    monkeypatch.setattr("services.price.time.sleep", lambda delay: sleeps.append(delay))

    result = ps.get_history("x")

    assert len(result) == 1
    assert ps._session.get.call_count == 2
    assert sleeps == [0.0]


def test_prefetch_propagates_rate_limit_error(make_price_service):
    ps = make_price_service(max_retries=1)
    ps._session = Mock()
    ps._session.get = Mock(return_value=_resp(429, {}))

    with pytest.raises(ApiRateLimitError, match="429"):
        ps.prefetch(["x"], workers=1)


def test_close_closes_http_session(make_price_service):
    ps = make_price_service()
    session = Mock()
    ps._session = session

    ps.close()
    ps.close()

    session.close.assert_called_once()


def test_get_history_parses_response(make_price_service):
    ps = make_price_service()
    ps._session = Mock()
    ps._session.get = Mock(return_value=_resp(200, {
        "prices": [{"price": 100, "amount": 2, "time": "2024-01-01"}]
    }))
    result = ps.get_history("x")
    assert len(result) == 1
    assert result[0]["price"] == 100


def test_get_history_handles_error(make_price_service):
    ps = make_price_service()
    ps._session = Mock()
    ps._session.get = Mock(return_value=_resp(500, {}))
    assert ps.get_history("x") == []


def test_get_lots_parses_response(make_price_service):
    ps = make_price_service()
    ps._session = Mock()
    ps._session.get = Mock(return_value=_resp(200, {
        "total": 5,
        "lots": [{"amount": 2, "buyoutPrice": 100}],
    }))
    result = ps.get_lots("x")
    assert result["total"] == 5
    assert len(result["lots"]) == 1


def test_prefetch_deduplicates(make_price_service):
    ps = make_price_service(use_history=True, fallback_to_lots=False)
    ps._session = Mock()
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        return _resp(200, {"prices": [{"price": 100, "amount": 1}] * 10})

    ps._session.get = fake_get
    ps.prefetch(["a", "a", "a", "b"])
    assert calls["n"] == 2  # только 2 уникальных