from unittest.mock import Mock

import pytest

import api.auth as auth_mod


def test_retry_on_5xx(monkeypatch):
    auth_mod._session = None
    attempts = {"n": 0}

    def fake_post(*a, **k):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return Mock(status_code=503, text="err")
        return Mock(
            status_code=200,
            text="",
            json=Mock(return_value={"access_token": "tok", "expires_in": 3600}),
        )

    fake_session = Mock()
    fake_session.post = fake_post

    monkeypatch.setattr(auth_mod, "_get_session", lambda: fake_session)
    monkeypatch.setattr(auth_mod.time, "sleep", lambda s: None)

    result = auth_mod.fetch_token(max_retries=3)
    assert result["access_token"] == "tok"
    assert attempts["n"] == 3
    auth_mod._session = None


def test_no_retry_on_401(monkeypatch):
    auth_mod._session = None
    r = Mock(status_code=401, text="unauthorized", json=Mock(return_value={}))
    fake_session = Mock()
    fake_session.post = Mock(return_value=r)

    monkeypatch.setattr(auth_mod, "_get_session", lambda: fake_session)
    monkeypatch.setattr(auth_mod.time, "sleep", lambda s: None)

    with pytest.raises(RuntimeError, match="401"):
        auth_mod.fetch_token()
    auth_mod._session = None