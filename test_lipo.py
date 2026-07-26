import json

from lipo import Cycle, Pack, load, save


def pack_with(irs=(), mahs=()):
    p = Pack("test", cells=4, capacity_mah=1300)
    n = max(len(irs), len(mahs))
    for i in range(n):
        p.cycles.append(
            Cycle(f"2026-01-{i + 1:02d}",
                  charged_mah=mahs[i] if i < len(mahs) else 1200,
                  ir_mohm=irs[i] if i < len(irs) else None)
        )
    return p


def test_new_pack_is_healthy():
    assert Pack("a", 4, 1300).health()[0] == "ok"


def test_storage_voltage():
    assert Pack("a", 4, 1300).storage_v == 15.4
    assert Pack("b", 6, 1050).storage_v == 23.1


def test_baseline_uses_first_three_cycles():
    p = pack_with(irs=(10, 12, 11, 30, 30, 30))
    assert p.baseline_ir == 11


def test_current_uses_last_three_cycles():
    p = pack_with(irs=(10, 10, 10, 20, 22, 21))
    assert p.current_ir == 21


def test_ir_rise_detected():
    p = pack_with(irs=(10, 10, 10, 14, 14, 14))
    assert p.ir_rise_pct == 40.0
    assert p.health()[0] == "watch"


def test_severe_ir_rise_recommends_retirement():
    p = pack_with(irs=(10, 10, 10, 18, 18, 18))
    assert p.health()[0] == "retire"


def test_capacity_fade_detected():
    p = pack_with(mahs=(1200, 1200, 1200, 1000, 1000, 1000))
    assert round(p.fade_pct) == 17
    assert p.health()[0] == "watch"


def test_capacity_gain_is_not_negative_fade():
    p = pack_with(mahs=(1000, 1000, 1000, 1200, 1200, 1200))
    assert p.fade_pct == 0.0


def test_ir_optional():
    p = pack_with(mahs=(1200, 1200, 1200))
    assert p.ir_rise_pct is None
    assert p.health()[0] == "ok"


def test_manual_retirement_wins():
    p = Pack("a", 4, 1300)
    p.retired = True
    assert p.health()[0] == "retired"


def test_roundtrip_through_json(tmp_path):
    store = tmp_path / "packs.json"
    original = {"p1": pack_with(irs=(9, 9, 9), mahs=(1250, 1240, 1245))}
    save(original, store)
    restored = load(store)
    assert restored["p1"].cycle_count == 3
    assert restored["p1"].baseline_ir == 9
    assert json.loads(store.read_text())["p1"]["cells"] == 4


def test_missing_store_returns_empty(tmp_path):
    assert load(tmp_path / "nope.json") == {}
