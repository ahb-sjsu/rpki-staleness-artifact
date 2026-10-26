#!/usr/bin/env python3
"""Exploratory, written after grading in answer to review (2026-10-26).
Not part of PREREG-RPKI-ROV-STALENESS; the sealed verdict stands as graded.

From the eight graded unit records alone, recompute the bar statistics
(B1 and B2 gains in standard errors, the B3 ratio and its bootstrap upper
bound with the grader's seed, the B4 gain) with:

- each reference day left out in turn;
- the largest wrong-accept holder (HGC, AS9304) removed from every day;
- the planted APNIC experiment block (203.147.108.0/23) removed;

and report the clock offset of each current list from the RIB time.

    python analysis/rpki/rov_sensitivity.py GRADED_DIR [OUT.json]
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_sealed_rov import B3_RATIO, BOOT, SEED, SE_BAR, _increasing, _paired  # noqa: E402
from rov_unit import DAILY_DELTAS, SUBDAY_DELTAS  # noqa: E402


def _rates(u: dict, arm: str, lab: str, drop_origin=None, drop_pair=None) -> tuple[float, float]:
    """(e_accept, e_drop) with the chosen wrong accepts taken out. Wrong
    drops are not listed per route in the graded record, so only accepts
    are filtered; e_drop is unchanged."""
    r = u[arm][lab]
    k = sum(1 for f in r["accept_flips"]
            if (drop_origin is not None and f[1] == drop_origin)
            or (drop_pair is not None and (f[0], f[1]) == drop_pair))
    return (r["accept"] - k) / u["n"], r["e_drop"]


def stats(units: list[dict], **flt) -> dict:
    acc = {d: np.array([_rates(u, "daily", str(d), **flt)[0] for u in units]) for d in DAILY_DELTAS}
    drp = {d: np.array([_rates(u, "daily", str(d), **flt)[1] for u in units]) for d in DAILY_DELTAS}
    out = {}
    for name, s in (("B1", acc), ("B2", drp)):
        means = [float(s[d].mean()) for d in DAILY_DELTAS]
        gain, se = _paired(s[1], s[30])
        out[name] = {"z": gain / se, "pass": _increasing(means, True) and gain > SE_BAR * se}
    rng = np.random.default_rng(SEED)
    k, ratios = len(units), []
    for _ in range(BOOT):
        idx = rng.integers(0, k, k)
        m30 = acc[30][idx].mean()
        ratios.append(acc[1][idx].mean() / m30 if m30 > 0 else np.inf)
    up = float(np.percentile(ratios, 95))
    out["B3"] = {"point": float(acc[1].mean() / acc[30].mean()), "upper": up, "pass": up <= B3_RATIO}
    sub = {lab: np.array([_rates(u, "subday", lab, **flt)[0] for u in units]) for lab in SUBDAY_DELTAS}
    smeans = [float(sub[lab].mean()) for lab in SUBDAY_DELTAS]
    sg, sse = _paired(sub["1h"], sub["1d"])
    out["B4"] = {"z": sg / sse if sse else float("inf"),
                 "pass": _increasing(smeans, False) and sg > SE_BAR * sse}
    return out


def offsets(units: list[dict]) -> dict:
    """Hours from the RIB time (T0 00:00 UTC) to each current list."""
    lm = lambda s: datetime.strptime(s, "%a, %d %b %Y %H:%M:%S %Z")  # noqa: E731
    daily, snap = [], []
    for u in units:
        t0 = datetime.fromisoformat(u["t0"])
        for k, v in u["daily_fresh"]["per_ta"].items():
            if k.endswith("_last_modified"):
                daily.append((lm(v) - t0).total_seconds() / 3600)
        ts = re.search(r"rpki-(\d{8}T\d{6})Z", u["subday_fresh"]["snapshot"]).group(1)
        snap.append((datetime.strptime(ts, "%Y%m%dT%H%M%S") - t0).total_seconds() / 3600)
    return {"daily_current_hours_after_rib": [min(daily), max(daily)],
            "snapshot_current_hours_after_rib": [min(snap), max(snap)]}


def main(graded: Path, dest: Path | None) -> int:
    units = [json.loads(p.read_text()) for p in sorted(graded.glob("rov-unit-*.json"))]
    out = {"exploratory": True, "all": stats(units), "leave_one_out": {},
           "without_AS9304": stats(units, drop_origin=9304),
           "without_TUI_block": stats(units, drop_pair=("203.147.108.0/23", 24021)),
           "offsets": offsets(units)}
    for i, u in enumerate(units):
        out["leave_one_out"][u["t0"]] = stats(units[:i] + units[i + 1:])
    for key in ("all", "without_AS9304", "without_TUI_block"):
        s = out[key]
        print(f"{key:>18}: B1 {s['B1']['z']:.1f} B2 {s['B2']['z']:.1f} "
              f"B3 {s['B3']['point']:.4f}/{s['B3']['upper']:.4f} B4 {s['B4']['z']:.1f}")
    for t0, s in out["leave_one_out"].items():
        print(f"   without {t0}: B1 {s['B1']['z']:.1f} B2 {s['B2']['z']:.1f} "
              f"B3 {s['B3']['point']:.4f}/{s['B3']['upper']:.4f} B4 {s['B4']['z']:.1f}")
    print(out["offsets"])
    if dest:
        dest.write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None))
