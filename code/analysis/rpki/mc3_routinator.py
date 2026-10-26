#!/usr/bin/env python3
"""MC3 of PREREG-RPKI-ROV-STALENESS: our validator against Routinator.

Routinator 0.15.2 (pinned image, no network) validates the T0
announcements against exactly the VRP set our validator used, supplied
as SLURM locally added assertions with every trust anchor and fetcher
disabled. Its verdicts are compared with ours route by route and per
state. Writes `mc3.json`; the grader requires max_abs_diff_frac <= 0.001.

    sudo python analysis/rpki/mc3_routinator.py --t0 2026-09-02 \\
        --routes routes.txt --cache CACHE --out RESULTS

Runs on Atlas (Docker); the routes file comes from
`rov_unit.py --dump-announcements` for the same T0.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from rov import INVALID, NOT_FOUND, VALID, VrpIndex  # noqa: E402
from rov_unit import routinator_vrps  # noqa: E402

IMAGE = "nlnetlabs/routinator:v0.15.2"
STATE = {"valid": VALID, "invalid": INVALID, "not-found": NOT_FOUND}


def write_slurm(vrps: set, dest: Path) -> None:
    assertions = [{"asn": int(a), "prefix": p, "maxPrefixLength": int(m)}
                  for a, p, m in sorted(vrps)]
    dest.write_text(json.dumps({
        "slurmVersion": 1,
        "validationOutputFilters": {"prefixFilters": [], "bgpsecFilters": []},
        "locallyAddedAssertions": {"prefixAssertions": assertions,
                                   "bgpsecAssertions": []}}))


def run_routinator(work: Path) -> dict[tuple, str]:
    # the image runs routinator as an unprivileged user, so the mounted
    # work dir (repo store, output file) must be writable by it
    (work / "repo").mkdir(exist_ok=True)
    work.chmod(0o777)
    (work / "repo").chmod(0o777)
    cmd = ["docker", "run", "--rm", "--network", "none",
           "-v", f"{work}:/data", "--entrypoint", "routinator", IMAGE,
           "--no-rir-tals", "--disable-rsync", "--disable-rrdp",
           "-x", "/data/slurm.json", "--repository-dir", "/data/repo",
           "validate", "--noupdate", "-i", "/data/routes.txt",
           "-o", "/data/routinator-out.txt"]
    subprocess.run(cmd, check=True)
    out = {}
    for line in (work / "routinator-out.txt").read_text().splitlines():
        # "192.0.2.0/24 => AS64500: valid"
        left, state = line.rsplit(":", 1)
        prefix, asn = left.split(" => ")
        out[(prefix.strip(), int(asn.strip().upper().removeprefix("AS")))] = \
            STATE[state.strip()]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t0", required=True, type=date.fromisoformat)
    ap.add_argument("--routes", required=True, type=Path)
    ap.add_argument("--cache", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    work = (args.out / "mc3-work").resolve()   # docker -v needs an absolute path
    work.mkdir(parents=True, exist_ok=True)
    vrps, per_ta = routinator_vrps(args.t0, args.cache)
    write_slurm(vrps, work / "slurm.json")
    routes = []
    for line in args.routes.read_text().splitlines():
        prefix, asn = line.split(" => ")
        routes.append((prefix.strip(), int(asn)))
    (work / "routes.txt").write_text("".join(f"{p} => {a}\n" for p, a in routes))

    theirs = run_routinator(work)
    ours_idx = VrpIndex(vrps)
    ours = {r: ours_idx.validate(*r) for r in routes}

    missing = [r for r in routes if r not in theirs]
    disagree = [[p, a, ours[(p, a)], theirs[(p, a)]] for p, a in routes
                if (p, a) in theirs and ours[(p, a)] != theirs[(p, a)]]
    n = len(routes)
    c_ours, c_theirs = Counter(ours.values()), Counter(theirs.values())
    diffs = {s: abs(c_ours[s] - c_theirs[s]) / n for s in (VALID, INVALID, NOT_FOUND)}
    res = {"t0": args.t0.isoformat(), "image": IMAGE, "n": n,
           "vrps": len(vrps), "per_ta": per_ta,
           "ours": dict(c_ours), "routinator": dict(c_theirs),
           "per_state_abs_diff_frac": diffs,
           "max_abs_diff_frac": max(diffs.values()),
           "routes_missing_from_routinator": len(missing),
           "routes_disagreeing": len(disagree),
           "disagreement_examples": disagree[:50]}
    (args.out / "mc3.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("n", "max_abs_diff_frac",
                                          "routes_disagreeing",
                                          "routes_missing_from_routinator")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
