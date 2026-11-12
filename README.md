# wise-pm-library

WISE provides norm-based process scoring and investigation priorities. This repository accompanies *WISE: Actionable Norm-Based Scoring for Process Mining* by Urszula Jessen, Dirk Fahland and Francesca Zerbato.

WISE (Weighted Insights for Evaluating Efficiency) assesses recorded process execution against explicit business requirements. A **process norm** states the requirements as constraints grouped into layers; a **view** weights the constraints from one stakeholder perspective; every case receives a score from bounded deviation scores; groups of cases (slices) are ranked by the **Priority Index**, the positive gap between the mean score of all scored cases and the slice mean score, scaled by the number of scored cases or by business exposure. Every priority stays linked to the layers, constraints and cases behind it.

The repository contains

- **the method** as a small Python package, `wise`,
- **the evaluation notebook**, [WISE on the BPIC 2019 purchase-to-pay log](notebooks/WISE_BPIC19_Evaluation_Story.ipynb), which is the place to start,
- **additional dataset tests**: reference assessments of three public logs with expected values, and analysis notebooks for eight further BPI Challenge logs.

## Install

Python 3.11 or newer. The package needs NumPy and pandas; Matplotlib and Jupyter are optional extras for the figures and the notebooks.

```sh
git clone https://github.com/feelfine1977/wise-pm-library.git
cd wise-pm-library
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install ".[notebook,test]"
```

Extras: `figures` (Matplotlib), `notebook` (Matplotlib and Jupyter), `test` (pytest). The import name is `wise`. The full library `wise-pm` uses the same import name, so install the two in separate environments.

## The evaluation notebook

[`notebooks/WISE_BPIC19_Evaluation_Story.ipynb`](notebooks/WISE_BPIC19_Evaluation_Story.ipynb) applies WISE to the BPI Challenge 2019 purchase-to-pay log and tells the evaluation step by step:

| Section | Content |
|---|---|
| 0 | The story as a graph |
| 1 | What is evaluated: the company's question and the evaluation questions |
| 2 | WISE in brief: process norm, constraints, deviation score, layers, views, case score, slices, Priority Index |
| 3 | The data |
| 4 | Step 1: a norm from the process owner's words, what the layers mean, first assessment |
| 5 | Step 2: the refined norm, payment time as a measurement, one combined ranking |
| 6 | Step 3: one Priority Index per layer, the slice by layer table, two combined views |
| 7 | Findings and what they mean for the company |
| 8 | Checks: slicing scheme, sensitivity to assessment settings, drill-down to the recorded events |
| 9 | Close: answers, next steps for the company, what stays open |

The notebook is saved with its outputs and can be read without running it. [EVALUATION.md](EVALUATION.md) summarises its questions, norms, results and findings. The norms are defined in the notebook itself, so every constraint can be read where it is used; the functions it calls are in [`notebooks/wise_story.py`](notebooks/wise_story.py). Its last cell compares the numbers quoted in the text with the computed values and stops with an error if one differs.

To run it, supply the BPI Challenge 2019 log as described under [Data](#data), then:

```sh
cd notebooks
jupyter notebook WISE_BPIC19_Evaluation_Story.ipynb
```

Run all cells from top to bottom. A full run takes a few minutes.

## The method in a few lines

```python
import wise

log = wise.running_p2p_log()            # the five illustrative cases of the running example
norm = wise.running_p2p_norm()          # its norm, with the views Finance and Logistics
result = wise.score(log, norm)          # violations, scope, scores, layer contributions
print(result.scores.round(4))
print(result.coverage("Finance"))       # weighted evidence coverage

backlog = wise.prioritize(result, by="company", view="Finance")
print(backlog.table)                    # the prioritised investigation list
print(wise.layer_contributions(result, backlog))   # signed layer contributions to the gap
```

A smaller illustration (four invoice cases, two views, each of which puts another slice first) is `wise.illustrative_invoice_log()` with `wise.illustrative_invoice_norm()`.

For your own data, pass a pandas DataFrame to `wise.EventLog` with its case, activity and timestamp columns and the case attributes, and build a `wise.Norm` or load one from JSON with `wise.Norm.load(...)`.

## Data

No event log is part of this repository. Put the logs you need into one folder, under any sub-folders, and name that folder in the environment variable `WISE_PAPER_DATA`. The evaluation notebook also looks into a folder `notebooks/data`.

| Log | Used by | Source and identifier | File | Bytes | SHA-256 |
|---|---|---|---|---:|---|
| BPI Challenge 2019 | evaluation notebook; additional tests | 4TU.Centre for Research Data, [doi:10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1](https://doi.org/10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1); the CSV export is linked from the [challenge page](https://icpmconference.org/2019/icpm-2019/contests-challenges/bpi-challenge-2019/) as `BPIChallenge2019CSV.zip` | `BPI_Challenge_2019.csv` | 527,457,189 | `7d592fb425690d13011d1b874fe2af63f61a66acfc368ecf87b4ed266e6cdb00` |
| BPI Challenge 2013, incidents | additional tests | Ghent University, [doi:10.4121/uuid:500573e6-accc-4b0c-9576-aa5468b10cee](https://doi.org/10.4121/uuid:500573e6-accc-4b0c-9576-aa5468b10cee) | `BPI_Challenge_2013_incidents.xes.gz` | 1,322,247 | `6ec2136c607648608655802486df97a866f351668751b7ecbca51e1f8715d522` |
| BPI Challenge 2017 | additional tests | Eindhoven University of Technology, [doi:10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b](https://doi.org/10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b) | `BPI Challenge 2017.xes.gz` | 29,658,747 | `183c5e5189282779c811c78c33ff936351b3dd201165d612211fc220936f8249` |

For BPI Challenge 2019 use the CSV export (1,595,923 rows), not the XES file: extract `BPI_Challenge_2019.csv` from the archive `BPIChallenge2019CSV.zip` (36,720,297 bytes, SHA-256 `372b5a15c30f4a21b370db25b1912cc60ad1104d4198cfd34f8aecb2f4c2425a`). A file is read only if its SHA-256 matches. The other two logs are read as the gzip-compressed XES files as published.

Check the folder:

```sh
python scripts/verify_data.py --data <folder>
```

The logs keep the terms of their publishers; the licence of this repository covers its code and configurations only. The `.gitignore` keeps `data/` folders, logs and generated outputs out of the repository.

## Additional dataset tests

These parts test the library on further data. They are separate from the evaluation notebook and use their own norms.

### Reference assessments of three logs

The subpackage `wise.evaluation` holds reference assessments of BPI Challenge 2019, BPI Challenge 2013 (incidents) and BPI Challenge 2017: a domain adapter with its configuration for each log, the serialised norms, and expected values recorded with version 1.0.0 of this library. They serve as regression tests of scoring, prioritisation and layer contributions on real logs. [`tests/evaluation/EXPECTED_VALUES.md`](tests/evaluation/EXPECTED_VALUES.md) lists every expected value beside the computed one, with the result-item numbering of that version. The purchase-to-pay norm used here has ten criteria and differs from the norms of the evaluation notebook.

Everything at once: prints every expected value beside the computed one, and writes `comparison.csv`, `summary.csv`, one calculation record per log and three figures to the output folder. The command exits with status 1 if a value differs, a numerical check fails or a required input is missing.

```sh
python scripts/evaluate_paper.py --data <folder> --output outputs
```

In Python, one function per result item:

```python
from wise.evaluation import paper

paper.compare("<folder>")                 # every expected value, the computed value, agreement
paper.item_17_layer_contributions("<folder>")
paper.calculation_record("bpic2019", "<folder>")
```

Numerical checks: the library's scoring and aggregation are compared with a reference arithmetic on the same prepared assessments, for three views per log, flat and layer-balanced scoring, each at γ = 0 and γ = 20. The case scores are also computed again with the cases in another order, with the norm serialised and read back, and with the whole-case context attached, and must be unchanged.

```sh
python scripts/replay_native.py --data <folder> [--output <folder>]
```

How these assessments are computed: a domain adapter interprets the source records of a log and produces, for every case and criterion, a deviation value in [0, 1], a business-scope flag and an evidence state, together with the group of the case. The library then scores these prepared assessments through its public interfaces. The criteria, thresholds and view weights are illustrative choices made by the researchers.

### Analysis notebooks for further BPI Challenge logs

[`notebooks/additional_datasets/`](notebooks/additional_datasets) has one notebook per challenge. Each follows the stages of PM² from the business question through source checks, measured deviations and case evidence to proposals for a process-improvement pilot. They are saved without outputs and read their logs from the folder named by `WISE_PAPER_DATA`.

| Challenge | Process | Notebook |
|---|---|---|
| 2011 | Hospital patient histories | [BPIC2011_Healthcare_Analysis](notebooks/additional_datasets/BPIC2011_Healthcare_Analysis.ipynb) |
| 2012 | Loan applications | [BPIC2012_Lending_Analysis](notebooks/additional_datasets/BPIC2012_Lending_Analysis.ipynb) |
| 2013 | Incidents and problems | [BPIC2013_Incidents_Extended](notebooks/additional_datasets/BPIC2013_Incidents_Extended.ipynb) |
| 2014 | Service restoration | [BPIC2014_Service_Analysis](notebooks/additional_datasets/BPIC2014_Service_Analysis.ipynb) |
| 2015 | Building permits | [BPIC2015_Permits_Analysis](notebooks/additional_datasets/BPIC2015_Permits_Analysis.ipynb) |
| 2017 | Loan applications | [BPIC2017_Lending_Extended](notebooks/additional_datasets/BPIC2017_Lending_Extended.ipynb) |
| 2018 | Agricultural grants | [BPIC2018_Grants_Analysis](notebooks/additional_datasets/BPIC2018_Grants_Analysis.ipynb) |
| 2020 | Travel administration | [BPIC2020_Travel_Analysis](notebooks/additional_datasets/BPIC2020_Travel_Analysis.ipynb) |

The helper `bpic_analysis.py` and the dataset specification `bpic_datasets.json` in the same folder declare sources, norms, views and case attributes. Each dataset has its own norm; its scores and priorities should be interpreted within that assessment. Diagnostic cut points require process-owner review; they are not inferred service agreements.

## Tests

Unit tests of the method and constructed contract tests need no data. The dataset test compares each computed result of the reference assessments with its expected value and is skipped, with a message that says why, when a log is not supplied.

```sh
python -m pytest                                            # without the logs
WISE_PAPER_DATA=<folder> python -m pytest                   # with the logs
```

## What is in this repository

```
src/wise/                     the method
  constraints.py, family.py, families/   presence, lag, balance, occurrence limit, exclusion; metric on a case attribute
  selection.py                applicability rules (business scope), three-valued
  norm.py, norm_document.py   process norm, layers, views; the JSON document format and the fingerprint
  log.py, case_index.py       the event log and its case-level primitives
  scoring.py                  violations, scope, case scores (flat and layer-balanced), layer contributions, coverage
  prioritization.py, backlog.py   Priority Index, small-slice adjustment, exposure scaling, signed layer contributions
  datasets.py                 the running example and a smaller illustration
src/wise/evaluation/          reference assessments of three logs (additional tests)
  adapters/, norms/native/    domain adapters with their configurations; serialised norms
  data_catalog.json, data.py  input catalogue: source identities and input hashes; verification
  reference.py, replay.py     reference arithmetic; replay with the numerical checks
  paper.py, figures.py        one function per result item and figure; comparison with the expected values; calculation record
  expected/                   expected values and compact aggregate reference results
scripts/                      evaluate_paper.py, replay_native.py, verify_data.py
notebooks/
  WISE_BPIC19_Evaluation_Story.ipynb   the evaluation notebook
  wise_story.py                        functions used by it
  additional_datasets/                 analysis notebooks for eight further BPI Challenge logs
tests/                        unit tests, constructed contract tests (tests/evaluation), dataset test; expected values of the reference assessments
EVALUATION.md                 summary of the evaluation on BPI Challenge 2019
CHANGELOG.md, CITATION.cff, LICENSE
```

Full source logs, complete prepared case assessments and generated output folders are not distributed in the repository.

## What is not included, and the full library

This is a frozen subset. It holds the capabilities the method uses and nothing else. The living library is [`wise-pm`](https://github.com/feelfine1977/wise-pm); it continues beside this repository with its own version line and offers, among other things, derived case attributes, further constraint options, diagnostics, a command-line interface and further evaluation configurations.

The code of this repository was derived from `wise-pm`: the method modules from the development line that follows its version 0.1.0, the adapters, configurations and reference arithmetic from its evaluation directory (commit `52cc4b2e9a3c94ec6f8e8ba5874f220a3155f484`). Where the two differ in behaviour, [CHANGELOG.md](CHANGELOG.md) says so. On the shared capabilities the two give identical results; norm documents written here (schema version 3) can be read by `wise-pm` from version 0.2.0 on.

## Licence and citation

MIT, see [LICENSE](LICENSE). If you use this software, please cite the paper and the software; [CITATION.cff](CITATION.cff) has the details.
