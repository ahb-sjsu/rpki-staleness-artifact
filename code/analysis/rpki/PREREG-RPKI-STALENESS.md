# PREREG-RPKI-STALENESS — the witness supply-chain cell

**STATUS: SEALED 2026-08-17 01:25 PDT, BY RECORDED OWNER OVERRIDE of
the same-day rule — the program's fifth recorded exception**, with a
mitigation the previous overrides lacked: **the graded bars bind only
to data no eye has touched.** The shakedown
(`results/rpki-staleness-shakedown.json`, committed) examined the
RIPE NCC and ARIN trust anchors and generated the hypothesis; the
bars below grade the union of the three **unseen** trust anchors
(APNIC, LACNIC, AFRINIC), fetched for the first time by the sealed
run. Runner: `staleness_curve.py` (full mode) + this document's
bars, evaluated by `run_sealed_rpki.py`. Results:
`RESULTS-RPKI-STALENESS.md` + `results/rpki-staleness.json`, as
executed.**

## Claim under test

Survey §5: witnesses have supply chains — a relying party acting on
a VRP set synchronized Δ ago is acting on a stale witness, and the
staleness has a measurable price. OT-14 (Third Crucible) earned the
law's shape on the embedding substrate: damage tracks measured
drift, with a floor below which refreshing buys nothing. Prediction,
transferred: **VRP-set divergence grows monotonically in Δ, and
daily refresh holds the dangerous direction (stale authorizations)
under a declared floor.**

## Design

Public data only: `ftp.ripe.net/rpki/<tal>/.../roas.csv.xz`
(routinator daily validation runs, archived). Reference day
T0 = 2026-08-16; Δ ∈ {1, 2, 4, 8, 15, 30} days. A VRP is
(ASN, prefix, maxLength); per-Δ grading of the stale set against T0:
**removed_frac** (stale authorizations still trusted — the dangerous
direction) and **added_frac** (missing coverage).

## Manipulation checks (any failure → VOID)

- MC1: all files fetch and parse; every unseen TA holds > 1,000 VRPs
  at T0.
- MC2 (disclosure): the RIPE NCC and ARIN curves were seen at
  shakedown and are REPORTED only; no bar may reference them.

## Bars (graded on the unseen union: APNIC + LACNIC + AFRINIC)

- **B1 (the OT-14 shape on untouched data):** removed_frac and
  added_frac each strictly monotone in Δ across the six-point grid
  (Spearman = 1.0; with six points and no ties this is exact
  monotonicity).
- **B2 (the daily-refresh floor):** removed_frac at Δ = 1 day
  ≤ 0.002 — daily synchronization holds stale-authorization exposure
  under 0.2%.

**PASS = B1 ∧ B2** (given no VOID); any bar failing → FAIL as
executed. Reported ungraded: per-TA strata including ARIN's
event-dominated non-monotone curve (the reason per-TA monotonicity
is not barred — the OT-13 lesson), the all-TA pooled curve, and the
removed/added asymmetry (the RPKI grows, so missing-coverage
dominates stale-authorization).
