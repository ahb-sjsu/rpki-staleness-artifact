"""Sealed RPKI staleness evaluation, PREREG-RPKI-STALENESS.
Refuses to run unless the prereg is SEALED; grades the record
written by `staleness_curve.py` (full mode).

    python analysis/rpki/run_sealed_rpki.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "..", "..", "results")


def require_seal():
    t = open(os.path.join(HERE, "PREREG-RPKI-STALENESS.md"),
             encoding="utf-8").read()
    if "STATUS: DRAFT-UNSEALED" in t or "STATUS: SEALED" not in t:
        sys.exit("REFUSED: PREREG-RPKI-STALENESS.md is not SEALED.")


def strictly_monotone(vals: list[float]) -> bool:
    return all(b > a for a, b in zip(vals, vals[1:]))


def main():
    require_seal()
    d = json.load(open(os.path.join(RESULTS, "rpki-staleness.json")))
    unseen = d["unseen_union"]
    deltas = [str(x) for x in d["deltas_days"]]

    mc1 = all(v["fresh_vrps"] > 1000 for k, v in d["tals"].items()
              if k in unseen["tals"]) and unseen["fresh_vrps"] > 1000
    removed = [unseen["curve"][k]["removed_frac"] for k in deltas]
    added = [unseen["curve"][k]["added_frac"] for k in deltas]
    b1 = strictly_monotone(removed) and strictly_monotone(added)
    b2 = unseen["curve"]["1"]["removed_frac"] <= 0.002

    verdict = "VOID" if not mc1 else ("PASS" if (b1 and b2) else "FAIL")
    print(f"MC1 census/floors: {'ok' if mc1 else 'VOID'}")
    print(f"B1 strict monotonicity on unseen union: "
          f"removed {removed} added {added} -> "
          f"{'PASS' if b1 else 'FAIL'}")
    print(f"B2 daily-refresh floor (removed@1d "
          f"{unseen['curve']['1']['removed_frac']} <= 0.002): "
          f"{'PASS' if b2 else 'FAIL'}")
    d["verdict"] = {"MC1": bool(mc1), "B1": bool(b1), "B2": bool(b2),
                    "verdict": verdict}
    json.dump(d, open(os.path.join(RESULTS, "rpki-staleness.json"),
                      "w"), indent=1)
    print(f"\nRPKI-STALENESS: {verdict} -> results/rpki-staleness.json")


if __name__ == "__main__":
    main()
