import json

import ingest.common as common


def test_snapshot_skips_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "RAW", tmp_path)
    monkeypatch.setattr(common, "ROOT", tmp_path)
    assert common.snapshot("s", b"abc", "f.json") is not None
    assert common.snapshot("s", b"abc", "f.json") is None
    assert common.snapshot("s", b"abcd", "f.json") is not None
    entries = [json.loads(l) for l in (tmp_path / "s" / "manifest.jsonl").read_text().splitlines()]
    assert [e["changed"] for e in entries] == [True, False, True]


def test_registry_modules_importable():
    import importlib
    for sid, cfg in common.load_sources().items():
        mod = importlib.import_module(cfg["module"])
        assert mod.SOURCE_ID == sid
        assert callable(mod.run)
