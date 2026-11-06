import json

import storage.exclusions as ex_mod


def test_load_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ex_mod, "EXCLUSIONS_FILE", tmp_path / "none.json")
    assert ex_mod.load_exclusions() == set()


def test_roundtrip(tmp_path, monkeypatch):
    p = tmp_path / "e.json"
    monkeypatch.setattr(ex_mod, "EXCLUSIONS_FILE", p)

    assert ex_mod.add_exclusions({"a", "b"}) == {"a", "b"}
    assert ex_mod.load_exclusions() == {"a", "b"}

    assert ex_mod.remove_exclusions({"a"}) == {"b"}
    assert ex_mod.load_exclusions() == {"b"}

    ex_mod.clear_exclusions()
    assert ex_mod.load_exclusions() == set()


def test_corrupted_file(tmp_path, monkeypatch):
    p = tmp_path / "e.json"
    p.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(ex_mod, "EXCLUSIONS_FILE", p)
    assert ex_mod.load_exclusions() == set()


def test_plain_list_format(tmp_path, monkeypatch):
    p = tmp_path / "e.json"
    p.write_text(json.dumps(["a", "b"]), encoding="utf-8")
    monkeypatch.setattr(ex_mod, "EXCLUSIONS_FILE", p)
    assert ex_mod.load_exclusions() == {"a", "b"}


def test_dict_format(tmp_path, monkeypatch):
    p = tmp_path / "e.json"
    p.write_text(json.dumps({"items": ["x", "y"]}), encoding="utf-8")
    monkeypatch.setattr(ex_mod, "EXCLUSIONS_FILE", p)
    assert ex_mod.load_exclusions() == {"x", "y"}