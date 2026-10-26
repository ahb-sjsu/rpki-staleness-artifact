#!/usr/bin/env python3
"""Grade PREREG-RPKI-ROV-STALENESS from the eight unit records.

    python analysis/rpki/run_sealed_rov.py RESULTS_DIR

Reads `rov-unit-<T0>.json` for every graded T0 and `mc3.json` (the
independent-validator cross-check), applies MC1 to MC4 and bars B1 to
B4 exactly as the prereg states them, and writes
`results/rpki-rov-staleness.json` as executed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from governor.sealed import require_seal  # noqa: E402
from rov_unit import DAILY_DELTAS, GRADED_T0, PREREG, SUBDAY_DELTAS  # noqa: E402

SE_BAR = 4.0
B3_RATIO = 0.10
BOOT = 10_000
SEED = 20261025


def _paired(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    d = b - a
    return float(d.mean()), float(d.std(ddof=1) / np.sqrt(len(d)))


def _increasing(means: list[float], strict: bool) -> bool:
    pairs = zip(means, means[1:])
    return all((y > x) if strict else (y >= x) for x, y in pairs)


def main(results: Path) -> int:
    require_seal(PREREG)
    units = []
    for t0 in GRADED_T0:
        f = results / f"rov-unit-{t0.isoformat()}.json"
        units.append(json.loads(f.read_text()))
    out = {"cell": "rpki-rov-staleness", "t0": [u["t0"] for u in units],
           "mc": {}, "bars": {}}

    # MC1 inputs
    mc1 = []
    for u in units:
        for c, s in u["rib"].items():
            if s.get("distinct_pairs", 0) <= 500_000:
                mc1.append(f"{u['t0']} {c}: {s.get('distinct_pairs')} pairs")
        tas = [u["daily_fresh"]["per_ta"]] + \
            [r["stale_per_ta"] for r in u["daily"].values()]
        for per in tas:
            for tal, n in per.items():
                if tal.endswith("_last_modified"):
                    continue
                if n <= 1000:
                    mc1.append(f"{u['t0']} {tal}: {n} VRPs")
    out["mc"]["MC1"] = {"ok": not mc1, "failures": mc1}

    # MC2 planted validator tests
    p = subprocess.run([sys.executable, "-m", "pytest", "-q",
                        str(ROOT / "tests" / "test_rpki_rov.py")],
                       capture_output=True, text=True, cwd=ROOT)
    out["mc"]["MC2"] = {"ok": p.returncode == 0, "tail": p.stdout[-400:]}

    # MC3 independent validator
    mc3_path = results / "mc3.json"
    if mc3_path.exists():
        mc3 = json.loads(mc3_path.read_text())
        out["mc"]["MC3"] = {"ok": mc3["max_abs_diff_frac"] <= 0.001, **mc3}
    else:
        out["mc"]["MC3"] = {"ok": False, "reason": "mc3.json missing"}

    # MC4 sub-day bridge (voids B4 only)
    mc4 = []
    for u in units:
        n = u["n"]
        a, b = u["daily_fresh"]["states"], u["subday_fresh"]["states"]
        for state in a:
            diff = abs(a[state] - b[state]) / n
            if diff > 0.005:
                mc4.append(f"{u['t0']} {state}: {diff:.4%}")
    out["mc"]["MC4"] = {"ok": not mc4, "failures": mc4}

    void = not all(out["mc"][k]["ok"] for k in ("MC1", "MC2", "MC3"))

    # daily arm
    acc = {d: np.array([u["daily"][str(d)]["e_accept"] for u in units])
           for d in DAILY_DELTAS}
    drp = {d: np.array([u["daily"][str(d)]["e_drop"] for u in units])
           for d in DAILY_DELTAS}
    for name, series in (("B1", acc), ("B2", drp)):
        means = [float(series[d].mean()) for d in DAILY_DELTAS]
        gain, se = _paired(series[1], series[30])
        out["bars"][name] = {
            "means": dict(zip(map(str, DAILY_DELTAS), means)),
            "strictly_increasing": _increasing(means, strict=True),
            "diff_30_minus_1": gain, "se": se,
            "pass": _increasing(means, strict=True) and gain > SE_BAR * se}

    rng = np.random.default_rng(SEED)
    k = len(units)
    ratios = []
    for _ in range(BOOT):
        idx = rng.integers(0, k, k)
        m30 = acc[30][idx].mean()
        ratios.append(acc[1][idx].mean() / m30 if m30 > 0 else np.inf)
    upper = float(np.percentile(ratios, 95))
    out["bars"]["B3"] = {"ratio_point": float(acc[1].mean() / acc[30].mean()),
                         "ratio_upper95": upper, "bar": B3_RATIO,
                         "pass": upper <= B3_RATIO}

    sub = {lab: np.array([u["subday"][lab]["e_accept"] for u in units])
           for lab in SUBDAY_DELTAS}
    smeans = [float(sub[lab].mean()) for lab in SUBDAY_DELTAS]
    sgain, sse = _paired(sub["1h"], sub["1d"])
    out["bars"]["B4"] = {
        "means": dict(zip(SUBDAY_DELTAS, smeans)),
        "non_decreasing": _increasing(smeans, strict=False),
        "diff_1d_minus_1h": sgain, "se": sse,
        "void": not out["mc"]["MC4"]["ok"],
        "pass": _increasing(smeans, strict=False) and sgain > SE_BAR * sse}

    if void:
        out["verdict"] = "VOID"
    else:
        ok = all(out["bars"][b]["pass"] for b in ("B1", "B2", "B3"))
        out["verdict"] = "PASS" if ok else "FAIL"
    dest = ROOT / "results" / "rpki-rov-staleness.json"
    dest.write_text(json.dumps(out, indent=1))
    print(json.dumps({"verdict": out["verdict"],
                      **{b: out["bars"][b]["pass"] for b in out["bars"]}}))
    print(f"-> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
