# wise-pm-library

WISE provides norm-based process scoring, investigation priorities and the evaluation used in *WISE: Actionable Norm-Based Scoring for Process Mining* by Urszula Jessen, Dirk Fahland and Francesca Zerbato.

WISE (Weighted Insights for Evaluating Efficiency) assesses recorded process execution against explicit business rules. A **process norm** states the rules as constraints grouped into layers; a **view** weights the constraints from one stakeholder perspective; every case receives a score from bounded deviation values; groups of cases (slices) are ranked by the **Priority Index**, the positive gap between the population mean score and the slice mean score, scaled by the number of scored cases or by business exposure. Every priority stays linked to the layers, constraints and cases behind it.

This repository accompanies the paper. It contains

- the method as a small Python package, `wise` (Section 4 of the paper),
- the evaluation of the paper, `wise.evaluation`: the three applications of Section 5 with their adapters, configurations, norms and expected values,
- one function per result item, table and figure of the paper, a command that prints every computed value beside the printed one and writes a calculation record per application, notebooks, and tests.

Version **1.0.0** contains the method and evaluation settings used in the October 2026 paper; see [CHANGELOG.md](CHANGELOG.md). [Evaluation results](EVALUATION.md) lists the reported and computed values. The [notebook guide](notebooks/README.md) covers the numerical checks, Figures 4–6 and further analysis of each dataset.

## Install

Python 3.11 or newer. The package needs NumPy and pandas; Matplotlib and Jupyter are optional extras for the figures and the notebook.

```sh
git clone https://github.com/feelfine1977/wise-pm-library.git
cd wise-pm-library
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install ".[notebook,test]"
```

Extras: `figures` (Matplotlib), `notebook` (Matplotlib and Jupyter), `test` (pytest). The import name is `wise`. The full library `wise-pm` uses the same import name, so install the two in separate environments.

## The method in a few lines

```python
import wise

log = wise.running_p2p_log()            # the five illustrative cases of Table 4
norm = wise.running_p2p_norm()          # the norm of Table 3, views Finance and Logistics
result = wise.score(log, norm)          # violations, scope, scores, layer contributions
print(result.scores.round(4))           # Table 4
print(result.coverage("Finance"))       # weighted evidence coverage

backlog = wise.prioritize(result, by="company", view="Finance")
print(backlog.table)                    # the prioritised investigation list
print(wise.layer_contributions(result, backlog))   # signed layer contributions to the penalty gap
```

The smaller illustration of Section 3 (Figure 2: four invoice cases, two views, each of which puts another slice first) is `wise.illustrative_invoice_log()` with `wise.illustrative_invoice_norm()`.

For your own data, pass a pandas DataFrame to `wise.EventLog` with its case, activity and timestamp columns and the case attributes, and build a `wise.Norm` or load one from JSON with `wise.Norm.load(...)`.

## Data

No event log is part of this repository. The evaluation reads three public logs. Put them into one folder, under any sub-folders; a file is found by its name and is read only if its size and SHA-256 match the input catalogue ([`src/wise/evaluation/data_catalog.json`](src/wise/evaluation/data_catalog.json)).

| Log | Source and identifier | File | Bytes | SHA-256 |
|---|---|---|---:|---|
| BPI Challenge 2019 | 4TU.Centre for Research Data, [doi:10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1](https://doi.org/10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1); the CSV export is linked from the [challenge page](https://icpmconference.org/2019/icpm-2019/contests-challenges/bpi-challenge-2019/) as `BPIChallenge2019CSV.zip` | `BPI_Challenge_2019.csv` | 527,457,189 | `7d592fb425690d13011d1b874fe2af63f61a66acfc368ecf87b4ed266e6cdb00` |
| BPI Challenge 2013, incidents | Ghent University, [doi:10.4121/uuid:500573e6-accc-4b0c-9576-aa5468b10cee](https://doi.org/10.4121/uuid:500573e6-accc-4b0c-9576-aa5468b10cee) | `BPI_Challenge_2013_incidents.xes.gz` | 1,322,247 | `6ec2136c607648608655802486df97a866f351668751b7ecbca51e1f8715d522` |
| BPI Challenge 2017 | Eindhoven University of Technology, [doi:10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b](https://doi.org/10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b) | `BPI Challenge 2017.xes.gz` | 29,658,747 | `183c5e5189282779c811c78c33ff936351b3dd201165d612211fc220936f8249` |

The BPIC'19 adapter reads the CSV export of the challenge (1,595,923 rows), not the XES file: extract `BPI_Challenge_2019.csv` from the archive `BPIChallenge2019CSV.zip` (36,720,297 bytes, SHA-256 `372b5a15c30f4a21b370db25b1912cc60ad1104d4198cfd34f8aecb2f4c2425a`). No conversion from the XES file is provided; another export would need its own reviewed adapter configuration. The two other adapters read the gzip-compressed XES files as published.

Check the folder before a run:

```sh
python scripts/verify_data.py --data <folder>
```

The logs keep the terms of their publishers; the licence of this repository covers its code and configurations only. The `.gitignore` keeps a local `data/` folder, logs and generated outputs out of the repository.

## Run the evaluation

The data folder is passed as `--data`, as the argument `data` of the Python functions, or once through the environment variable `WISE_PAPER_DATA`.

**Everything at once.** Prints every printed value of the paper beside the computed one and a summary per result item, and writes `comparison.csv`, `summary.csv`, one calculation record per application and Figures 4 to 6 (PDF and PNG) to the output folder:

```sh
python scripts/evaluate_paper.py --data <folder> --output outputs
```

Runtime depends on the machine and source files. The command exits with status 1 if a computed value differs from a printed one, a numerical check fails or a required input is missing.

**Calculation records.** For each application the command writes `calculation_record_<application>.json` into the output folder (`calculation_record_bpic2019.json`, `calculation_record_bpic2013_incidents.json`, `calculation_record_bpic2017.json`; in Python: `paper.calculation_record("<application>", "<folder>")`). A record identifies what Appendix B.2 of the paper lists for a calculation record: the source export (file name, size, SHA-256, numbers of events and cases), the adapter configuration and its SHA-256, the norm with its fingerprint, the tested settings (views with their weights, scoring modes, values of γ, grouping, comparison reference, tie order), evidence summaries (per criterion the cases in scope, evaluated, outside scope and unavailable by reason), the ordered results (the ranked groups of every view) and the numerical checks (every difference against the reference arithmetic, equality of scope and evidence states, and the three further checks described below). A record holds aggregates and identities only: no case of a log and no path of the machine it was written on. Records are not distributed with the repository: the output folder is not part of it, and each run writes them anew.

**In Python**, one function per result item, table and figure:

```python
from wise.evaluation import paper

paper.compare("<folder>")                 # every printed value, the computed value, agreement
paper.item_14_packaging("<folder>")       # mean penalty, scored items, gap and Priority Index of Packaging
paper.item_17_layer_contributions("<folder>")
paper.figure_4("<folder>")                # a Matplotlib figure in the design of the printed one
paper.table_b1()                          # the ten criteria of the purchase-to-pay norm
paper.item_41_illustration()              # the illustration of Section 3; needs no log
```

**The notebooks.** `notebooks/` holds the paper's notebook, which walks through the evaluation in the order of the paper and shows each computed value beside the printed one, and further analysis notebooks. The paper's notebook calls the functions above; no result of the paper is computed only inside a notebook.

**The tests.** Unit tests of the method and constructed contract tests of the evaluation need no data. The dataset evaluation test compares each computed result with the expected values and is skipped, with a message that says why, when a log is not supplied:

```sh
python -m pytest                                            # without the logs
WISE_PAPER_DATA=<folder> python -m pytest                   # with the logs: every result item of the paper
```

**The numerical checks of Section 5.6.** The library's scoring and aggregation are compared with the reference arithmetic on the same prepared criterion assessments, for three views in each of the three applications: nine primary view evaluations and eighteen mode–view combinations across flat and layer-balanced scoring, each at γ = 0 and γ = 20:

```sh
python scripts/replay_native.py --data <folder> [--output <folder>]
```

The command prints one line per application and one with the totals; with `--output` it writes a verification file `<application>.json` with every difference for each application. The constructed tests that Section 5.6 names (deviation values after shuffling the rows of the event table; case scores after serialising and reloading a norm) are in `tests/test_invariants.py`, and `paper.item_42_constructed_checks()` makes them on the two bundled examples.

Beyond what the paper states, the same command makes three further checks on each application: the case scores are computed again with the complete cases in another order, with the norm serialised and read back, and with the whole-case context attached, and must be unchanged. The whole-case context of an application is the set of attributes of its case table that describe the complete case and allow other groupings of the same scored cases: purchasing document, vendor and matching flow for BPIC'19, the product for the incidents, application type and loan goal for the loan applications. Attaching it adds these attributes to the cases; no criterion reads them. Reordering moves complete cases: a case is one record of the prepared assessment, so all its values move together. The dataset evaluation test makes these checks for each application as well.

### What agrees

The paper has 38 result items: 35 numeric or textual results and 3 figures, with 259 printed values. Every computed value agrees with the printed one at the printed precision; [Evaluation results](EVALUATION.md) lists them, says which printed statements are not compared, and which of the values are input checks that cannot differ. The item numbers are stable and have gaps: a number is not reused when the paper drops a result.

One printed value is compared by its order of magnitude and not by its digits: the largest absolute difference of the consistency check of Section 5.6 (printed as approximately 1.73 × 10⁻¹¹). It is a floating-point residual between two implementations of the same sums, and its digits depend on the machine and on the versions of NumPy and pandas. What is asserted is that it is below the declared tolerance of 10⁻⁸ and of the printed order.

The figures are drawn by `wise.evaluation.figures` from the computed values, in the design of the printed figures (size, type, axes, ticks, labels, legend wording, number formats).

## What is in this repository

```
src/wise/                     the method (paper Section 4)
  constraints.py, family.py, families/   presence, lag, balance, occurrence limit, exclusion; metric on a case attribute
  selection.py                applicability rules (business scope), three-valued
  norm.py, norm_document.py   process norm, layers, views; the JSON document format and the fingerprint
  log.py, case_index.py       the event log and its case-level primitives
  scoring.py                  violations, scope, case scores (flat and layer-balanced), layer contributions, coverage
  prioritization.py, backlog.py   Priority Index, small-slice adjustment, exposure scaling, signed layer contributions
  datasets.py                 the running example of Tables 3 and 4; the illustration of Section 3 (Figure 2)
src/wise/evaluation/          the evaluation of the paper (Section 5, Appendix B)
  adapters/                   domain adapters and their configurations: bpic2019, bpic2013 (incidents), bpic2017
  norms/native/               serialised native norms of the three applications
  data_catalog.json, data.py  input catalogue: source identities and input hashes; verification
  native.py                   carrier log and identity metric constraints for prepared assessments
  reference.py, replay.py     reference arithmetic; replay with the numerical checks of Section 5.6
  paper.py, figures.py        one function per result item, table and figure; comparison with the printed values; calculation record
  evaluate.py, reference_tables.py   the evaluation command; compact aggregate reference tables
  expected/                   printed values of every result item; compact aggregate reference results
scripts/                      evaluate_paper.py, replay_native.py, verify_data.py
notebooks/                    the paper's notebook and further analysis notebooks
tests/                        unit tests, constructed contract tests (tests/evaluation), dataset evaluation test
```

Not part of the repository: the raw logs, prepared case assessments, source records of individual cases, and what a run writes into the output folder (comparison tables, calculation records, figures).

### How the applications are computed

A domain adapter interprets the source records of a log and produces, for every case and criterion, a deviation value in [0, 1], a business-scope flag and an evidence state, together with the group of the case. In the terms of Section 4.2 of the paper, the adapter supplies bounded case-level assessment functions whose business scope, input evidence, calculation and treatment of missing observations are specified in its code and configuration. The library then scores these prepared assessments through its public interfaces: each prepared value is preserved by an identity `Metric` constraint with threshold zero and width one, and the carrier log has one assessment record per case and a placeholder timestamp. The carrier does not reconstruct the original process trace. The consistency check therefore covers scoring, aggregation and explanations after adaptation; how an adapter reads the source records is defined by its code and configuration and is tested on constructed records in `tests/evaluation`.

The criteria, thresholds and view weights of the three applications are illustrative choices made by the researchers. Priorities order investigations; they are not estimates of financial loss, achievable savings or causal effects.

## What is not included, and the full library

This is a frozen subset. It holds the capabilities the paper's method and evaluation use and nothing else. The living library is [`wise-pm`](https://github.com/feelfine1977/wise-pm); it continues beside this repository with its own version line and offers, among other things, derived case attributes, further constraint options, diagnostics, a command-line interface and further evaluation configurations.

The code of this repository was derived from `wise-pm`: the method modules from the development line that follows its version 0.1.0, the adapters, configurations and reference arithmetic from its evaluation directory (commit `52cc4b2e9a3c94ec6f8e8ba5874f220a3155f484`). Everything the paper does not use was left out. Where the two differ in behaviour, [CHANGELOG.md](CHANGELOG.md) says so. On the shared capabilities the two give identical results; norm documents written here (schema version 3) can be read by `wise-pm` from version 0.2.0 on.

## Licence and citation

MIT, see [LICENSE](LICENSE). If you use this software, please cite the paper and the software; [CITATION.cff](CITATION.cff) has the details.
