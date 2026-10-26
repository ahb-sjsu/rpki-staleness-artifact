# RESULTS-RPKI-ROV-STALENESS: verdict and record

**Graded 2026-10-25 (UTC) per `PREREG-RPKI-ROV-STALENESS.md`, sealed in e47a7fe.
Eight T0s (2026-09-02 to 2026-10-21, weekly), RIS rrc00, rrc01 and rrc03.
Grader `analysis/rpki/run_sealed_rov.py` at e47a7fe, run on Atlas from the sealed
source copy. Record: `results/rpki-rov-staleness.json`; MC3 record:
`results/rpki-rov-mc3.json`.**

## Verdict: **FAIL** (B3)

| check | outcome |
|---|---|
| MC1 input floors | ok |
| MC2 planted validator tests | ok, 17 passed (see Execution note) |
| MC3 Routinator 0.15.2 cross-check, 2026-09-02 | ok, 1,439,978 announcements, 0 disagreeing, max diff 0.0 |
| MC4 sub-day bridge | ok |
| **B1** wrong accepts rise with age, daily arm | **PASS**: 0.0046% at 1 d to 0.059% at 30 d, strictly increasing; gain 5.8 SE |
| **B2** wrong drops rise with age, daily arm | **PASS**: 0.020% at 1 d to 0.53% at 30 d, strictly increasing; gain 32 SE |
| **B3** daily-refresh floor, m_A(1)/m_A(30) upper 95% bound at most 0.10 | **FAIL**: point 0.079, upper bound 0.105 |
| B4 sub-day arm (graded on its own) | PASS: 0.00006% at 1 h, 0.0010% at 6 h, 0.0043% at 1 d |

Daily refresh removes about 92% of a month-stale relying party's wrong accepts
on average, but the bootstrap over eight weeks cannot place the upper bound of the
ratio under 10%. As executed, the sealed claim of "at least 90%" fails.

## Execution note

The first execution returned **VOID**: MC2 reported "no tests ran", because the
sealed source copy on Atlas (`src-e47a7fe`) had been staged without `tests/`.
Bars were identical to the second execution (B1, B2, B4 pass; B3 fails). The test
file was copied from commit e47a7fe (sha256 c7d562b0...c1fc5), it passed 17 of 17,
and the grader was rerun unchanged. Both outputs are kept:
`results/rpki-rov-staleness.exec1-void-no-tests.json` and the graded record. The
rerun could only move VOID to PASS or FAIL; no data or code changed.

## Disclosed input defect: 2026-09-16 rrc00

The graded unit record for 2026-09-16 read rrc00 from a stream that ended early
without an error (48.6M elements, 1,284,245 distinct pairs). The full dump,
downloaded and gzip-checked, holds 53.1M elements and 1,429,342 pairs. The union
over three collectors lost 2,909 announcements (1,442,931 against 1,445,840). The
other seven days and collectors match independent full reads exactly. MC1 (at
least 500k pairs per collector) did not catch it.

Owner decision 2026-10-25 (option 2): grade as sealed, disclose, and report a
sensitivity check that recomputes 2026-09-16 from the complete dumps with the
sealed `rov_unit.py` and regrades with that record swapped.

**Sensitivity result (2026-10-25): the verdict does not change.** The day was
recomputed with the sealed `rov_unit.py` from complete local copies of all three
dumps (each matched Content-Length and passed gzip -t), and a copy of the graded
set with that one record swapped was regraded by the unchanged grader. Record:
`results/rpki-rov-staleness.sens-0916-complete-rib.json`.

| | sealed grade | 09-16 from complete dumps |
|---|---|---|
| 09-16 announcements | 1,442,931 | 1,445,840 |
| 09-16 wrong accepts at 1 d / 30 d | 32 / 762 | 32 / 766 |
| MC1 to MC4 | ok | ok |
| B1 gain (SE) | 5.83 | 5.83 |
| B2 gain (SE) | 31.8 | 31.9 |
| B3 ratio point / upper 95% | 0.0786 / 0.1051 | 0.0786 / 0.1051 |
| B4 gain (SE) | 5.18 | 5.18 |
| verdict | FAIL | FAIL |

The missing 2,909 announcements held 4 of the day's 766 thirty-day wrong accepts
and 1 of its 7,930 thirty-day wrong drops. B3's upper bound is the same to
every printed digit (0.10512795502719177), and its point estimate moved from
0.078650 to 0.078612.
