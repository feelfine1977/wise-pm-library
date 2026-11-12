# WISE on the BPIC 2019 purchase-to-pay log

`WISE_BPIC19_Evaluation_Story.ipynb` applies WISE to the BPI Challenge 2019 event log and tells the evaluation step by step: what the process owner asks, how the requirements become a norm, what each assessment shows, how the norm is refined, where the deviations concentrate, what the findings mean for the company, and how robust they are.

The notebook is saved with its outputs and can be read without running it.

## Contents

| File | Purpose |
| --- | --- |
| `WISE_BPIC19_Evaluation_Story.ipynb` | The notebook |
| `wise_story.py` | Functions used by the notebook: reading the log, assessment, score, Priority Index, figures |
| `requirements.txt` | Python packages |
| `data/` | Place for the event log (not included) |

## Data

The notebook uses the CSV version of the BPI Challenge 2019 event log.

van Dongen, B.F.: Dataset BPI Challenge 2019. 4TU.Centre for Research Data. https://doi.org/10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1

Download the CSV and save it as `data/BPI_Challenge_2019.csv`. To use a file in another place, set the environment variable `BPIC19_CSV` to its path. The notebook checks the SHA-256 of the file before it starts:

```
7d592fb425690d13011d1b874fe2af63f61a66acfc368ecf87b4ed266e6cdb00
```

## Run

Python 3.10 or newer.

```bash
python -m pip install -r requirements.txt
```

```bash
jupyter notebook WISE_BPIC19_Evaluation_Story.ipynb
```

Run all cells from top to bottom. A full run takes a few minutes.

## Structure of the notebook

| Section | Content |
| --- | --- |
| 0 | The story as a graph |
| 1 | What is evaluated: the company's question and the evaluation questions |
| 2 | WISE in brief: process norm, constraints, deviation score, layers, views, case score, slices, Priority Index, and the terms this evaluation adds |
| 3 | The data |
| 4 | Step 1: a norm from the owner's words, what the layers Flow, Value and Invoice rework mean, first assessment, what it shows about the norm |
| 5 | Step 2: the refined norm, payment time as a measurement, one combined ranking |
| 6 | Step 3: one Priority Index per layer (single-layer views), the slice by layer table, two combined views |
| 7 | Findings and what they mean for the company |
| 8 | Checks: slicing scheme, sensitivity to assessment settings, drill-down to the recorded events |
| 9 | Close: answers, next steps for the company, what stays open |

The norms are defined in the notebook itself, so every constraint can be read where it is used. The last cell compares the numbers quoted in the text with the computed values and stops with an error if one differs.
