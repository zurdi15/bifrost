from app.metrics.store import MetricsStore


def make_store(tmp_path) -> MetricsStore:
    store = MetricsStore(tmp_path / "metrics.db", retention={"raw": 100, "1m": 200, "1h": 300})
    store._open_sync()
    return store


def insert(store: MetricsStore, node_id: int, name: str, points: list[tuple[int, float]]):
    rows = [(node_id, store._intern_sync(name), ts, value) for ts, value in points]
    store._flush_sync(rows)


def test_downsample_raw_to_1m(tmp_path):
    store = make_store(tmp_path)
    base = 6000  # minute-aligned
    insert(store, 1, "cpu.pct", [(base + 0, 10.0), (base + 10, 20.0), (base + 50, 60.0)])
    insert(store, 1, "cpu.pct", [(base + 60, 100.0)])  # next minute

    # now is far enough past both minutes (lag window) to close them.
    store.downsample_once_sync(now=base + 300)
    _, series = store.query_sync(1, ["cpu.pct"], 0, 10_000, res="1m")
    rows = series["cpu.pct"]
    assert rows[0] == [base, 30.0, 10.0, 60.0]  # avg/min/max of the first minute
    assert rows[1][0] == base + 60

    # Idempotent: running again must not duplicate or change anything.
    store.downsample_once_sync(now=base + 300)
    _, series2 = store.query_sync(1, ["cpu.pct"], 0, 10_000, res="1m")
    assert series2["cpu.pct"] == rows


def test_downsample_1m_to_1h_weighted(tmp_path):
    store = make_store(tmp_path)
    base = 3600 * 10
    # Two raw points in minute 0 (avg 10), one in minute 1 (avg 40):
    insert(store, 1, "mem.pct", [(base, 5.0), (base + 30, 15.0), (base + 60, 40.0)])
    store.downsample_once_sync(now=base + 3600 + 200)
    _, series = store.query_sync(1, ["mem.pct"], 0, base + 3600, res="1h")
    ts, avg, minimum, maximum = series["mem.pct"][0]
    assert ts == base
    # Weighted by sample count: (5+15+40)/3 = 20, not (10+40)/2 = 25.
    assert avg == 20.0
    assert (minimum, maximum) == (5.0, 40.0)


def test_retention_deletes_old_rows(tmp_path):
    store = make_store(tmp_path)
    now = 1_000_000
    insert(store, 1, "cpu.pct", [(now - 99, 1.0), (now - 150, 2.0)])
    store.apply_retention_sync(now=now)  # raw retention = 100s
    _, series = store.query_sync(1, ["cpu.pct"], 0, now, res="raw")
    assert [row[1] for row in series["cpu.pct"]] == [1.0]


def test_auto_resolution_selection():
    assert MetricsStore.pick_resolution(0, 3600) == "raw"
    assert MetricsStore.pick_resolution(0, 6 * 3600) == "raw"
    assert MetricsStore.pick_resolution(0, 24 * 3600) == "1m"
    assert MetricsStore.pick_resolution(0, 14 * 86400) == "1m"
    assert MetricsStore.pick_resolution(0, 30 * 86400) == "1h"


def test_unknown_metric_returns_empty(tmp_path):
    store = make_store(tmp_path)
    _, series = store.query_sync(1, ["nope"], 0, 100, res="raw")
    assert series["nope"] == []
