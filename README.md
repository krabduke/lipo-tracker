# lipo-tracker

Packs rarely fail suddenly. Internal resistance creeps up and delivered
capacity creeps down over dozens of cycles, and the pack that sags mid-throttle
was measurably worse a month earlier. This logs each cycle and flags the pack
before it puts a quad in a field.

```
$ python3 lipo.py log gnb-1300-a --charged 1035 --ir 16.1
gnb-1300-a: cycle 6 logged, status retire
  - internal resistance up 66% from baseline

$ python3 lipo.py show gnb-1300-a

gnb-1300-a  4S 1300mAh  acquired 2026-01-01
  storage voltage   15.4 V (3.85 V/cell)
  cycles            6
  IR baseline       9.5 mOhm
  IR now            15.8 mOhm  (+66%)
  charge baseline   1240 mAh
  charge now        1040 mAh  (fade 16%)
  status            retire
```

## How the thresholds work

Baseline is the **median of the first three** measured cycles; current is the
median of the **last three**. Medians rather than single readings, because IR
meters are noisy and one bad measurement should not retire a good pack.

| signal | watch | retire |
|---|---|---|
| IR rise over baseline | 30% | 60% |
| capacity fade | 15% | 25% |

Thresholds are module constants. Adjust them to taste.

## Usage

```
python3 lipo.py add gnb-1300-a --cells 4 --capacity 1300
python3 lipo.py log gnb-1300-a --charged 1240 --ir 9.5 --notes "cold day"
python3 lipo.py list
python3 lipo.py show gnb-1300-a
```

Storage is a single JSON file at `~/.lipo/packs.json`, so the log is greppable
and diffable. Override with `--store`.

Stdlib only. Tests: `python3 -m pytest test_lipo.py`

## Not handled

Per-cell voltages. Cell divergence is the other main failure mode and would be
the obvious next addition.
