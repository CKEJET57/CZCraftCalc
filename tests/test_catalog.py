from __future__ import annotations

from services.catalog import _get_text, _parse_blocks, health


def test_catalog_text_parser_resolves_language_fallbacks():
    assert _get_text({"lines": {"ru": "Название", "en": "Name"}}, "en") == "Name"
    assert _get_text({"lines": {"ru": "Название"}}, "de") == "Название"


def test_catalog_parser_preserves_supported_info_block_shapes():
    parsed = _parse_blocks({
        "infoBlocks": [
            {"type": "text", "title": {"ru": "Описание"}, "text": {"ru": "Первая\\nВторая"}},
            {"type": "list", "title": {"ru": "Параметры"}, "elements": [
                {"type": "numeric", "name": {"ru": "Урон"}, "value": 10},
                {"type": "text", "text": {"ru": "Дополнительно"}},
            ]},
        ]
    }, "ru")

    assert parsed[0] == {
        "type": "text", "title": "Описание", "text": "Первая\nВторая",
    }
    assert parsed[1]["type"] == "list"
    assert parsed[1]["elements"][0]["name"] == "Урон"
    assert parsed[1]["elements"][1]["value"] == "Дополнительно"


def test_catalog_health_contract():
    assert health() == {"ok": True}
