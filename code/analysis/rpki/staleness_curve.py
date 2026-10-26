#!/usr/bin/env python3
"""RPKI witness-staleness curve (survey §7.3) — shakedown mode until
the prereg seals.

The witness supply chain of survey §5, measured on public data: a
relying party that last synchronized Δ days ago is acting on a stale
VRP set. Grade that stale set against the current one — the same
stale-codec-vs-fresh grading OT-14 sealed on the embedding substrate,
here on the RPKI witness infrastructure itself:

- **removed fraction**: VRPs the stale view still trusts that no
  longer validate (stale authorization — the dangerous direction);
- **added fraction**: current VRPs the stale view lacks (missing
  coverage — the availability direction).

Data: `ftp.ripe.net/rpki/<tal>/YYYY/MM/DD/roas.csv.xz`, routinator
daily runs per trust anchor, archived since 2011. A VRP is the tuple
(ASN, prefix, maxLength); set comparison per TA per Δ.

    python analysis/rpki/staleness_curve.py --shakedown
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import lzma
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

BASE = "https://ftp.ripe.net/rpki"
T0 = date(2026, 8, 16)                    # reference day (complete)
DELTAS = [1, 2, 4, 8, 15, 30]
TALS_SHAKEDOWN = ["ripencc.tal", "arin.tal"]
TALS_FULL = ["ripencc.tal", "arin.tal", "apnic.tal", "lacnic.tal",
             "afrinic.tal"]
HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"


def fetch(tal: str, d: date) -> set[tuple]:
    CACHE.mkdir(exist_ok=True)
    local = CACHE / f"{tal}-{d.isoformat()}.csv.xz"
    if not local.exists():
        url = f"{BASE}/{tal}/{d.year}/{d.month:02d}/{d.day:02d}/roas.csv.xz"
        urllib.request.urlretrieve(url, local)
    vrps = set()
    with lzma.open(local, "rt", newline="") as f:
        rdr = csv.reader(f)
        header = next(rdr)
        idx = {name.strip().lower(): i for i, name in enumerate(header)}
        a = idx.get("asn", 1)
        p = idx.get("ip prefix", 2)
        m = idx.get("max length", 3)
        for row in rdr:
            if len(row) > m:
                vrps.add((row[a].strip(), row[p].strip(),
                          row[m].strip()))
    return vrps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shakedown", action="store_true")
    args = ap.parse_args()
    tals = TALS_SHAKEDOWN if args.shakedown else TALS_FULL

    out = {"cell": "rpki-staleness" + (
        "-shakedown" if args.shakedown else ""),
        "t0": T0.isoformat(), "deltas_days": DELTAS, "tals": {}}
    for tal in tals:
        fresh = fetch(tal, T0)
        rows = {}
        print(f"{tal}: {len(fresh)} VRPs at t0")
        for dd in DELTAS:
            stale = fetch(tal, T0 - timedelta(days=dd))
            removed = len(stale - fresh)
            added = len(fresh - stale)
            rows[str(dd)] = {
                "stale_vrps": len(stale),
                "removed": removed,
                "removed_frac": round(removed / max(len(stale), 1), 6),
                "added": added,
                "added_frac": round(added / max(len(fresh), 1), 6),
            }
            print(f"  d={dd:>2}d: stale {len(stale):>7} "
                  f"removed {removed:>6} ({rows[str(dd)]['removed_frac']:.4f})"
                  f"  added {added:>6} ({rows[str(dd)]['added_frac']:.4f})")
        out["tals"][tal] = {"fresh_vrps": len(fresh), "curve": rows}

    if not args.shakedown:
        # graded arm: the union of the trust anchors NOT seen at
        # shakedown -- the bars are a prediction on untouched data
        unseen = [t_ for t_ in tals if t_ not in TALS_SHAKEDOWN]
        u0 = set()
        for t_ in unseen:
            u0 |= fetch(t_, T0)
        rows = {}
        print(f"unseen-union ({'+'.join(unseen)}): {len(u0)} VRPs at t0")
        for dd in DELTAS:
            us = set()
            for t_ in unseen:
                us |= fetch(t_, T0 - timedelta(days=dd))
            removed, added = len(us - u0), len(u0 - us)
            rows[str(dd)] = {
                "stale_vrps": len(us), "removed": removed,
                "removed_frac": round(removed / max(len(us), 1), 6),
                "added": added,
                "added_frac": round(added / max(len(u0), 1), 6)}
            print(f"  d={dd:>2}d: removed_frac "
                  f"{rows[str(dd)]['removed_frac']:.4f}  added_frac "
                  f"{rows[str(dd)]['added_frac']:.4f}")
        out["unseen_union"] = {"tals": unseen, "fresh_vrps": len(u0),
                               "curve": rows}

    name = ("rpki-staleness-shakedown.json" if args.shakedown
            else "rpki-staleness.json")
    dest = HERE / ".." / ".." / "results" / name
    json.dump(out, open(dest, "w"), indent=1)
    print(f"-> results/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
