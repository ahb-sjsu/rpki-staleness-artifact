"""Ungraded lookup behind the paper's "Who Is Exposed" section.

For each one-day wrong accept carried by 110 or more RIS peers, and for the
one block that is a wrong accept on all eight days, print the VRPs that cover
it in the stale (T0 - 1 day) and current (T0) daily five-TA unions. Uses the
sealed loader `rov_unit.routinator_vrps`, so it downloads the RIPE NCC daily
archive files for each day into CACHE.

    python code/lookups/whatchanged.py [CACHE] > results/lookups/whatchanged.txt

The output shipped in results/lookups/whatchanged.txt was produced by this
script with absolute paths in place of the repo-relative ones below.
"""
import ipaddress
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code" / "analysis" / "rpki"))
from rov_unit import routinator_vrps  # noqa: E402

G = ROOT / "results" / "graded"
CACHE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "whatchanged-cache"
U = {json.loads(p.read_text())["t0"]: json.loads(p.read_text()) for p in G.glob("rov-unit-*.json")}

pick = defaultdict(list)          # t0 -> flips
days = defaultdict(set)
for t0, u in U.items():
    for f in u["daily"]["1"]["accept_flips"]:
        days[(f[0], f[1])].add(t0)
every = [k for k, v in days.items() if len(v) == 8]
for t0, u in U.items():
    for f in u["daily"]["1"]["accept_flips"]:
        if f[3] >= 110 or (f[0], f[1]) in every:
            pick[t0].append(f)


def cover(vrps, prefix):
    net = ipaddress.ip_network(prefix)
    out = []
    for a, p, m in vrps:
        n = ipaddress.ip_network(p)
        if n.version == net.version and net.subnet_of(n):
            out.append((a, p, int(m)))
    return sorted(out)


for t0 in sorted(pick):
    d = date.fromisoformat(t0)
    now, _ = routinator_vrps(d, CACHE)
    old, _ = routinator_vrps(d - timedelta(days=1), CACHE)
    for p, o, tr, npeer in pick[t0]:
        print(f"{t0} {p} AS{o} {tr} peers={npeer} on {len(days[(p, o)])} day(s)")
        print("   stale:", cover(old, p))
        print("   now:  ", cover(now, p))
print("WC-DONE")
