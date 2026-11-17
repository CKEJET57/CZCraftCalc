from __future__ import annotations

import json
import sys
import types

from desktop.python import bridge


def test_character_search_validates_input_before_oauth():
    result = bridge._search_character({"name": "  ", "region": "RU"})

    assert result["ok"] is False
    assert result["error"]["code"] == "validation"


def test_stats_metadata_reads_local_database(tmp_path, monkeypatch):
    stats_file = tmp_path / "database" / "stats.json"
    stats_file.parent.mkdir(parents=True)
    stats_file.write_text(
        json.dumps([{"id": "kills", "category": "COMBAT"}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(bridge, "ROOT", tmp_path)

    result = bridge._stats_metadata()

    assert result == {
        "ok": True,
        "data": [{"id": "kills", "category": "COMBAT"}],
    }


def test_character_search_uses_existing_api_functions(monkeypatch):
    auth_module = types.ModuleType("api.auth")
    characters_module = types.ModuleType("api.characters")
    auth_module.fetch_token = lambda: {"access_token": "test-token"}
    characters_module.fetch_character_profile = (
        lambda token, region, name: {
            "username": name,
            "region": region,
            "token_received": token == "test-token",
        }
    )
    monkeypatch.setitem(sys.modules, "api.auth", auth_module)
    monkeypatch.setitem(sys.modules, "api.characters", characters_module)

    result = bridge._search_character({"name": "TestPlayer", "region": "ru"})

    assert result == {
        "ok": True,
        "data": {
            "username": "TestPlayer",
            "region": "RU",
            "token_received": True,
        },
    }


def test_dispatch_passes_nested_desktop_payload(monkeypatch):
    monkeypatch.setattr(
        bridge,
        "_desktop_api",
        lambda action, payload: {"action": action, "payload": payload},
    )

    result = bridge.dispatch({
        "action": "items",
        "payload": {"q": "Модекк", "craftable": True},
    })

    assert result == {
        "ok": True,
        "data": {
            "action": "items",
            "payload": {"q": "Модекк", "craftable": True},
        },
    }
