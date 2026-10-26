#!/usr/bin/env python3
"""Ungraded reports of PREREG-RPKI-ROV-STALENESS that the graded unit
records do not hold. Post hoc: written 2026-10-25, after the seal and
before any graded record was read. Nothing here grades a bar.

Two modes, one job each:

  attrib   one T0. Recomputes the T0 decisions with the sealed validator
           (rov.VrpIndex, unchanged) and attributes every wrong accept and
           wrong drop by RIS collector, by address family and, on the
           daily arm, by trust anchor. Also lists the wrong drops, which
           the graded record does not. Its transition counts must equal
           the graded record's exactly (`consistent` in the output); an
           attribution that does not reproduce the graded counts is not
           reported.

  persist  one T0 and one offset k in {1, 7, 30} days. Of the wrongly
           accepted announcements in the graded record (every daily and
           sub-day age), how many are still seen by the same collectors
           in the RIB dumps of T0 + k at 00:00 UTC.

RIB dumps are downloaded in full and checked (Content-Length and gzip CRC)
before parsing, and each record keeps per-collector byte and entry counts.
The first version streamed them from the URL, and such a stream can end
early without an error (fixed 2026-10-25, after the 2026-09-09 attribution
and the graded 2026-09-16 rrc00 read were found cut).

Trust-anchor attribution: a flip involves trust anchor r when the VRPs
of r covering the prefix differ between the fresh and the stale set.
A flip can involve more than one; those are counted under "multi" as
well as under each anchor. The sub-day arm has no trust-anchor
attribution (one rpki-client feed, not per-anchor files).

    python analysis/rpki/rov_ungraded.py attrib --t0 2026-09-02 \\
        --record graded/rov-unit-2026-09-02.json --out DIR
    python analysis/rpki/rov_ungraded.py persist --t0 2026-09-02 --offset 7 \\
        --record graded/rov-unit-2026-09-02.json --out DIR
"""

from __future__ import annotations

import argparse
import gzip
import json
import lzma
import shutil
import sys
import time
import urllib.request
import zlib
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from rov import INVALID, VrpIndex  # noqa: E402
from rov_unit import (DAILY_DELTAS, GRADED_T0, RIPE_RPKI, RIS,  # noqa: E402
                      SHAKEDOWN_T0, SUBDAY_DELTAS, TALS, _get, _parsed,
                      _states, _vrps_from_csv, rpkiviews_vrps, subday_points)

OFFSETS = [1, 7, 30]


def _gzip_ok(path: Path) -> bool:
    """Read the whole gzip stream; a cut file fails the length or CRC check."""
    try:
        with gzip.open(path, "rb") as fh:
            while fh.read(1 << 22):
                pass
        return True
    except (EOFError, OSError, zlib.error):
        return False


def _fetch_rib(url: str, dest: Path, tries: int = 3) -> dict:
    """Download one RIB dump in full. Streaming it into the parser can end
    early without an error (2026-10-25: graded 2026-09-16 rrc00 lost 10%
    of its entries), so the file must match Content-Length and pass its
    gzip check before it is parsed. Stops the job if it never does."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    got = want = -1
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(url, timeout=300) as r, open(dest, "wb") as fh:
                want = int(r.headers["Content-Length"])
                shutil.copyfileobj(r, fh, 1 << 20)
        except OSError as e:
            print(f"{url}: attempt {attempt}: {e}", flush=True)
            continue
        got = dest.stat().st_size
        if got == want and _gzip_ok(dest):
            return {"bytes": got, "attempts": attempt}
        print(f"{url}: attempt {attempt}: {got} of {want} bytes or bad gzip", flush=True)
    raise SystemExit(f"RIB {url} incomplete after {tries} tries ({got} of {want} bytes)")


def _rib_pairs(day: date, collectors: list[str], stats: dict, workdir: Path):
    """Yield (collector index, (prefix, origin)) for the day's 00:00 RIB
    dumps, with exactly rov_unit.announcements' filtering, from complete
    local copies. Fills stats[collector] with bytes, attempts, rib_elems."""
    import bgpkit

    for i, c in enumerate(collectors):
        url = (f"{RIS}/{c}/{day.year}.{day.month:02d}/"
               f"bview.{day.strftime('%Y%m%d')}.0000.gz")
        local = workdir / f"bview.{c}.{day.strftime('%Y%m%d')}.gz"
        s = _fetch_rib(url, local)
        n_elem = 0
        for elem in bgpkit.Parser(url=str(local)):
            n_elem += 1
            path = str(elem.as_path or "").split()
            if not path or not path[-1].isdigit():
                continue
            yield i, (str(elem.prefix), int(path[-1]))
        local.unlink()
        stats[c] = s | {"rib_elems": n_elem}
        print(f"{c} {day}: {s['bytes']} bytes, {n_elem} entries", flush=True)


def announcements_masked(t0: date, collectors: list[str], stats: dict,
                         workdir: Path) -> tuple[dict, dict]:
    """rov_unit.announcements, keeping the per-collector bitmask."""
    seen: dict[tuple, int] = defaultdict(int)
    colls: dict[tuple, int] = defaultdict(int)
    for i, key in _rib_pairs(t0, collectors, stats, workdir):
        seen[key] += 1
        colls[key] |= 1 << i
    return dict(seen), dict(colls)


def per_ta(day: date, cache: Path) -> dict[str, set]:
    """rov_unit.routinator_vrps, kept per trust anchor."""
    out = {}
    for tal in TALS:
        url = (f"{RIPE_RPKI}/{tal}.tal/{day.year}/{day.month:02d}/"
               f"{day.day:02d}/roas.csv.xz")
        f = _get(url, cache / "routinator" / f"{tal}-{day.isoformat()}.csv.xz")
        with lzma.open(f, "rt", newline="") as fh:
            out[tal] = {(a.strip().upper().removeprefix("AS"), p.strip(), m.strip())
                        for a, p, m in _vrps_from_csv(fh)}
    return out


def _union(sets: dict[str, set]) -> VrpIndex:
    u: set = set()
    for s in sets.values():
        u |= s
    return VrpIndex(u)


def _blank(collectors: list[str]) -> dict:
    return {"by_collector": {c: 0 for c in collectors}, "v4": 0, "v6": 0}


def _attribute(rows, masks, fst, stale_idx, collectors, ta_fresh=None,
               ta_stale=None) -> dict:
    """Transitions (to check against the graded record) and the
    attribution of every flip."""
    trans: dict[str, int] = defaultdict(int)
    acc, drp = _blank(collectors), _blank(collectors)
    if ta_fresh is not None:
        for d in (acc, drp):
            d["by_ta"] = {t: 0 for t in TALS} | {"multi": 0, "none": 0}
    drops = []
    for (prefix, fam, plen, addr, origin, npeer), mask, f in zip(rows, masks, fst):
        s = stale_idx.validate_key(fam, plen, addr, origin)
        trans[f"{s}->{f}"] += 1
        if f == INVALID and s != INVALID:
            d = acc
        elif s == INVALID and f != INVALID:
            d = drp
            drops.append([prefix, origin, f"{s}->{f}", npeer, mask])
        else:
            continue
        d["v4" if fam == 4 else "v6"] += 1
        for i, c in enumerate(collectors):
            if mask >> i & 1:
                d["by_collector"][c] += 1
        if ta_fresh is not None:
            hit = [t for t in TALS
                   if sorted(ta_fresh[t].covering_key(fam, plen, addr))
                   != sorted(ta_stale[t].covering_key(fam, plen, addr))]
            for t in hit:
                d["by_ta"][t] += 1
            if len(hit) > 1:
                d["by_ta"]["multi"] += 1
            elif not hit:   # cannot happen if the union changed; a sanity count
                d["by_ta"]["none"] += 1
    return {"transitions": dict(trans), "accept": acc, "drop": drp,
            "drop_flips": drops}


def _nz(trans: dict) -> dict:
    """Transitions without zero counts. rov_unit._errors reads two keys of
    its defaultdict before saving it, so the graded record carries them as
    0 when they never occurred; that is not a disagreement."""
    return {k: v for k, v in trans.items() if v}


def _family_totals(rows) -> dict:
    n4 = sum(1 for r in rows if r[1] == 4)
    return {"n_v4": n4, "n_v6": len(rows) - n4}


def attrib(args) -> dict:
    rec = json.loads(args.record.read_text())
    collectors = rec["collectors"]
    rib: dict = {}
    peers, colls = announcements_masked(args.t0, collectors, rib, args.cache / "rib")
    rows = _parsed(peers)
    masks = [colls[(p, o)] for p, *_mid, o, _n in rows]
    del peers, colls
    by_coll = {c: sum(1 for m in masks if m >> i & 1) for i, c in enumerate(collectors)}
    for c in collectors:
        rib[c]["distinct_pairs"] = by_coll[c]
    out = {"t0": args.t0.isoformat(), "collectors": collectors, "n": len(rows),
           **_family_totals(rows), "rib": rib, "n_by_collector": by_coll,
           "daily": {}, "subday": {}}
    # The record's own per-collector counts must match too: a cut read on
    # either side shows here first (MC1's 500k floor does not catch it).
    checks = {"n": len(rows) == rec["n"],
              **{f"rib_{c}": by_coll[c] == rec["rib"][c]["distinct_pairs"]
                 for c in collectors}}

    fresh_sets = per_ta(args.t0, args.cache)
    fresh = _union(fresh_sets)
    fst = _states(rows, fresh)
    del fresh
    ta_fresh = {t: VrpIndex(s) for t, s in fresh_sets.items()}
    del fresh_sets
    for d in DAILY_DELTAS:
        stale_sets = per_ta(args.t0 - timedelta(days=d), args.cache)
        stale = _union(stale_sets)
        ta_stale = {t: VrpIndex(s) for t, s in stale_sets.items()}
        del stale_sets
        r = _attribute(rows, masks, fst, stale, collectors, ta_fresh, ta_stale)
        checks[f"daily_{d}"] = _nz(r["transitions"]) == _nz(rec["daily"][str(d)]["transitions"])
        out["daily"][str(d)] = r
        print(f"daily d={d:>2}: consistent={checks[f'daily_{d}']}", flush=True)
        del stale, ta_stale
    del ta_fresh

    pts = subday_points(args.t0)
    vfresh = rpkiviews_vrps(pts["fresh"][1], args.cache)
    vst = _states(rows, vfresh)
    del vfresh
    for label in SUBDAY_DELTAS:
        stale = rpkiviews_vrps(pts[label][1], args.cache)
        r = _attribute(rows, masks, vst, stale, collectors)
        checks[f"subday_{label}"] = (_nz(r["transitions"])
                                     == _nz(rec["subday"][label]["transitions"]))
        out["subday"][label] = r
        print(f"subday {label}: consistent={checks[f'subday_{label}']}", flush=True)
        del stale
    out["checks"] = checks
    out["consistent"] = all(checks.values())
    return out


def persist(args) -> dict:
    rec = json.loads(args.record.read_text())
    collectors = rec["collectors"]
    later = args.t0 + timedelta(days=args.offset)
    by_age = {f"daily_{d}": {(p, o) for p, o, *_ in rec["daily"][str(d)]["accept_flips"]}
              for d in DAILY_DELTAS}
    by_age |= {f"subday_{lab}": {(p, o) for p, o, *_ in rec["subday"][lab]["accept_flips"]}
               for lab in SUBDAY_DELTAS}
    wanted = set().union(*by_age.values())
    present: set = set()
    rib: dict = {}
    for _, key in _rib_pairs(later, collectors, rib, args.cache / "rib"):
        if key in wanted:
            present.add(key)
    return {"t0": args.t0.isoformat(), "offset_days": args.offset,
            "rib_day": later.isoformat(), "collectors": collectors, "rib": rib,
            "by_age": {a: {"accepts": len(k), "still_present": len(k & present)}
                       for a, k in by_age.items()},
            "present": sorted([p, o] for p, o in present)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["attrib", "persist"])
    ap.add_argument("--t0", required=True, type=date.fromisoformat)
    ap.add_argument("--record", required=True, type=Path,
                    help="the graded rov-unit-<T0>.json for this T0")
    ap.add_argument("--offset", type=int, choices=OFFSETS)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cache", type=Path, default=Path("rov-cache"))
    args = ap.parse_args()
    if args.t0 not in GRADED_T0 and args.t0 != SHAKEDOWN_T0:
        raise SystemExit(f"{args.t0} is neither a graded day nor the shakedown day")
    t_start = time.time()
    if args.mode == "attrib":
        out = attrib(args)
        name = f"rov-ungraded-attrib-{args.t0.isoformat()}.json"
    else:
        if args.offset is None:
            raise SystemExit("persist needs --offset")
        out = persist(args)
        name = f"rov-ungraded-persist-{args.t0.isoformat()}-p{args.offset}.json"
    out["elapsed_s"] = round(time.time() - t_start, 1)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / name).write_text(json.dumps(out, indent=1))
    print(f"-> {args.out / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
