# rpki-staleness-artifact

Evidence for **"How Stale Is Too Stale? Route Origin Validation Errors of Lagging RPKI Relying Parties"** (A. H. Bond, submitted to IEEE ICC 2027).

The paper replays the routes seen by three RIPE RIS collectors on eight reference days (the Wednesdays from 2 September to 21 October 2026) against RPKI authorization lists from one hour to thirty days old, and counts the routes a stale list wrongly accepts and wrongly drops. Its tests were written into a preregistration and sealed before any graded day was read. This repository holds that preregistration, the code, the records as executed, and a notebook that recomputes every number in the paper from those records.

## Reproduce the paper

```
pip install -r requirements.txt
jupyter nbconvert --to notebook --execute reproduce.ipynb     # or open it and run all cells
```

Run it from the repository root. `reproduce.ipynb` recomputes each number from `results/` and checks it against the value printed in the paper, one line per number, and its last cell fails if any check does not match. The default run reads only the records and takes under a minute. Its final section reruns one reference day from the public archives when `RUN_RAW = True` (about 1.3 GB of downloads, 1.5 GiB of memory and 30 minutes).

The notebook in this repository was executed on Python 3.12.3 with numpy 2.5.4, matplotlib 3.11.2, pytest 9.1.1 and pybgpkit 0.8.0.

## The preregistration

`code/analysis/rpki/PREREG-RPKI-ROV-STALENESS.md`, sealed 2026-10-25, SHA-256 `3937cea69183efe666370980072ccf3b039bb7fa508fb8c6baab9ef930fe8430`. It sits beside the code because the runners read its `STATUS: SEALED` line and refuse to run a graded day without it (`code/governor/sealed.py`). The earlier payload-list test is `PREREG-RPKI-STALENESS.md` (sealed 2026-08-17).

## Where each part of the paper comes from

| paper | code | record |
|---|---|---|
| Graded verdict, bars B1 to B4, MC1 to MC4 | `run_sealed_rov.py` | `results/rpki-rov-staleness.json`, notes `results/RESULTS-RPKI-ROV-STALENESS.md` |
| Per-day measurements (Table I, Fig. 2) | `rov_unit.py`, figure and table by `code/paper/make_figs.py` | `results/graded/rov-unit-<day>.json` |
| Routinator cross-check (MC3) | `mc3_routinator.py` (needs Docker) | `results/rpki-rov-mc3.json`, `results/graded/mc3.json` |
| 16 September from complete dumps (sensitivity) | `rov_unit.py` on complete local dumps | `results/sensitivity-0916/rov-unit-2026-09-16.json`, regrade `results/rpki-rov-staleness.sens-0916-complete-rib.json` |
| Who is exposed, persistence, attribution (ungraded, declared in the preregistration) | `rov_ungraded.py` | `results/ungraded-v2/` |
| Widely carried one-day wrong accepts | `code/lookups/whatchanged.py` | `results/lookups/whatchanged.txt` |
| Payload-list test (Method) | `staleness_curve.py`, `run_sealed_rpki.py` | `results/rpki-staleness.json`, notes `results/RESULTS-RPKI-STALENESS.md` |
| Exploratory checks added after review | `rov_sensitivity.py`, `rov_bridge.py`, `rov_exposure.py` | `results/review/` |

All code paths are under `code/analysis/rpki/` unless shown.

## Provenance notes

- **The first grading run was VOID.** The copy of the sealed code used for grading had been staged without `tests/`, so MC2 reported no tests. The test file was restored from the seal commit and checked by hash, and the grader was rerun unchanged. Both outputs are kept: `results/rpki-rov-staleness.exec1-void-no-tests.json` and the graded record.
- **16 September rrc00 was read short.** The graded job streamed the dump, and the stream ended early without an error (48.6 of 53.1 million entries, 2,909 of 1,445,840 announcements lost). The day was graded as sealed and recomputed from the complete dumps. The verdict does not change. The ungraded reports read every dump in full and check its gzip CRC first (`rov_ungraded._fetch_rib`).
- **Tests.** `code/tests/test_rpki_rov.py` is byte-identical to the sealed file (SHA-256 `c7d562b0...c1fc5`, 17 tests). `code/tests/test_rov_ungraded.py` holds tests written after the seal, including a test that an AS0 VRP does not override a matching VRP (RFC 6483).
- **A wording error in sealed code.** The docstring of `rov.py` says AS0 VRPs make a prefix Invalid "for every origin". The code itself (`validate_key`) returns Valid when any covering VRP matches, as RFC 6483 requires, and the test above checks it. The sealed file is left unchanged.
- **Persistence.** Five of the 24 later route tables (the +30-day checks for 30 September to 21 October and the +7-day check for 21 October) did not exist when the paper was written.
- **Paths.** `rov-unit` records name the public URLs they read. Lookups and records written on the measurement host are left as executed.

## Data

The measurements use public archives, which are not redistributed here: RIPE RIS RIB dumps (https://data.ris.ripe.net), the RIPE NCC daily RPKI archive (https://ftp.ripe.net/rpki) and RPKIViews snapshots (https://www.rpkiviews.org).

## License

Two licenses, split by what the file is.

| what | license | file |
|---|---|---|
| code (`*.py`, `*.ipynb` code cells) | MIT | `LICENSE` |
| prose, preregistrations, results records and data | CC BY 4.0 | `LICENSE-TEXT` |

The paper itself is not in this repository and is outside both licenses.
