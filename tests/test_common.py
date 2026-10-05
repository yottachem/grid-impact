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


def test_snapshot_multi_file_source(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "RAW", tmp_path)
    monkeypatch.setattr(common, "ROOT", tmp_path)
    for _ in range(2):
        written = [common.snapshot("s", body, name) for name, body in [("a.parquet", b"1"), ("b.parquet", b"2")]]
    assert written == [None, None]


def test_registry_modules_importable():
    import importlib
    for sid, cfg in common.load_sources().items():
        mod = importlib.import_module(cfg["module"])
        assert mod.SOURCE_ID == sid
        assert callable(mod.run)


def test_transient_vs_real_failures():
    import requests

    from ingest.run import _is_transient

    def http_error(code):
        resp = requests.Response()
        resp.status_code = code
        return requests.HTTPError(response=resp)

    assert _is_transient(http_error(504))
    assert _is_transient(http_error(429))
    assert _is_transient(requests.Timeout())
    assert not _is_transient(http_error(403))  # bad API key must fail loudly
    assert not _is_transient(ValueError("schema changed"))
