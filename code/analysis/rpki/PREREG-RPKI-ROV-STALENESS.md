# PREREG-RPKI-ROV-STALENESS — what a stale relying party decides wrongly

**STATUS: SEALED 2026-10-25 (owner instruction 2026-10-24: "seal at midnight and launch"). FAMILY-CONSTRUCTED: 2026-10-24.**
The runner (`analysis/rpki/run_sealed_rov.py`, to be written) calls
`governor.sealed.require_seal` and will not grade before this file carries a dated
`STATUS: SEALED` line at least one day after the construction date. Shakedown runs
before the seal carry no evidential weight and are logged below.

## Why this cell exists

PREREG-RPKI-STALENESS (sealed 2026-08-17, PASS) measured the stale witness itself:
a relying party (RP) whose validated ROA payload (VRP) set is Δ days old trusts
VRPs that were since removed (0.015% at 1 day, 1.21% at 30 days on the unseen
union) and lacks VRPs since added (0.056% to 2.04%). That cell graded the VRP set,
not the decisions made with it. A removed VRP that covers no announced route
changes nothing; one that covers a hijack changes everything. This cell grades the
decisions: Route Origin Validation (ROV, RFC 6811) outcomes on real BGP
announcements, stale VRP set against fresh, as a function of Δ.

It is the measurement for the SVCC 2027 paper (`paper/svcc2027-rpki/PLAN.md`).

## Data (public only)

- **VRPs.** `ftp.ripe.net/rpki/<tal>.tal/YYYY/MM/DD/roas.csv.xz`, the RIPE NCC
  routinator daily archive, for all five trust anchors (AFRINIC, APNIC, ARIN,
  LACNIC, RIPE NCC). An RP's view on day d is the **union** over the five TAs on
  day d, as a real RP loads all five. A VRP is (ASN, prefix, maxLength).
- **Announcements.** RIPE RIS RIB dumps `data.ris.ripe.net/<rrc>/YYYY.MM/
  bview.YYYYMMDD.0000.gz` for collectors **rrc00, rrc01, rrc03**, at 00:00 UTC on
  each reference day. An announcement is a distinct (prefix, origin AS) pair seen
  from at least one peer of at least one of the three collectors. Paths whose
  origin is an AS_SET are excluded and counted. IPv4 and IPv6 are both included.

## Design

- **Reference days (graded).** T0 ∈ {2026-09-02, 09-09, 09-16, 09-23, 09-30,
  10-07, 10-14, 10-21}: every Wednesday from 2026-09-02 to 2026-10-21, fixed by
  rule before any of them was opened. Eight days give eight paired replicates.
- **Staleness grid.** Δ ∈ {1, 2, 4, 8, 15, 30} days (as the earlier cell), nominal
  by archive directory date. The archive's capture time drifts within a day, so
  each file's server Last-Modified time is recorded and the effective age is
  reported beside every nominal Δ. Bars are graded on the nominal grid.
- **ROV.** RFC 6811 per announcement (p, o) against a VRP set V: covering VRPs are
  those whose prefix covers p; none → NotFound; any covering VRP with ASN = o
  (o ≠ 0) and len(p) ≤ maxLength → Valid; otherwise Invalid.
- **Decision errors** at (T0, Δ), with fresh = V(T0), stale = V(T0 − Δ), and N
  the number of announcements at T0:
  - **E_accept** = #{(p, o): fresh Invalid, stale not Invalid} / N. A route a
    current drop-invalid router rejects but the stale RP accepts: the attacker's
    window. Reported split: Valid→Invalid (revoked or narrowed authorization) and
    NotFound→Invalid (protection the stale RP has not seen yet).
  - **E_drop** = #{(p, o): stale Invalid, fresh not Invalid} / N. A legitimate
    route the stale RP wrongly drops: the availability cost.
  - Valid↔NotFound changes are counted and reported; under drop-invalid policy
    they change no forwarding decision.

## Sub-day arm (added 2026-10-24 on owner approval, before seal)

The daily archive cannot resolve the lags most RPs actually have (minutes to
hours). The sub-day arm uses a second, independent source with its own validator:

- **Source.** RPKIViews full snapshots from the Amsterdam node
  (`https://josephine.sobornost.net/rpkidata/YYYY/MM/DD/rpki-YYYYMMDDTHHMMSSZ.tgz`,
  about every 20 minutes, rpki-client). The VRPs are the member
  `output/rpki-client.csv`, read from the head of the stream; the rest of the
  archive is not downloaded.
- **Points.** For each graded T0, fresh = the first snapshot at or after T0 00:00
  UTC; stale at Δ ∈ {1 h, 6 h, 1 d} = the latest snapshot whose timestamp is at or
  before (fresh timestamp − Δ). Both sides come from the same node and validator,
  so the arm never mixes sources.
- **Announcements.** The same T0 RIB announcements as the daily arm.

## Manipulation checks (any failure → VOID)

- **MC1 (inputs).** Every VRP file and RIB dump fetches and parses; each TA holds
  more than 1,000 VRPs on every day used; each collector yields more than 500,000
  distinct announcements on every T0.
- **MC2 (validator).** Before grading, the ROV implementation passes a planted
  test suite (RFC 6811 Section 2 cases: exact match, maxLength exceeded, wrong
  origin, AS0, multiple covering VRPs, no cover, IPv4 and IPv6). One failure →
  VOID.
- **MC3 (cross-check).** On the first graded T0 (2026-09-02), the validator's
  Valid/Invalid/NotFound counts for the fresh daily-arm set agree with an
  independent implementation to within 0.1% of announcements per state. The
  independent implementation is Routinator 0.15.2 (`nlnetlabs/routinator:v0.15.2`,
  no network), validating the same announcements in batch (`validate -i`) against
  the same VRP set supplied as SLURM locally added assertions, with every trust
  anchor and fetcher disabled (`analysis/rpki/mc3_routinator.py`). Route-by-route
  disagreements are reported. A probe on 2026-10-24 confirmed this configuration
  reproduces all twelve planted MC2 verdicts.
- **MC4 (sub-day bridge; voids the sub-day arm only).** On every graded T0 the
  fresh-state counts (Valid, Invalid, NotFound) from RPKIViews and from the RIPE
  routinator archive agree within 0.5% of announcements per state. Failure voids
  B4 and leaves B1 to B3 standing.

## Bars (graded on the eight T0s; paired across T0)

Let m_A(Δ), m_D(Δ) be the means over T0 of E_accept and E_drop, and SE their
standard errors over the eight T0s.

- **B1 (exposure grows with staleness).** m_A is strictly increasing over the Δ
  grid (Spearman 1.0 on six points) **and** the paired difference
  E_accept(30) − E_accept(1) exceeds 4 SE of that difference.
- **B2 (availability cost grows with staleness).** The same two conditions for
  E_drop.
- **B3 (the daily-refresh floor, relative).** The 95% upper bootstrap bound
  (10,000 resamples over T0) of the ratio m_A(1) / m_A(30) is at most 0.10: daily
  refresh removes at least 90% of a month-stale RP's exposure.

- **B4 (sub-day exposure is smaller, on the sub-day arm).** m_A is non-decreasing
  over {1 h, 6 h, 1 d} **and** the paired difference E_accept(1 d) − E_accept(1 h)
  exceeds 4 SE of that difference.

**PASS = B1 ∧ B2 ∧ B3** given no VOID, with B4 graded and reported on its own (a
VOID of the sub-day arm by MC4 is reported as such); any bar failing → FAIL as
executed, and reported.

## Reported ungraded

Per-collector and per-TA attribution of flips; IPv4 against IPv6; the
Valid→Invalid and NotFound→Invalid split of E_accept; absolute counts, not only
fractions; E_accept and E_drop weighted by address space and by the number of RIS
peers that carry each announcement; persistence (how many E_accept announcements are still present 1, 7
and 30 days after T0); the fraction of fresh-Invalid announcements at T0 (the
baseline the errors sit on); and a mapping from published RP-staleness
distributions (related-work survey) to expected exposure.

## Disclosure

- The VRP files for 2026-07-17, 08-01, 08-08, 08-12, 08-14, 08-15 and 08-16 were
  opened by PREREG-RPKI-STALENESS for set divergence only. Some stale inputs here
  (T0 − Δ for early T0s) fall near those dates. No ROV decision and no RIB dump
  has been computed or opened on any date before this draft.
- 2026-10-24, while scoping the sub-day arm: the RPKIViews directory for
  2026-09-02 (a graded day) was listed and the member names of one archive
  (`rpki-20260902T000621Z.tgz`) were read. No VRP content was read and no ROV
  decision was computed.
- Shakedown uses **T0 = 2026-08-20 on rrc00 only**, which is not a graded day. Its
  numbers may set expectations of scale. They may not be used to set or move any
  bar in this file.

## Shakedown log

All runs below used T0 = 2026-08-20, which is not a graded day. None of their
numbers set or moved a bar.

- 2026-10-24, run 1 (rrc00 only, first version of `rov_unit.py`). Completed. Peak
  RSS about 10 GB, from per-announcement sets of (collector, peer) tuples. Fixed by
  per-key peer counters, a per-collector bitmask and integer prefix keys. No change
  to any metric definition.
- 2026-10-24, run 2 (footprint measurement under `/usr/bin/time -v`). Deviation
  from the line above: this run used all three graded collectors (rrc00, rrc01,
  rrc03) and the sub-day arm, because the NRP sizing veto needs the footprint of
  the unit as it will run. Peak RSS 0.97 GiB, 84% of one CPU, 27 min wall. These
  values are in `footprints.json` and size the NRP request (1 CPU, 2 GiB).
- 2026-10-24, MC3 trial (Routinator 0.15.2 on the 2026-08-20 announcements). Two
  tooling failures, both in `mc3_routinator.py` and neither in the validator under
  test: a relative Docker volume path, and a work directory the container user
  could not write. Both fixed. The planted 12-case probe matched Routinator on
  every verdict. The full trial was still running at seal time; its outcome is not
  a criterion and will be reported with the graded MC3.
- Unit tests (`tests/test_rpki_rov.py`) pin `rov_unit._errors` to
  `rov.decision_errors` and the RFC 6811 planted cases. CI green before seal.
