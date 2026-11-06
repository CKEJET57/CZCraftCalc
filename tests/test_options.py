from types import SimpleNamespace

from core.options import AnalysisOptions


def test_menu_defaults():
    o = AnalysisOptions.menu_defaults()
    assert o.recursive is True
    assert o.no_history is True
    assert o.no_heartbeat is True
    assert o.max_requests == 2000


def test_from_args():
    args = SimpleNamespace(
        region="EU", lang="en", fee=10.0, recursive=True, max_depth=5,
        no_fallback=True, no_history=True, max_requests=100, workers=2,
        no_heartbeat=True, verbose=True, explain=True, explain_tree=True,
        ignore_missing=True, exclude="a,b", show_ids=True,
    )
    o = AnalysisOptions.from_args(args)
    assert o.region == "EU"
    assert o.fee == 10.0
    assert o.exclude == "a,b"
    assert o.recursive is True