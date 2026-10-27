#!/usr/bin/env python3
"""Exploratory, written after grading in answer to review (2026-10-26).
Not part of PREREG-RPKI-ROV-STALENESS and grades nothing.

For one reference day, from complete local copies of the RIB dumps:

1. route-level bridge: the 3x3 table of outcomes each route gets from the
   daily archive's current list (Routinator) and the snapshot archive's
   current list (rpki-client), and how many of each arm's error routes
   are among the routes on which the two current lists disagree;
2. AS0 overlap: routes that are Valid although an AS0 VRP also covers
   them (RFC 6483 precedence), so the inputs exercise that case;
3. covering routes for wrong drops (v2: covers shorter than /8 or /16
   are ignored; v1 counted default routes): for each route a stale list wrongly
   drops, whether a less specific announced prefix covers it that the
   same stale list does not find Invalid, i.e. a route that could still
   carry the traffic.

    python analysis/rpki/rov_bridge.py --t0 2026-09-02 --record graded/rov-unit-2026-09-02.json --out DIR

The announcement count must equal the record's (the 16 September record
recomputed from the complete dumps is the one to pass for that day).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from rov import INVALID, VALID, VrpIndex  # noqa: E402
from rov_unit import (SUBDAY_DELTAS, _parsed, _states, routinator_vrps,  # noqa: E402
                      rpkiviews_vrps, subday_points)
from rov_ungraded import announcements_masked  # noqa: E402

STATES = ("valid", "invalid", "not_found")


def _errors(rows, fresh_st, stale_st) -> tuple[set, set]:
    acc, drp = set(), set()
    for r, f, s in zip(rows, fresh_st, stale_st):
        if f == INVALID and s != INVALID:
            acc.add((r[0], r[4]))
        elif s == INVALID and f != INVALID:
            drp.add((r[0], r[4]))
    return acc, drp


def _as0_overlap(rows, idx: VrpIndex, st) -> int:
    n = 0
    for (p, fam, plen, addr, o, _), s in zip(rows, st):
        if s == VALID and any(asn == 0 for asn, _m in idx.covering_key(fam, plen, addr)):
            n += 1
    return n


MIN_COVER = {4: 8, 6: 16}   # a default route or a /1 is not an aggregate (v1 counted them)


def _covered(rows, stale_st, drops: set) -> dict:
    """For each wrongly dropped route, the most specific strictly less
    specific announced prefix, no shorter than MIN_COVER, that the stale
    list does not find Invalid; whether its origin is the dropped route's
    own; and its length."""
    usable = defaultdict(lambda: defaultdict(set))   # (fam, len) -> addr -> origins
    for (p, fam, plen, addr, o, _), s in zip(rows, stale_st):
        if s != INVALID and plen >= MIN_COVER[fam]:
            usable[(fam, plen)][addr].add(o)
    lengths = {f: sorted({ln for (ff, ln) in usable if ff == f}, reverse=True) for f in (4, 6)}
    hit = same = 0
    by_len: Counter = Counter()
    for p, fam, plen, addr, o, _ in rows:
        if (p, o) not in drops:
            continue
        width = 32 if fam == 4 else 128
        for ln in lengths[fam]:
            if ln >= plen:
                continue
            mask = ((1 << ln) - 1) << (width - ln)
            origins = usable[(fam, ln)].get(addr & mask)
            if origins:
                hit += 1
                same += o in origins
                by_len[f"v{fam}/{ln}"] += 1
                break
    return {"drops": len(drops), "with_usable_cover": hit, "cover_same_origin": same,
            "min_cover": MIN_COVER, "cover_length": dict(by_len.most_common(12))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t0", required=True, type=date.fromisoformat)
    ap.add_argument("--record", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cache", type=Path, default=Path("rov-cache"))
    args = ap.parse_args()
    t_start = time.time()
    rec = json.loads(args.record.read_text())
    collectors = rec["collectors"]
    rib: dict = {}
    peers, _colls = announcements_masked(args.t0, collectors, rib, args.cache / "rib")
    del _colls
    rows = _parsed(peers)
    del peers
    out = {"t0": args.t0.isoformat(), "n": len(rows), "n_matches_record": len(rows) == rec["n"],
           "rib": rib, "exploratory": True}

    dvrps, _ = routinator_vrps(args.t0, args.cache)
    didx = VrpIndex(dvrps)
    del dvrps
    dst = _states(rows, didx)
    out["as0_valid_overlap_daily_current"] = _as0_overlap(rows, didx, dst)
    del didx

    pts = subday_points(args.t0)
    sidx = rpkiviews_vrps(pts["fresh"][1], args.cache)
    sst = _states(rows, sidx)
    del sidx
    conf = Counter(f"{a}|{b}" for a, b in zip(dst, sst))
    out["bridge_confusion_daily_by_snapshot"] = {f"{a}|{b}": conf.get(f"{a}|{b}", 0)
                                                 for a in STATES for b in STATES}
    disagree = {(r[0], r[4]) for r, a, b in zip(rows, dst, sst) if a != b}
    out["bridge_disagree"] = len(disagree)

    out["subday"] = {}
    for label in SUBDAY_DELTAS:
        stale = rpkiviews_vrps(pts[label][1], args.cache)
        st = _states(rows, stale)
        del stale
        acc, drp = _errors(rows, sst, st)
        out["subday"][label] = {"accept": len(acc), "drop": len(drp),
                                "accept_on_disagreeing_routes": len(acc & disagree),
                                "drop_on_disagreeing_routes": len(drp & disagree),
                                "check_matches_record": (len(acc), len(drp)) == (
                                    rec["subday"][label]["accept"], rec["subday"][label]["drop"])}
        print(label, out["subday"][label], flush=True)

    out["daily"] = {}
    for d in (1, 30):
        vrps, _ = routinator_vrps(args.t0 - timedelta(days=d), args.cache)
        st = _states(rows, VrpIndex(vrps))
        del vrps
        acc, drp = _errors(rows, dst, st)
        out["daily"][str(d)] = {"accept": len(acc), "drop": len(drp),
                                "accept_on_disagreeing_routes": len(acc & disagree),
                                "drop_on_disagreeing_routes": len(drp & disagree),
                                "drop_cover": _covered(rows, st, drp),
                                "check_matches_record": (len(acc), len(drp)) == (
                                    rec["daily"][str(d)]["accept"], rec["daily"][str(d)]["drop"])}
        print(d, out["daily"][str(d)], flush=True)

    out["elapsed_s"] = round(time.time() - t_start, 1)
    args.out.mkdir(parents=True, exist_ok=True)
    dest = args.out / f"rov-bridge-{args.t0.isoformat()}.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"-> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
