#!/usr/bin/env python3
"""One measurement unit of PREREG-RPKI-ROV-STALENESS: one reference
day T0, all configured RIS collectors.

Writes `rov-unit-<T0>.json` with, for the daily arm (RIPE NCC routinator
archive, five-TA union) and the sub-day arm (RPKIViews, rpki-client),
the ROV decision errors of each stale VRP set against the fresh one on
the T0 announcements, plus the fresh-state counts both sources give
(MC4) and the list of wrongly accepted announcements (for naming and
persistence, reported ungraded).

Graded days refuse to run until the prereg is sealed; the shakedown day
(2026-08-20) runs freely and carries no evidential weight.

    python analysis/rpki/rov_unit.py --t0 2026-08-20 --collectors rrc00 --out DIR
"""

from __future__ import annotations

import argparse
import csv
import json
import lzma
import re
import sys
import tarfile
import time
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from rov import INVALID, NOT_FOUND, VALID, VrpIndex, prefix_key  # noqa: E402

PREREG = HERE / "PREREG-RPKI-ROV-STALENESS.md"
GRADED_T0 = [date(2026, 9, 2) + timedelta(days=7 * k) for k in range(8)]
SHAKEDOWN_T0 = date(2026, 8, 20)
DAILY_DELTAS = [1, 2, 4, 8, 15, 30]                 # days
SUBDAY_DELTAS = {"1h": 3600, "6h": 6 * 3600, "1d": 86400}
TALS = ["afrinic", "apnic", "arin", "lacnic", "ripencc"]
RIPE_RPKI = "https://ftp.ripe.net/rpki"
RIS = "https://data.ris.ripe.net"
RPKIVIEWS = "https://josephine.sobornost.net/rpkidata"


def _get(url: str, dest: Path) -> Path:
    """Download once; keep the server's Last-Modified beside the file
    (`<file>.lm`), since the archive's capture time drifts within a day."""
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(4):
            try:
                tmp = dest.with_suffix(dest.suffix + ".part")
                _, headers = urllib.request.urlretrieve(url, tmp)
                Path(str(dest) + ".lm").write_text(headers.get("Last-Modified", ""))
                tmp.rename(dest)
                break
            except OSError:
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
    return dest


# ---------------------------------------------------------------- VRPs

def _vrps_from_csv(text_stream) -> list[tuple]:
    rdr = csv.reader(text_stream)
    header = next(rdr)
    idx = {name.strip().lower(): i for i, name in enumerate(header)}
    a, p, m = idx["asn"], idx["ip prefix"], idx["max length"]
    return [(r[a], r[p], r[m]) for r in rdr if len(r) > max(a, p, m)]


def routinator_union(day: date, cache: Path) -> tuple[VrpIndex, dict]:
    """The five-TA union an RP would hold on `day` (daily arm)."""
    vrps, per_ta = routinator_vrps(day, cache)
    return VrpIndex(vrps), per_ta


def routinator_vrps(day: date, cache: Path) -> tuple[set, dict]:
    """The raw five-TA VRP union for `day`, as (asn digits, prefix, maxlen)."""
    vrps: set[tuple] = set()
    per_ta = {}
    for tal in TALS:
        url = (f"{RIPE_RPKI}/{tal}.tal/{day.year}/{day.month:02d}/"
               f"{day.day:02d}/roas.csv.xz")
        f = _get(url, cache / "routinator" / f"{tal}-{day.isoformat()}.csv.xz")
        with lzma.open(f, "rt", newline="") as fh:
            got = {(a.strip().upper().removeprefix("AS"), p.strip(), m.strip())
                   for a, p, m in _vrps_from_csv(fh)}
        per_ta[tal] = len(got)
        lm = Path(str(f) + ".lm")
        per_ta[f"{tal}_last_modified"] = lm.read_text() if lm.exists() else ""
        vrps |= got
    return vrps, per_ta


_SNAP = re.compile(r'href="(rpki-(\d{8}T\d{6})Z\.tgz)"')


def _snapshots(day: date) -> list[tuple[datetime, str]]:
    url = f"{RPKIVIEWS}/{day.year}/{day.month:02d}/{day.day:02d}/"
    with urllib.request.urlopen(url, timeout=120) as r:
        html = r.read().decode()
    out = []
    for name, stamp in _SNAP.findall(html):
        ts = datetime.strptime(stamp, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        out.append((ts, url + name))
    return sorted(out)


def rpkiviews_vrps(url: str, cache: Path) -> VrpIndex:
    """Stream the snapshot and keep only output/rpki-client.csv, which
    sits at the head of the archive; the connection closes after it."""
    local = cache / "rpkiviews" / (url.rsplit("/", 1)[1] + ".csv")
    if not local.exists():
        local.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=300) as r:
            with tarfile.open(fileobj=r, mode="r|gz") as tar:
                for member in tar:
                    if member.name.endswith("output/rpki-client.csv"):
                        local.write_bytes(tar.extractfile(member).read())
                        break
        if not local.exists():
            raise RuntimeError(f"no output/rpki-client.csv in {url}")
    with open(local, newline="") as fh:
        vrps = {(a.strip().upper().removeprefix("AS"), p.strip(), m.strip())
                for a, p, m in _vrps_from_csv(fh)}
    return VrpIndex(vrps)


def subday_points(t0: date) -> dict[str, tuple[datetime, str]]:
    """fresh = first snapshot at/after T0 00:00 UTC; stale at Δ = the
    latest snapshot at/before (fresh timestamp - Δ)."""
    start = datetime(t0.year, t0.month, t0.day, tzinfo=timezone.utc)
    snaps = _snapshots(t0 - timedelta(days=2)) + _snapshots(t0 - timedelta(days=1)) \
        + _snapshots(t0)
    fresh = next((s for s in snaps if s[0] >= start), None)
    if fresh is None:
        raise RuntimeError(f"no RPKIViews snapshot at/after {start}")
    pts = {"fresh": fresh}
    for label, secs in SUBDAY_DELTAS.items():
        cut = fresh[0] - timedelta(seconds=secs)
        before = [s for s in snaps if s[0] <= cut]
        if not before:
            raise RuntimeError(f"no RPKIViews snapshot at/before {cut}")
        pts[label] = before[-1]
    return pts


# ------------------------------------------------------- announcements

def announcements(t0: date, collectors: list[str]) -> tuple[dict, dict]:
    """Distinct (prefix, origin) pairs in the T0 00:00 RIB dumps, with the
    number of distinct (collector, peer) that carry each. AS_SET origins
    are excluded and counted."""
    import bgpkit

    # A RIB dump holds one route per peer per prefix, so counting elems
    # counts peers; storing peer identities would cost ~100 tuples per pair.
    seen: dict[tuple, int] = defaultdict(int)
    colls: dict[tuple, int] = defaultdict(int)      # bitmask of collectors
    stats = {}
    for i, c in enumerate(collectors):
        bit = 1 << i
        url = (f"{RIS}/{c}/{t0.year}.{t0.month:02d}/"
               f"bview.{t0.strftime('%Y%m%d')}.0000.gz")
        n_elem = n_set = 0
        for elem in bgpkit.Parser(url=url):
            n_elem += 1
            path = str(elem.as_path or "").split()
            if not path:
                continue
            last = path[-1]
            if not last.isdigit():          # AS_SET or confederation
                n_set += 1
                continue
            key = (str(elem.prefix), int(last))
            seen[key] += 1
            colls[key] |= bit
        stats[c] = {"rib_elems": n_elem, "as_set_origins": n_set}
    for i, c in enumerate(collectors):
        stats[c]["distinct_pairs"] = sum(1 for v in colls.values() if v >> i & 1)
    del colls
    peers = dict(seen)
    return peers, stats


# --------------------------------------------------------------- grading

def _parsed(peers: dict) -> list[tuple]:
    """(prefix text, family, length, network int, origin, peer count),
    parsed once and kept as plain ints to stay inside a 2 GiB pod."""
    return [(p, *prefix_key(p), o, n) for (p, o), n in peers.items()]


def _states(rows: list[tuple], idx: VrpIndex) -> list[str]:
    return [idx.validate_key(fam, plen, addr, o)
            for _, fam, plen, addr, o, _ in rows]


def _counts(states: list[str]) -> dict:
    counts = {VALID: 0, INVALID: 0, NOT_FOUND: 0}
    for s in states:
        counts[s] += 1
    return counts


def _errors(rows: list[tuple], fresh_st: list[str], stale: VrpIndex) -> dict:
    """Same quantities as rov.decision_errors (tested there), computed
    against precomputed fresh states, plus the ungraded weighted views
    and the list of wrongly accepted announcements."""
    trans: dict[str, int] = defaultdict(int)
    w = {"accept_peer": 0, "drop_peer": 0, "peer_total": 0,
         "accept_v4_addr": 0, "drop_v4_addr": 0, "v4_addr_total": 0}
    flips = []
    for (prefix, fam, plen, addr, origin, npeer), f in zip(rows, fresh_st):
        s = stale.validate_key(fam, plen, addr, origin)
        trans[f"{s}->{f}"] += 1
        v4 = fam == 4
        size = 1 << (32 - plen) if v4 else 0
        w["peer_total"] += npeer
        w["v4_addr_total"] += size
        if f == INVALID and s != INVALID:
            w["accept_peer"] += npeer
            w["accept_v4_addr"] += size
            flips.append([prefix, origin, f"{s}->{f}", npeer])
        elif s == INVALID and f != INVALID:
            w["drop_peer"] += npeer
            w["drop_v4_addr"] += size
    n = len(rows)
    accept = trans[f"{VALID}->{INVALID}"] + trans[f"{NOT_FOUND}->{INVALID}"]
    drop = trans[f"{INVALID}->{VALID}"] + trans[f"{INVALID}->{NOT_FOUND}"]
    return {"n": n, "transitions": dict(trans), "accept": accept,
            "accept_revoked": trans[f"{VALID}->{INVALID}"],
            "accept_unseen": trans[f"{NOT_FOUND}->{INVALID}"],
            "drop": drop, "e_accept": accept / n if n else 0.0,
            "e_drop": drop / n if n else 0.0, "weighted": w,
            "accept_flips": flips}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t0", required=True, type=date.fromisoformat)
    ap.add_argument("--collectors", default="rrc00,rrc01,rrc03")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cache", type=Path, default=Path("rov-cache"))
    ap.add_argument("--dump-announcements", type=Path,
                    help="write the T0 announcements as 'prefix => asn' lines (MC3)")
    ap.add_argument("--announcements-only", action="store_true",
                    help="stop after --dump-announcements (MC3 extraction on Atlas)")
    args = ap.parse_args()
    collectors = args.collectors.split(",")

    if args.t0 in GRADED_T0:
        sys.path.insert(0, str(HERE.parent.parent))
        from governor.sealed import require_seal
        require_seal(PREREG)
    elif args.t0 != SHAKEDOWN_T0:
        raise SystemExit(f"{args.t0} is neither a graded day nor the shakedown day")

    t_start = time.time()
    peers, rib_stats = announcements(args.t0, collectors)
    out = {"t0": args.t0.isoformat(), "collectors": collectors,
           "shakedown": args.t0 == SHAKEDOWN_T0, "n": len(peers),
           "rib": rib_stats, "daily": {}, "subday": {}}

    if args.dump_announcements:
        with open(args.dump_announcements, "w") as fh:
            for prefix, origin in peers:
                fh.write(f"{prefix} => {origin}\n")
        if args.announcements_only:
            print(f"-> {args.dump_announcements} ({len(peers)} announcements)")
            return 0
    rows = _parsed(peers)
    del peers
    fresh, per_ta = routinator_union(args.t0, args.cache)
    fst = _states(rows, fresh)
    out["daily_fresh"] = {"vrps": fresh.size, "per_ta": per_ta,
                          "states": _counts(fst)}
    del fresh
    for d in DAILY_DELTAS:
        stale, ta = routinator_union(args.t0 - timedelta(days=d), args.cache)
        r = _errors(rows, fst, stale)
        r["stale_vrps"], r["stale_per_ta"] = stale.size, ta
        out["daily"][str(d)] = r
        print(f"daily d={d:>2}: e_accept {r['e_accept']:.6f} "
              f"e_drop {r['e_drop']:.6f}", flush=True)
        del stale

    pts = subday_points(args.t0)
    vfresh = rpkiviews_vrps(pts["fresh"][1], args.cache)
    vst = _states(rows, vfresh)
    out["subday_fresh"] = {"snapshot": pts["fresh"][1], "vrps": vfresh.size,
                           "states": _counts(vst)}
    del vfresh
    for label in SUBDAY_DELTAS:
        stale = rpkiviews_vrps(pts[label][1], args.cache)
        r = _errors(rows, vst, stale)
        r["snapshot"], r["stale_vrps"] = pts[label][1], stale.size
        out["subday"][label] = r
        print(f"subday {label}: e_accept {r['e_accept']:.6f} "
              f"e_drop {r['e_drop']:.6f}", flush=True)
        del stale

    out["elapsed_s"] = round(time.time() - t_start, 1)
    args.out.mkdir(parents=True, exist_ok=True)
    dest = args.out / f"rov-unit-{args.t0.isoformat()}.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"-> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
