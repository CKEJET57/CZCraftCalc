from storage.listing import (
    build_item_index,
    extract_item_id,
    get_item_name,
)


def test_extract_item_id():
    assert extract_item_id({"data": "/items/other/qyvk.json"}) == "qyvk"
    assert extract_item_id({"data": "/items/misc/401j.json"}) == "401j"
    assert extract_item_id({}) is None
    assert extract_item_id({"data": None}) is None


def test_build_item_index():
    listing = [
        {"data": "/items/misc/401j.json"},
        {"data": "/items/misc/zzz.json"},
        {"data": None},  # пропускается
        {},              # пропускается
    ]
    idx = build_item_index(listing)
    assert set(idx) == {"401j", "zzz"}


def test_get_item_name_fallbacks():
    idx = {
        "a": {"name": {"lines": {"ru": "Ру", "en": "En"}}},
        "b": {"name": {"lines": {"en": "OnlyEn"}}},
        "c": {"name": {"key": "item.c.key", "lines": {}}},
    }
    assert get_item_name(idx, "a", "ru") == "Ру"
    assert get_item_name(idx, "a", "de") == "En"
    assert get_item_name(idx, "b", "ru") == "OnlyEn"
    assert get_item_name(idx, "c", "ru") == "item.c.key"
    assert get_item_name(idx, "nope", "ru") == "[неизвестный itemId: nope]"