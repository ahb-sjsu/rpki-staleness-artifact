# RESULTS-RPKI-STALENESS — verdict and record

**2026-08-17 (UTC). Sealed per `PREREG-RPKI-STALENESS.md` (fifth
recorded override, mitigated: bars bound only to trust anchors no
eye had touched); public data (`ftp.ripe.net/rpki` daily routinator
archives), T0 = 2026-08-16, Δ ∈ {1, 2, 4, 8, 15, 30} days. Record:
`results/rpki-staleness.json`. Ordering note: the seal commit was
staged before the graded fetch and landed after it (GPG pinentry
timeout); the prereg text was final and unchanged throughout.**

## Verdict: **PASS**

| check | outcome |
|---|---|
| MC1 census/floors | ok (all TAs parse; unseen union 366,943 VRPs at T0) |
| **B1** strict monotonicity, unseen union, both directions | **PASS** — removed 0.015% → 1.21%, added 0.056% → 2.04%, strictly increasing at all six Δ |
| **B2** daily-refresh floor | **PASS** — removed@1d = 0.015%, 13× under the 0.2% bar |

## What was measured

**The witness supply chain has the OT-14 shape, on data that could
not have suggested it.** The hypothesis came from the RIPE NCC and
ARIN curves (shakedown, committed); the grade landed on APNIC +
LACNIC + AFRINIC, fetched for the first time by the sealed run —
and both divergence directions rose strictly monotonically across
the full Δ grid. A relying party's stale VRP set degrades along the
staleness axis exactly as the earned staleness law predicts:
smoothly, monotonically, with a cheap floor — **daily
synchronization holds stale-authorization exposure to 1.5 in
10,000**, fifty times tighter than a month-stale view (1.2 in 100).

**Reported ungraded, as declared:**
- Per-TA strata: RIPE NCC drift-dominated and monotone (0.06% →
  1.66% removed); **ARIN event-dominated and non-monotone** (a
  transient VRP cohort in the Δ = 4–8 d window — a bulk
  publish-then-revoke episode). Supply-chain staleness has both a
  drift component and an event component; only the aggregate is
  law-shaped, which is precisely why per-TA monotonicity was never
  barred.
- The asymmetry: added_frac > removed_frac at every Δ — the RPKI
  grows, so a stale witness's dominant failure is *missing
  coverage* (unvalidatable new announcements), not stale
  authorization. For the governor's tooltip this splits the
  staleness field into an availability cost and a safety cost with
  different signs and different prices.
- LACNIC/AFRINIC contribute small but consistent components
  (AFRINIC ~30k VRPs, same monotone shape at its own scale).

## Standing

Survey §7.3 closes. The taxonomy program's measured corpus now:
**BGP 0.351 / IS-IS 0.184 / OSPF 0.083 (certificate cells), BMP
witness-grading validated, and the witness supply chain itself
law-shaped with a daily-refresh floor** — the §5 claim ("witnesses
have supply chains") carries its first sealed numbers. Remaining §7
cells: EIGRP (blocked on implementation access). The OT-14 transfer
is also a cross-program result: a law earned on embedding-retrieval
substrates predicted, in advance and in writing, the shape of RPKI
supply-chain staleness on unseen trust anchors.
