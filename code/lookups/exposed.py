"""Read-only: who the wrong accepts at 1 d and 30 d are, from the graded records."""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

U = [json.loads(p.read_text()) for p in sorted(Path(sys.argv[1]).glob("rov-unit-*.json"))]
mean_peers = sum(u["daily"]["1"]["weighted"]["peer_total"] / u["n"] for u in U) / len(U)
print(f"mean peers per announcement over days: {mean_peers:.1f}")
for age in ("1", "30"):
    flips = [(u["t0"], *f) for u in U for f in u["daily"][age]["accept_flips"]]
    days = defaultdict(set)
    for t0, p, o, tr, npeer in flips:
        days[(p, o)].add(t0)
    rec = Counter(len(v) for v in days.values())
    trs = Counter(tr for _, _, _, tr, _ in flips)
    v6 = sum(1 for _, p, *_ in flips if ":" in p)
    peers = [f[4] for f in flips]
    origins = Counter(o for (p, o) in days)
    print(f"\n== age {age} d: {len(flips)} flips over 8 days, {len(days)} distinct (prefix, origin)")
    print("days per distinct pair:", dict(sorted(rec.items())))
    print("transitions:", dict(trs), "| v6 share", round(v6 / len(flips), 3))
    print(f"peers per flip: median {median(peers)}, max {max(peers)}, "
          f"share with <= 5 peers {sum(1 for x in peers if x <= 5) / len(peers):.3f}")
    print("distinct origins:", len(origins), "| top origins by distinct pairs:",
          origins.most_common(10))
    top_o = origins.most_common(10)
    print("share of distinct pairs from top 10 origins:",
          round(sum(c for _, c in top_o) / len(days), 3))
    print("top by peers:")
    for f in sorted(flips, key=lambda f: -f[4])[:8]:
        print("  ", f)
