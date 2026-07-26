#!/usr/bin/env python3
"""Track LiPo pack health across charge cycles.

Packs rarely fail suddenly. Internal resistance creeps up and delivered
capacity creeps down over dozens of cycles, and the pack that sags mid-throttle
was measurably worse a month earlier. This logs each cycle and flags packs whose
IR has risen or whose capacity has faded past a threshold.

Storage is a single JSON file, so the log is greppable and diffable.
"""
from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

DEFAULT_STORE = Path.home() / ".lipo" / "packs.json"

IR_WARN_PCT = 30.0        # IR rise over baseline before a warning
IR_RETIRE_PCT = 60.0      # IR rise over baseline before retirement advice
FADE_WARN_PCT = 15.0      # capacity fade before a warning
FADE_RETIRE_PCT = 25.0
STORAGE_V_PER_CELL = 3.85


@dataclass
class Cycle:
    when: str                 # ISO date
    charged_mah: int          # mAh put back in on the charge
    ir_mohm: float | None = None   # per-pack internal resistance
    notes: str = ""


@dataclass
class Pack:
    pack_id: str
    cells: int
    capacity_mah: int
    chemistry: str = "LiPo"
    acquired: str = field(default_factory=lambda: date.today().isoformat())
    cycles: list[Cycle] = field(default_factory=list)
    retired: bool = False

    # ------------------------------------------------------------- derived
    @property
    def cycle_count(self) -> int:
        return len(self.cycles)

    @property
    def nominal_v(self) -> float:
        return self.cells * 3.7

    @property
    def storage_v(self) -> float:
        return round(self.cells * STORAGE_V_PER_CELL, 2)

    def _ir_series(self) -> list[float]:
        return [c.ir_mohm for c in self.cycles if c.ir_mohm is not None]

    @property
    def baseline_ir(self) -> float | None:
        """Median IR of the first three measured cycles."""
        series = self._ir_series()
        return statistics.median(series[:3]) if series else None

    @property
    def current_ir(self) -> float | None:
        """Median IR of the last three measured cycles, to damp noise."""
        series = self._ir_series()
        return statistics.median(series[-3:]) if series else None

    @property
    def ir_rise_pct(self) -> float | None:
        base, now = self.baseline_ir, self.current_ir
        if base is None or now is None or base == 0:
            return None
        return (now - base) / base * 100

    @property
    def baseline_capacity(self) -> float | None:
        vals = [c.charged_mah for c in self.cycles]
        return statistics.median(vals[:3]) if vals else None

    @property
    def current_capacity(self) -> float | None:
        vals = [c.charged_mah for c in self.cycles]
        return statistics.median(vals[-3:]) if vals else None

    @property
    def fade_pct(self) -> float | None:
        base, now = self.baseline_capacity, self.current_capacity
        if base is None or now is None or base == 0:
            return None
        return max(0.0, (base - now) / base * 100)

    def health(self) -> tuple[str, list[str]]:
        """Returns (status, reasons). Status is ok | watch | retire."""
        reasons: list[str] = []
        status = "ok"

        rise = self.ir_rise_pct
        if rise is not None:
            if rise >= IR_RETIRE_PCT:
                status = "retire"
                reasons.append(f"internal resistance up {rise:.0f}% from baseline")
            elif rise >= IR_WARN_PCT:
                status = "watch"
                reasons.append(f"internal resistance up {rise:.0f}%")

        fade = self.fade_pct
        if fade is not None:
            if fade >= FADE_RETIRE_PCT:
                status = "retire"
                reasons.append(f"capacity down {fade:.0f}%")
            elif fade >= FADE_WARN_PCT and status != "retire":
                status = "watch"
                reasons.append(f"capacity down {fade:.0f}%")

        if self.retired:
            return "retired", reasons or ["marked retired by hand"]
        return status, reasons


# ------------------------------------------------------------------- store

def load(path: Path) -> dict[str, Pack]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        pid: Pack(**{**data, "cycles": [Cycle(**c) for c in data.get("cycles", [])]})
        for pid, data in raw.items()
    }


def save(packs: dict[str, Pack], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({pid: asdict(p) for pid, p in packs.items()}, indent=2),
        encoding="utf-8",
    )


# -------------------------------------------------------------------- CLI

def cmd_add(args, packs, path) -> None:
    if args.pack_id in packs:
        raise SystemExit(f"{args.pack_id}: already exists")
    packs[args.pack_id] = Pack(args.pack_id, args.cells, args.capacity)
    save(packs, path)
    p = packs[args.pack_id]
    print(f"added {p.pack_id}: {p.cells}S {p.capacity_mah}mAh, storage {p.storage_v}V")


def cmd_log(args, packs, path) -> None:
    if args.pack_id not in packs:
        raise SystemExit(f"{args.pack_id}: unknown pack")
    pack = packs[args.pack_id]
    when = args.date or date.today().isoformat()
    datetime.strptime(when, "%Y-%m-%d")  # validate
    pack.cycles.append(Cycle(when, args.charged, args.ir, args.notes or ""))
    save(packs, path)

    status, reasons = pack.health()
    print(f"{pack.pack_id}: cycle {pack.cycle_count} logged, status {status}")
    for r in reasons:
        print(f"  - {r}")


def cmd_list(args, packs, path) -> None:
    if not packs:
        print("no packs yet. add one with:  lipo.py add PACK_ID --cells 4 --capacity 1300")
        return
    print(f"\n  {'pack':<12} {'spec':<12} {'cyc':>4} {'IR':>8} {'fade':>7}  status")
    print("  " + "-" * 56)
    for pack in packs.values():
        status, reasons = pack.health()
        rise = pack.ir_rise_pct
        fade = pack.fade_pct
        spec = f"{pack.cells}S {pack.capacity_mah}"
        print(
            f"  {pack.pack_id:<12} {spec:<12} {pack.cycle_count:>4} "
            f"{(f'{rise:+.0f}%' if rise is not None else '-'):>8} "
            f"{(f'{fade:.0f}%' if fade is not None else '-'):>7}  {status}"
        )
        for r in reasons:
            print(f"  {'':<12} {'':<12} {'':>4} {'':>8} {'':>7}  {r}")
    print()


def cmd_show(args, packs, path) -> None:
    if args.pack_id not in packs:
        raise SystemExit(f"{args.pack_id}: unknown pack")
    pack = packs[args.pack_id]
    status, reasons = pack.health()
    print(f"\n{pack.pack_id}  {pack.cells}S {pack.capacity_mah}mAh  acquired {pack.acquired}")
    print(f"  storage voltage   {pack.storage_v} V ({STORAGE_V_PER_CELL} V/cell)")
    print(f"  cycles            {pack.cycle_count}")
    if pack.baseline_ir is not None:
        print(f"  IR baseline       {pack.baseline_ir:.1f} mOhm")
        print(f"  IR now            {pack.current_ir:.1f} mOhm  ({pack.ir_rise_pct:+.0f}%)")
    if pack.baseline_capacity is not None:
        print(f"  charge baseline   {pack.baseline_capacity:.0f} mAh")
        print(f"  charge now        {pack.current_capacity:.0f} mAh  (fade {pack.fade_pct:.0f}%)")
    print(f"  status            {status}")
    for r in reasons:
        print(f"                    {r}")

    if pack.cycles:
        print(f"\n  {'date':<12} {'mAh':>6} {'IR':>7}  notes")
        for c in pack.cycles[-12:]:
            ir = f"{c.ir_mohm:.1f}" if c.ir_mohm is not None else "-"
            print(f"  {c.when:<12} {c.charged_mah:>6} {ir:>7}  {c.notes}")
    print()


def main() -> None:
    p = argparse.ArgumentParser(description="LiPo pack health tracker.")
    p.add_argument("--store", type=Path, default=DEFAULT_STORE)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="register a new pack")
    a.add_argument("pack_id")
    a.add_argument("--cells", type=int, required=True)
    a.add_argument("--capacity", type=int, required=True, help="rated mAh")
    a.set_defaults(fn=cmd_add)

    l = sub.add_parser("log", help="log a charge cycle")
    l.add_argument("pack_id")
    l.add_argument("--charged", type=int, required=True, help="mAh put back in")
    l.add_argument("--ir", type=float, default=None, help="internal resistance, mOhm")
    l.add_argument("--date", default=None, help="YYYY-MM-DD, defaults to today")
    l.add_argument("--notes", default="")
    l.set_defaults(fn=cmd_log)

    ls = sub.add_parser("list", help="show every pack")
    ls.set_defaults(fn=cmd_list)

    s = sub.add_parser("show", help="detail for one pack")
    s.add_argument("pack_id")
    s.set_defaults(fn=cmd_show)

    args = p.parse_args()
    args.fn(args, load(args.store), args.store)


if __name__ == "__main__":
    main()
