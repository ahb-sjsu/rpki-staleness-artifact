#!/usr/bin/env python3
"""Exploratory, written after grading in answer to review (2026-10-26).
Not part of PREREG-RPKI-ROV-STALENESS and grades nothing.

Persistence records say whether a wrongly accepted route is still
announced k days later. Exposure needs more: a relying party frozen at
T0 - age still finds the route not Invalid (its list never changes), so
the route stays wrongly accepted only while the current list at T0 + k
still finds it Invalid. This script validates every still-announced
wrong accept against the daily five-TA union for T0 + k.

    python analysis/rpki/rov_exposure.py --graded DIR --persist DIR --out FILE
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from rov import INVALID, VrpIndex  # noqa: E402
from rov_unit import routinator_vrps  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graded", required=True, type=Path)
    ap.add_argument("--persist", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cache", type=Path, default=Path("rov-cache"))
    args = ap.parse_args()
    units = {json.loads(p.read_text())["t0"]: json.loads(p.read_text())
             for p in args.graded.glob("rov-unit-*.json")}
    agg = defaultdict(lambda: {"accepts": 0, "still_announced": 0, "still_invalid_now": 0, "days": 0})
    per_day = []
    for p in sorted(args.persist.glob("rov-ungraded-persist-*.json")):
        r = json.loads(p.read_text())
        t0, k = r["t0"], r["offset_days"]
        present = {(a, b) for a, b in r["present"]}
        later = date.fromisoformat(t0) + timedelta(days=k)
        vrps, _ = routinator_vrps(later, args.cache)
        idx = VrpIndex(vrps)
        del vrps
        for age in ("1", "30"):
            flips = {(f[0], f[1]) for f in units[t0]["daily"][age]["accept_flips"]}
            still = flips & present
            inv = sum(1 for pfx, o in still if idx.validate(pfx, o) == INVALID)
            a = agg[(age, k)]
            a["accepts"] += len(flips); a["still_announced"] += len(still)
            a["still_invalid_now"] += inv; a["days"] += 1
            per_day.append({"t0": t0, "offset": k, "age": age, "accepts": len(flips),
                            "still_announced": len(still), "still_invalid_now": inv})
            print(t0, k, age, len(flips), len(still), inv, flush=True)
    out = {"exploratory": True,
           "by_age_offset": {f"{a}d+{k}": v for (a, k), v in sorted(agg.items())},
           "per_day": per_day}
    args.out.write_text(json.dumps(out, indent=1))
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
