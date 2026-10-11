# Evaluation results

Every result item of *WISE: Actionable Norm-Based Scoring for Process Mining* (manuscript of 11 October 2026) with its printed value, the value this library computes, and whether the two agree.

The tables were produced by `python scripts/evaluate_paper.py` with version 1.0.1 of this library (Python 3.12.10, NumPy 2.5.4, pandas 3.0.6, macOS, arm64) from the three public logs named in the README. `tests/test_paper_evaluation.py` makes the same comparison.

## Summary

- Result items: 38 (35 numeric or textual results, 3 figures).
- Items with agreement on every printed value: 38.
- Printed values: 259; agreeing computed values: 259; different: 0; not computed: 0.

The item numbers are stable: a number is not reused when the paper drops a result. The numbers 23, 27, 28 and 34 are therefore not in use (groups shared with the Balanced top ten; the worked incident; the Balanced mean penalty of the incident application; size and checksum of the CSV export).

The three figures are drawn by `wise.evaluation.figures` from the computed values in the design of the printed figures; every number shown in them is in the tables below.

## How a value is compared

- A number agrees when it rounds to the printed value at the printed number of decimals.
- Counts, labels, identifiers and yes/no statements agree when they are equal.
- One value is compared by its order of magnitude: the largest absolute difference of the consistency check of Section 5.6, printed as approximately 1.73 × 10⁻¹¹. It is a floating-point residual between two implementations of the same sums; its digits depend on the machine and on the versions of NumPy and pandas (the same check of BPIC'19 gave 2.05 × 10⁻¹¹ on 30 September 2026 with the full library `wise-pm` 0.1.0, NumPy 2.2.6 and pandas 2.3.0). It agrees when it lies within a factor of ten of the printed value; that it is below the declared tolerance of 10⁻⁸ is compared as a value of its own, and the test asserts this bound and not the digits.

## Values that are input checks

Six of the printed values are also conditions that an adapter enforces before anything is computed: it stops if the file it reads does not have this number of events or cases, and a file is read only if its size and SHA-256 match the input catalogue (`src/wise/evaluation/data_catalog.json`). On another file the run ends with an error instead of another number, so these values cannot differ; their agreement confirms the identity of the input, not a computation.

| Item | Value | Printed |
|---:|---|---|
| 3 | events | 1,595,923 |
| 3 | purchase-order items (scored cases) | 251,734 |
| 3 | purchasing documents | 76,349 |
| 26 | events | 65,533 |
| 26 | incidents (scored cases) | 7,554 |
| 31 | loan applications (scored cases) | 31,509 |

The manuscript of 11 October no longer prints the size and the SHA-256 of the BPIC'19 CSV export. Both are still enforced: they are in the input catalogue and in the adapter configuration, and every calculation record states them.

## Printed statements that are not compared

The comparison holds results. The following printed statements are not rows of it.

- **The specification of the purchase-to-pay norm** (Table B1 and Appendix B.1): the recorded condition, scale endpoints, scope and evidence rule of the ten criteria, the layer of each criterion, the plausibility interval of the selected timestamps (from 1 January 2017, before 1 January 2020), the pattern of a valid resource identity, that a valid batch identity is usable attribution but counts neither as a user-attributed event nor as a user identity, the primary settings (flat scoring, scored item count, γ = 0) and the tie order. They are not computed from a log; `tests/evaluation/test_configurations.py` checks the shipped adapter configuration and native norm against them. The raw weights per layer and the layer shares under Balanced are compared (item 40).
- **Rules of the adapter stated in Appendix B.1 that have no effect in this export**: an unparsable timestamp is passed over when another parsed one exists; an earlier parsed but out-of-range timestamp is not replaced by a later one; equality of the two timestamps of C05 has zero deviation. The adapter implements them; `tests/evaluation/test_adapters.py` exercises the adapter on constructed records.
- **Statements about the source and its documentation**: that the challenge describes four matching flows, permits repeated receipt and invoice cycles and omits approval workflows (Section 5.1 and Appendix B.1). The four flows and their item counts are compared (item 4); the description of the challenge is not checked here.
- **The statements of Appendix B.2 about this repository**: the paths of the adapters, configurations, native norms and input catalogue, the file names, the route to the BPIC'19 CSV, the transport of prepared assessments by a metric constraint with threshold zero and width one, and what the scripts write. They describe the repository and are not results; `tests/evaluation/test_configurations.py`, `tests/evaluation/test_native.py` and `tests/evaluation/test_data.py` cover the files, the transport and the input check.
- **Tables 5 and 6** (business concerns and decisions; proposed process changes) and the interpretation of the results: text, nothing is computed.
- **The identities of Appendix A**: bounded scores and additive layer contributions (A.2), the signed decomposition of the Priority Index for both scales and any γ (A.3), the zero sum of the unshrunk signed group excesses of a partition. They are properties of the method, tested on generated logs in `tests/test_invariants.py` and, for the three applications, part of the consistency check (item 33).
- **Arithmetic shown in the text** whose result is compared: (69.040972 − 30)/60 ≈ 0.650683 and 0.650683/7 ≈ 0.092955 (item 12).

## Numerical checks and calculation records

- **Consistency with the reference arithmetic** (Section 5.6; item 33): the library's scores, effective weights, criterion contributions and coverage, the group counts, means, gaps and priorities, and the signed layer contributions are compared with an independent implementation on the same prepared criterion assessments, for three views in each of the three applications: nine primary view evaluations and eighteen mode-view combinations across flat and layer-balanced scoring, each at γ = 0 and γ = 20. Scope and evidence states must be identical, every difference below 10⁻⁸. Made by `wise.evaluation.replay`, by `scripts/replay_native.py`, by `scripts/evaluate_paper.py` and by the dataset evaluation test.
- **Constructed tests** (Section 5.6; item 42): the deviation values after the rows of the event table are shuffled, and the case scores after a norm is serialised and reloaded. `tests/test_invariants.py` makes both on generated logs with the five basic constraint types; item 42 makes them on the two bundled examples.
- **Three further checks on each application, beyond what the paper states**: the case scores of all views, under flat and layer-balanced scoring, are computed again (a) with the complete cases in another order, (b) with the norm serialised to its JSON document and read back, (c) with the whole-case context attached, and compared case by case. Made by `scripts/replay_native.py`, `scripts/evaluate_paper.py` and the dataset evaluation test. The largest absolute score difference of each check in this run:

| Application | Cases reordered | Norm serialised and read back | Whole-case context attached | Context |
|---|---:|---:|---:|---|
| `bpic2019` | 0 | 0 | 0 | document, vendor, flow |
| `bpic2013_incidents` | 0 | 0 | 0 | product_group |
| `bpic2017` | 0 | 0 | 0 | application_type, loan_goal |

A case is one record of the prepared assessment, so reordering moves all values of a case together. The whole-case context is the set of attributes of an application's case table that describe the complete case and allow other groupings of the same scored cases; attaching it adds these attributes to the cases, and no criterion reads them. All checks begin with prepared deviation values: they establish numerical consistency of scoring and prioritisation, not how an adapter interprets the source records.

**Calculation records.** `scripts/evaluate_paper.py` writes one record per application into its output folder: `calculation_record_bpic2019.json`, `calculation_record_bpic2013_incidents.json` and `calculation_record_bpic2017.json` (in Python: `wise.evaluation.paper.calculation_record(application, data)`). Appendix B.2 of the paper speaks of calculation records retained by the authors that are not distributed with the library; the command writes a record with the same parts:

| Part of the record | What it identifies |
|---|---|
| `source_export` | the catalogued file name, size in bytes and SHA-256; numbers of events and cases (and of documents for BPIC'19); the name of the file as found in the data folder |
| `adapter_configuration` | identifier, version, file and SHA-256 of the configuration (of its JSON with sorted keys and no white space) |
| `norm` | name, version, file and fingerprint of the native norm; the criteria with their layers |
| `tested_settings` | the views with their raw weights, the scoring modes, the values of γ, the grouping, the scale, the comparison reference, the tie order, the whole-case context |
| `evidence_summaries` | per criterion: cases in scope, evaluated, outside scope, and unavailable by reason |
| `ordered_results` | per view: scored cases, reference mean score, and every group in ranked order with its scored cases, mean score, gap and Priority Index |
| `numerical_checks` | the tolerance; every difference against the reference arithmetic with the equality of scope and evidence states; the three further checks |

A record holds aggregates and identities only: no case of a log and no path of the machine. Records are not part of the repository; each run writes them anew into the output folder. With `--output`, `scripts/replay_native.py` writes the numerical checks alone as `<application>.json`. The fingerprints and checksums of this run:

| Application | Source export, SHA-256 | Adapter configuration, SHA-256 | Norm fingerprint |
|---|---|---|---|
| `bpic2019` | `7d592fb425690d13011d1b874fe2af63f61a66acfc368ecf87b4ed266e6cdb00` | `51ecc7f5fb77cd2cc0f03dc4ebd284a905333ed1f1787643dba392419ce6a812` | `8b98caa9a54c2cae8f0b894a0e18b6551caed181a74b86005ddde5f75dbec528` |
| `bpic2013_incidents` | `6ec2136c607648608655802486df97a866f351668751b7ecbca51e1f8715d522` | `ae06df5949c1280dda869a8a55908016154da24b36792bd41159f78012e0b053` | `d75dc2d77e5394030fd8e9a6a9956f5f000f8d73dcb907b433aac004c58002fd` |
| `bpic2017` | `183c5e5189282779c811c78c33ff936351b3dd201165d612211fc220936f8249` | `7d8258363811909d5c209b641c367758ac3a150791b160c7b4db30b8f63815a0` | `e080d65628f3ebccdaf00b75e486912f4ca40ffe7168fcd2783a923ebd7d8203` |

## Settings

- BPIC'19 (Sections 5.1 to 5.4, Appendix B.1): norm `wise-bpic19-transparent-ten-v1` with ten criteria in four layers (Table B1); views Balanced, Completion and Operations; flat scoring; groups by company and spend area unless stated; scored item count; comparison reference = mean score of all scored PO items under the view; γ = 0; ties by Priority Index, then scored count, then group identifier.
- BPIC'13 incidents (Section 5.5): norm `wise-bpic2013-transfer-six-v1` with six criteria; views Balanced, Routing and Timing; flat scoring; groups by product; γ = 0 unless stated.
- BPIC'17 (Section 5.5): norm `loan_application_recorded_concerns_v1` with five criteria; views Balanced, Timeliness and Interaction; flat scoring; groups by application type and loan goal; γ = 0 unless stated.
- Section 4: the running norm of Table 3 with the views Finance and Logistics, flat scoring. Section 3: the illustrative norm of Figure 2 with the views Processing effort and Financial control.

## Result items

| Item | Place | What | Printed values | Agreeing values | Settings |
|---:|---|---|---:|---|---|
| 1 | Table 4, p. 23; computations pp. 23-24 | Scores of the five illustrative cases under the Finance and Logistics views | 17 | yes | running norm of Table 3; flat scoring; c4 not applicable |
| 2 | Section 4.2, pp. 16-18; Section 4.5, p. 25 | Worked arithmetic of the method section | 12 | yes | `wise.sat`, the lag and occurrence-limit constraints of the running norm, `wise.prioritize` |
| 3 | Section 5.1, p. 27; Appendix B.1, p. 37 | Size of the BPIC'19 export | 3 | yes | BPIC'19 CSV; case = PO item (document and item) |
| 4 | Appendix B.1, p. 37 | Matching flows of the purchase-order items | 4 | yes | matching flow = item category of the PO item |
| 5 | Section 5.1, p. 27; Appendix B.1, p. 37 | Company-by-spend-area groups | 1 | yes | groups = company × spend area |
| 6 | Section 5.1, p. 28; Appendix B.1, p. 38 | All purchase-order items receive a score under the primary flat assessment | 3 | yes | norm `wise-bpic19-transparent-ten-v1`; flat scoring |
| 7 | Section 5.1, p. 28 | Mean weighted coverage per view | 3 | yes | fraction of in-scope raw weight with usable evidence; mean over all PO items |
| 8 | Section 5.3, p. 29 | C04 in Packaging | 2 | yes | C04; group Packaging |
| 9 | Section 5.3, p. 29 | Median selected invoice-to-clearing interval | 4 | yes | C04-evaluable items |
| 10 | Section 5.3, p. 29 | The same medians within the DF2 flow | 2 | yes | C04-evaluable items of flow DF2 |
| 11 | Fig. 5, p. 30 | Empirical cumulative distributions of the selected invoice-to-clearing interval, Packaging and remaining groups | 6 | yes | drawn from every observed interval |
| 12 | Section 5.3, pp. 29-30 | Worked purchase-order item | 13 | yes | Packaging; positive C04 deviation; interval nearest the median of the evaluable Packaging items; ties by item identifier; Balanced |
| 13 | Section 5.2, p. 28 | Population mean penalty under Balanced | 1 | yes | Balanced; flat; all scored PO items |
| 14 | Section 5.2, p. 28 | Packaging under Balanced | 3 | yes | Balanced; flat; scored item count; reference = population mean; γ = 0 |
| 15 | Section 5.2, p. 28 | Logistics under Balanced | 3 | yes | as item 14 |
| 16 | Section 5.2, p. 28 | Mean Balanced coverage of the two groups | 2 | yes | Balanced; mean of case-level coverage |
| 17 | Section 5.2, p. 28 | Signed layer contributions under Balanced | 8 | yes | Balanced; γ = 0; H = n × (group mean − population mean) per layer |
| 18 | Fig. 4, p. 29 | Bars of the signed layer contributions for Packaging and Logistics on a common scale | 12 | yes | values of items 14, 15 and 17 |
| 19 | Section 5.2, p. 28 | Recorded absences in Logistics | 2 | yes | C01 and C02 in Logistics |
| 20 | Section 5.2, p. 28 | Vendor concentration of the case penalty in Packaging | 2 | yes | sum of Balanced case penalties per vendor within Packaging |
| 21 | Section 5.4, p. 30 | Top-20 positive-priority purchasing documents shared between views | 12 | yes | groups = purchasing documents; item-level scores and reference; top 20 with positive PI; γ = 0 |
| 22 | Section 5.4, p. 31 | First two company-by-spend-area groups under every view | 6 | yes | company × spend area; γ = 0 |
| 24 | Section 5.4, p. 31 | Ranking policies on fixed Balanced case penalties: members shared with the primary PI top ten | 3 | yes | Balanced penalties, scored population and thirty groups fixed; ranking by mean penalty, total penalty and PI with γ = 20 |
| 25 | Fig. 6, p. 32 | Shortlist membership under declared assessment choices | 6 | yes | values of items 21 and 24 |
| 26 | Section 5.5, p. 32 | Size of the BPIC'13 incident application | 4 | yes | BPIC'13 incidents XES; case = incident; groups = product; norm `wise-bpic2013-transfer-six-v1` |
| 29 | Section 5.5, p. 32 | Product group PROD542 under Balanced | 4 | yes | Balanced; flat; γ = 0 |
| 30 | Section 5.5, p. 32 | Product group PROD424 under Balanced | 3 | yes | as item 29 |
| 31 | Section 5.5, p. 33 | Size and evidence of the BPIC'17 lending application | 3 | yes | BPIC'17 XES; case = application; groups = application type × loan goal; norm `loan_application_recorded_concerns_v1` |
| 32 | Section 5.5, p. 33 | Group selected first per view | 3 | yes | flat; γ = 0 |
| 33 | Section 5.6, p. 33 | Numerical check of the library's scoring and aggregation against the reference arithmetic on the same prepared criterion assessments | 9 | yes | three applications; three views each; flat and layer-balanced; each at γ = 0 and 20; tolerance 1e-8 |
| 35 | Section 5.2, p. 28 | Usable C04 endpoints among the applicable items of Logistics and Packaging | 4 | yes | C04 applies to non-Consignment items; usable endpoints = C04 evaluated |
| 36 | Section 5.4, pp. 30-31 | Purchasing document that leads each view | 3 | yes | groups = purchasing documents; γ = 0 |
| 37 | Section 5.5, p. 32 | Signed layer contributions of PROD424 under Balanced | 2 | yes | Balanced; γ = 0 |
| 38 | Section 5.5, p. 33 | Incident products under Balanced with the small-slice adjustment at γ = 20 | 6 | yes | Balanced; γ = 0 and γ = 20; top ten with positive priority |
| 39 | Section 5.5, p. 33 | Lending groups with the small-slice adjustment at γ = 20 and at capacity ten | 9 | yes | per view; γ = 0 and γ = 20; groups with positive priority |
| 40 | Section 5.1, pp. 27-28; Appendix B.1, p. 38 | Criteria and weights of the purchase-to-pay norm per layer | 17 | yes | shipped native norm of BPIC'19; no log needed |
| 41 | Section 3, pp. 9-10; Fig. 2, p. 11 | Illustrative assessment of four invoice cases under two views | 60 | yes | `wise.illustrative_invoice_log()` and `wise.illustrative_invoice_norm()`; flat scoring; case-count multiplier |
| 42 | Section 5.6, p. 33 | Constructed checks: shuffled event rows and a reloaded norm | 2 | yes | the two bundled examples (Tables 3 and 4; Figure 2); flat and layer-balanced; no log needed |

## Every printed value

In the last column, *input check* marks a value that cannot differ (see above) and *order* the value that is compared by its order of magnitude.

| Item | Quantity | Printed | Computed | Agreement | Note |
|---:|---|---|---|---|---|
| 1 | case A: violation of c2 | 0.75 | 0.75 | agrees |  |
| 1 | case B: violation of c5 | 2/3 ≈ 0.67 | 0.6666666667 | agrees |  |
| 1 | case C: violation of c3 | 0.65 | 0.65 | agrees |  |
| 1 | case D: violation of c6 | 1 | 1 | agrees |  |
| 1 | case E: violation of c1 | 1 | 1 | agrees |  |
| 1 | case E: violation of c2 | 1 | 1 | agrees |  |
| 1 | case E: violation of c3 | 1 | 1 | agrees |  |
| 1 | case A: score under Finance | 0.6625 | 0.6625 | agrees |  |
| 1 | case A: score under Logistics | 0.8875 | 0.8875 | agrees |  |
| 1 | case B: score under Finance | 0.9667 | 0.9666666667 | agrees |  |
| 1 | case B: score under Logistics | 0.7000 | 0.7 | agrees |  |
| 1 | case C: score under Finance | 0.8700 | 0.87 | agrees |  |
| 1 | case C: score under Logistics | 0.9675 | 0.9675 | agrees |  |
| 1 | case D: score under Finance | 0.9000 | 0.9 | agrees |  |
| 1 | case D: score under Logistics | 0.9000 | 0.9 | agrees |  |
| 1 | case E: score under Finance | 0.1500 | 0.15 | agrees |  |
| 1 | case E: score under Logistics | 0.5500 | 0.55 | agrees |  |
| 2 | sat(8; 10, 20) | 0 | 0 | agrees |  |
| 2 | sat(15; 10, 20) | 0.25 | 0.25 | agrees |  |
| 2 | sat(20; 10, 20) | 0.5 | 0.5 | agrees |  |
| 2 | sat(30; 10, 20) | 1 | 1 | agrees |  |
| 2 | lag constraint c2 at a lag of 10 days | 0 | 0 | agrees |  |
| 2 | lag constraint c2 at a lag of 20 days | 0.5 | 0.5 | agrees |  |
| 2 | lag constraint c2 at a lag of 30 days | 1 | 1 | agrees |  |
| 2 | occurrence limit c5 at three goods receipts | ≈ 0.33 | 0.3333333333 | agrees |  |
| 2 | occurrence limit c5 at four goods receipts | ≈ 0.67 | 0.6666666667 | agrees |  |
| 2 | occurrence limit c5 at five goods receipts | 1 | 1 | agrees |  |
| 2 | illustration: gap of a slice with mean 0.80 against the reference 0.94 | 0.14 | 0.14 | agrees |  |
| 2 | illustration: Priority Index of that slice with 240 scored cases | 33.6 | 33.6 | agrees |  |
| 3 | events | 1,595,923 | 1595923 | agrees | input check |
| 3 | purchase-order items (scored cases) | 251,734 | 251734 | agrees | input check |
| 3 | purchasing documents | 76,349 | 76349 | agrees | input check |
| 4 | DF2 items | 221,010 | 221010 | agrees |  |
| 4 | DF1 items | 15,182 | 15182 | agrees |  |
| 4 | Consignment items | 14,498 | 14498 | agrees |  |
| 4 | two-way items | 1,044 | 1044 | agrees |  |
| 5 | groups, missing labels kept as explicit categories | 30 | 30 | agrees |  |
| 6 | scored items under Balanced | 251,734 | 251734 | agrees |  |
| 6 | scored items under Completion | 251,734 | 251734 | agrees |  |
| 6 | scored items under Operations | 251,734 | 251734 | agrees |  |
| 7 | mean coverage under Balanced | 0.787570 | 0.7875700033 | agrees |  |
| 7 | mean coverage under Completion | 0.866370 | 0.8663695361 | agrees |  |
| 7 | mean coverage under Operations | 0.669052 | 0.6690517015 | agrees |  |
| 8 | Packaging items for which C04 can be evaluated | 76,608 | 76608 | agrees |  |
| 8 | of which with a positive C04 deviation | 64,068 | 64068 | agrees |  |
| 9 | Packaging: C04-evaluable items | 76,608 | 76608 | agrees |  |
| 9 | Packaging: median interval in days | 69.04 | 69.04097222 | agrees |  |
| 9 | outside Packaging: C04-evaluable items | 106,661 | 106661 | agrees |  |
| 9 | outside Packaging: median interval in days | 28.93 | 28.92916667 | agrees |  |
| 10 | Packaging, DF2: median interval in days | 70.14 | 70.13958333 | agrees |  |
| 10 | outside Packaging, DF2: median interval in days | 29.10 | 29.10138889 | agrees |  |
| 11 | legend: Packaging n | 76,608 | 76608 | agrees |  |
| 11 | legend: Packaging median in days | 69.04 | 69.04097222 | agrees |  |
| 11 | legend: remaining groups n | 106,661 | 106661 | agrees |  |
| 11 | legend: remaining groups median in days | 28.93 | 28.92916667 | agrees |  |
| 11 | first dashed marker: C04 threshold in days | 30 | 30 | agrees |  |
| 11 | second dashed marker: deviation value 1 in days | 90 | 90 | agrees |  |
| 12 | selected item (positive C04 deviation, interval nearest the Packaging median, ties by identifier) | 4507005472_00040 | 4507005472_00040 | agrees |  |
| 12 | selected invoice receipt | 2018-02-16 10:15 | 2018-02-16 10:15 | agrees |  |
| 12 | selected clearing | 2018-04-26 11:14 | 2018-04-26 11:14 | agrees |  |
| 12 | interval in days | 69.040972 | 69.04097222 | agrees |  |
| 12 | C04 deviation | ≈ 0.650683 | 0.6506828704 | agrees |  |
| 12 | criteria evaluable under Balanced | seven | 7 | agrees |  |
| 12 | contribution of C04 to the penalty | ≈ 0.092955 | 0.09295469577 | agrees |  |
| 12 | other evaluated criteria that contribute | none (the other six contribute zero) | 0 | agrees |  |
| 12 | score under Balanced | 0.907045 | 0.9070453042 | agrees |  |
| 12 | state of C05 | outside scope | out_of_scope | agrees |  |
| 12 | state of C09 | unavailable | missing_resource_evidence | agrees |  |
| 12 | state of C10 | unavailable | missing_resource_evidence | agrees |  |
| 12 | coverage under Balanced | seven ninths | 0.7777777778 | agrees |  |
| 13 | mean penalty of all scored items | 0.101358 | 0.101357911 | agrees |  |
| 14 | mean penalty | 0.117624 | 0.1176235456 | agrees |  |
| 14 | scored items | 109,199 | 109199 | agrees |  |
| 14 | Priority Index | 1,776.19 | 1776.19104 | agrees |  |
| 15 | mean penalty | 0.228143 | 0.2281429508 | agrees |  |
| 15 | scored items | 5,242 | 5242 | agrees |  |
| 15 | Priority Index | 664.61 | 664.607179 | agrees |  |
| 16 | Packaging | 0.7888 | 0.7888312978 | agrees |  |
| 16 | Logistics | 0.7067 | 0.7066831998 | agrees |  |
| 17 | Packaging: Completion | -332.42 | -332.4209854 | agrees |  |
| 17 | Packaging: Timing | +2,365.44 | 2365.436368 | agrees |  |
| 17 | Packaging: Rework | -267.95 | -267.9501084 | agrees |  |
| 17 | Packaging: Effort proxy | +11.13 | 11.12576566 | agrees |  |
| 17 | Logistics: Completion | +811.13 | 811.132774 | agrees |  |
| 17 | Logistics: Timing | -154.25 | -154.2482984 | agrees |  |
| 17 | Logistics: Rework | +10.54 | 10.53536174 | agrees |  |
| 17 | Logistics: Effort proxy | -2.81 | -2.812658315 | agrees |  |
| 18 | panel A bar label: Completion | -332.42 | -332.4209854 | agrees |  |
| 18 | panel A bar label: Timing | +2,365.44 | 2365.436368 | agrees |  |
| 18 | panel A bar label: Rework | -267.95 | -267.9501084 | agrees |  |
| 18 | panel A bar label: Effort proxy | +11.13 | 11.12576566 | agrees |  |
| 18 | panel A header: scored PO items | 109,199 | 109199 | agrees |  |
| 18 | panel A header: Priority Index | 1,776.19 | 1776.19104 | agrees |  |
| 18 | panel B bar label: Completion | +811.13 | 811.132774 | agrees |  |
| 18 | panel B bar label: Timing | -154.25 | -154.2482984 | agrees |  |
| 18 | panel B bar label: Rework | +10.54 | 10.53536174 | agrees |  |
| 18 | panel B bar label: Effort proxy | -2.81 | -2.812658315 | agrees |  |
| 18 | panel B header: scored PO items | 5,242 | 5242 | agrees |  |
| 18 | panel B header: Priority Index | 664.61 | 664.607179 | agrees |  |
| 19 | items without recorded invoice receipt | 3,260 | 3260 | agrees |  |
| 19 | items without recorded clearing | 3,507 | 3507 | agrees |  |
| 20 | vendors of the group | 266 | 266 | agrees |  |
| 20 | vendors that account for at least 80% of the total Balanced case penalty | 16 | 16 | agrees |  |
| 21 | Balanced and Completion: shared documents in the top 20 | 18 | 18 | agrees |  |
| 21 | Balanced and Completion: Jaccard similarity | 0.818 | 0.8181818182 | agrees |  |
| 21 | Balanced and Operations: shared documents in the top 20 | ten | 10 | agrees |  |
| 21 | Balanced and Operations: Jaccard similarity | 0.333 | 0.3333333333 | agrees |  |
| 21 | Completion and Operations: shared documents in the top 20 | eight | 8 | agrees |  |
| 21 | Completion and Operations: Jaccard similarity | 0.250 | 0.25 | agrees |  |
| 21 | Balanced: documents in the list | twenty | 20 | agrees |  |
| 21 | Balanced: a tie across the selection boundary | no | no | agrees |  |
| 21 | Completion: documents in the list | twenty | 20 | agrees |  |
| 21 | Completion: a tie across the selection boundary | no | no | agrees |  |
| 21 | Operations: documents in the list | twenty | 20 | agrees |  |
| 21 | Operations: a tie across the selection boundary | no | no | agrees |  |
| 22 | Balanced: first group | Packaging | companyID_0000 / Packaging | agrees |  |
| 22 | Balanced: second group | Logistics | companyID_0000 / Logistics | agrees |  |
| 22 | Completion: first group | Packaging | companyID_0000 / Packaging | agrees |  |
| 22 | Completion: second group | Logistics | companyID_0000 / Logistics | agrees |  |
| 22 | Operations: first group | Packaging | companyID_0000 / Packaging | agrees |  |
| 22 | Operations: second group | Logistics | companyID_0000 / Logistics | agrees |  |
| 24 | ranking by mean penalty | six | 6 | agrees |  |
| 24 | ranking by total penalty | four | 4 | agrees |  |
| 24 | PI with the small-group adjustment at γ = 20 | all ten | 10 | agrees |  |
| 25 | panel A: Balanced / Completion | 18/20 | 18 | agrees |  |
| 25 | panel A: Balanced / Operations | 10/20 | 10 | agrees |  |
| 25 | panel A: Completion / Operations | 8/20 | 8 | agrees |  |
| 25 | panel B: mean case penalty | 6/10 | 6 | agrees |  |
| 25 | panel B: total case penalty | 4/10 | 4 | agrees |  |
| 25 | panel B: PI with small-slice adjustment (γ = 20) | 10/10 | 10 | agrees |  |
| 26 | events | 65,533 | 65533 | agrees | input check |
| 26 | incidents (scored cases) | 7,554 | 7554 | agrees | input check |
| 26 | product groups | 704 | 704 | agrees |  |
| 26 | criteria of the incident norm | six | 6 | agrees |  |
| 29 | incidents | 75 | 75 | agrees |  |
| 29 | mean penalty | 0.665994 | 0.6659939166 | agrees |  |
| 29 | Priority Index | 37.245645 | 37.24564481 | agrees |  |
| 29 | signed contribution of Routing to the gap | +17.075672 | 17.07567183 | agrees |  |
| 30 | incidents | 882 | 882 | agrees |  |
| 30 | mean penalty | 0.205114 | 0.2051141456 | agrees |  |
| 30 | Priority Index | 31.512825 | 31.51282493 | agrees |  |
| 31 | loan applications (scored cases) | 31,509 | 31509 | agrees | input check |
| 31 | application-type-by-loan-goal combinations | 27 | 27 | agrees |  |
| 31 | in-scope criteria that are not evaluable, over all applications | none (all in-scope criteria are evaluable) | 0 | agrees |  |
| 32 | Balanced | New credit / Existing loan takeover | New credit / Existing loan takeover | agrees |  |
| 32 | Timeliness | New credit / Remaining debt home | New credit / Remaining debt home | agrees |  |
| 32 | Interaction | New credit / Remaining debt home | New credit / Remaining debt home | agrees |  |
| 33 | applications covered | three | 3 | agrees |  |
| 33 | views in each application | three | 3 | agrees |  |
| 33 | primary view evaluations | nine | 9 | agrees |  |
| 33 | mode-view combinations across flat and layer-balanced scoring | eighteen | 18 | agrees |  |
| 33 | values of γ at which each combination is checked | 0 and 20 | 0 and 20 | agrees |  |
| 33 | largest absolute difference | approximately 1.73 × 10^-11 | 1.728040e-11 | agrees | order |
| 33 | declared tolerance | 10^-8 | 1.000000e-08 | agrees |  |
| 33 | largest absolute difference is below the tolerance | yes | yes | agrees |  |
| 33 | scope and evidence states match exactly | yes | yes | agrees |  |
| 35 | Logistics: items with usable C04 endpoints | 1,734 | 1734 | agrees |  |
| 35 | Logistics: items to which C04 applies | 5,242 | 5242 | agrees |  |
| 35 | Packaging: items with usable C04 endpoints | 76,608 | 76608 | agrees |  |
| 35 | Packaging: items to which C04 applies | 100,635 | 100635 | agrees |  |
| 36 | Balanced | 4508073932 | 4508073932 | agrees |  |
| 36 | Completion | 4508073932 | 4508073932 | agrees |  |
| 36 | Operations | 4507021416 | 4507021416 | agrees |  |
| 37 | Recorded patterns | +31.776426 | 31.7764264 | agrees |  |
| 37 | Routing | -5.166766 | -5.166765952 | agrees |  |
| 38 | first group at γ = 20 | PROD424 | PROD424 | agrees |  |
| 38 | adjusted Priority Index of PROD424 | 30.814093 | 30.81409267 | agrees |  |
| 38 | adjusted Priority Index of PROD542 | 29.404456 | 29.40445643 | agrees |  |
| 38 | first group without the adjustment (the first-priority group changes) | PROD542 | PROD542 | agrees |  |
| 38 | products of the positive-priority shortlist retained | the same ten | 10 | agrees |  |
| 38 | Jaccard similarity of the two top-ten lists | one | 1 | agrees |  |
| 39 | Timeliness: first group at γ = 20 | Existing loan takeover | New credit / Existing loan takeover | agrees |  |
| 39 | Interaction: first group at γ = 20 | Existing loan takeover | New credit / Existing loan takeover | agrees |  |
| 39 | Balanced: positive-priority membership retained at γ = 20 | yes | yes | agrees |  |
| 39 | Timeliness: positive-priority membership retained at γ = 20 | yes | yes | agrees |  |
| 39 | Interaction: positive-priority membership retained at γ = 20 | yes | yes | agrees |  |
| 39 | Timeliness: positive groups at requested capacity ten | five | 5 | agrees |  |
| 39 | Interaction: positive groups at requested capacity ten | six | 6 | agrees |  |
| 39 | criteria of the lending norm | five | 5 | agrees |  |
| 39 | criteria that belong to Interaction | three | 3 | agrees |  |
| 40 | criteria of the norm | ten | 10 | agrees |  |
| 40 | Balanced: share of the total weight allocated to Completion, all ten criteria in scope and evaluable | 0.3 | 0.3 | agrees |  |
| 40 | Balanced: share of the total weight allocated to Timing, all ten criteria in scope and evaluable | 0.2 | 0.2 | agrees |  |
| 40 | Balanced: share of the total weight allocated to Rework, all ten criteria in scope and evaluable | 0.3 | 0.3 | agrees |  |
| 40 | Balanced: share of the total weight allocated to Effort proxy, all ten criteria in scope and evaluable | 0.2 | 0.2 | agrees |  |
| 40 | Balanced: raw weight of each criterion of Completion | 1 | 1 | agrees |  |
| 40 | Balanced: raw weight of each criterion of Timing | 1 | 1 | agrees |  |
| 40 | Balanced: raw weight of each criterion of Rework | 1 | 1 | agrees |  |
| 40 | Balanced: raw weight of each criterion of Effort proxy | 1 | 1 | agrees |  |
| 40 | Completion: raw weight of each criterion of Completion | 3 | 3 | agrees |  |
| 40 | Completion: raw weight of each criterion of Timing | 2 | 2 | agrees |  |
| 40 | Completion: raw weight of each criterion of Rework | 1 | 1 | agrees |  |
| 40 | Completion: raw weight of each criterion of Effort proxy | 1 | 1 | agrees |  |
| 40 | Operations: raw weight of each criterion of Completion | 1 | 1 | agrees |  |
| 40 | Operations: raw weight of each criterion of Timing | 1 | 1 | agrees |  |
| 40 | Operations: raw weight of each criterion of Rework | 2 | 2 | agrees |  |
| 40 | Operations: raw weight of each criterion of Effort proxy | 3 | 3 | agrees |  |
| 41 | case A1: deviation, release limit | 1 | 1 | agrees |  |
| 41 | case A1: deviation, no forwarding | 1 | 1 | agrees |  |
| 41 | case A1: deviation, required release record | 0 | 0 | agrees |  |
| 41 | case A2: deviation, release limit | 1 | 1 | agrees |  |
| 41 | case A2: deviation, no forwarding | 0 | 0 | agrees |  |
| 41 | case A2: deviation, required release record | 0 | 0 | agrees |  |
| 41 | case B1: deviation, release limit | 0 | 0 | agrees |  |
| 41 | case B1: deviation, no forwarding | 0 | 0 | agrees |  |
| 41 | case B1: deviation, required release record | 1 | 1 | agrees |  |
| 41 | case B2: deviation, release limit | 0 | 0 | agrees |  |
| 41 | case B2: deviation, no forwarding | 0 | 0 | agrees |  |
| 41 | case B2: deviation, required release record | 1 | 1 | agrees |  |
| 41 | Processing effort: weight of release limit | 0.40 | 0.4 | agrees |  |
| 41 | Processing effort: weight of no forwarding | 0.40 | 0.4 | agrees |  |
| 41 | Processing effort: weight of required release record | 0.20 | 0.2 | agrees |  |
| 41 | Processing effort, case A1: weighted deviation, release limit | 0.40 | 0.4 | agrees |  |
| 41 | Processing effort, case A1: weighted deviation, no forwarding | 0.40 | 0.4 | agrees |  |
| 41 | Processing effort, case A1: weighted deviation, required release record | 0.00 | 0 | agrees |  |
| 41 | Processing effort, case A2: weighted deviation, release limit | 0.40 | 0.4 | agrees |  |
| 41 | Processing effort, case A2: weighted deviation, no forwarding | 0.00 | 0 | agrees |  |
| 41 | Processing effort, case A2: weighted deviation, required release record | 0.00 | 0 | agrees |  |
| 41 | Processing effort, case B1: weighted deviation, release limit | 0.00 | 0 | agrees |  |
| 41 | Processing effort, case B1: weighted deviation, no forwarding | 0.00 | 0 | agrees |  |
| 41 | Processing effort, case B1: weighted deviation, required release record | 0.20 | 0.2 | agrees |  |
| 41 | Processing effort, case B2: weighted deviation, release limit | 0.00 | 0 | agrees |  |
| 41 | Processing effort, case B2: weighted deviation, no forwarding | 0.00 | 0 | agrees |  |
| 41 | Processing effort, case B2: weighted deviation, required release record | 0.20 | 0.2 | agrees |  |
| 41 | Processing effort: score of case A1 | 0.20 | 0.2 | agrees |  |
| 41 | Processing effort: score of case A2 | 0.60 | 0.6 | agrees |  |
| 41 | Processing effort: score of case B1 | 0.80 | 0.8 | agrees |  |
| 41 | Processing effort: score of case B2 | 0.80 | 0.8 | agrees |  |
| 41 | Financial control: weight of release limit | 0.10 | 0.1 | agrees |  |
| 41 | Financial control: weight of no forwarding | 0.10 | 0.1 | agrees |  |
| 41 | Financial control: weight of required release record | 0.80 | 0.8 | agrees |  |
| 41 | Financial control, case A1: weighted deviation, release limit | 0.10 | 0.1 | agrees |  |
| 41 | Financial control, case A1: weighted deviation, no forwarding | 0.10 | 0.1 | agrees |  |
| 41 | Financial control, case A1: weighted deviation, required release record | 0.00 | 0 | agrees |  |
| 41 | Financial control, case A2: weighted deviation, release limit | 0.10 | 0.1 | agrees |  |
| 41 | Financial control, case A2: weighted deviation, no forwarding | 0.00 | 0 | agrees |  |
| 41 | Financial control, case A2: weighted deviation, required release record | 0.00 | 0 | agrees |  |
| 41 | Financial control, case B1: weighted deviation, release limit | 0.00 | 0 | agrees |  |
| 41 | Financial control, case B1: weighted deviation, no forwarding | 0.00 | 0 | agrees |  |
| 41 | Financial control, case B1: weighted deviation, required release record | 0.80 | 0.8 | agrees |  |
| 41 | Financial control, case B2: weighted deviation, release limit | 0.00 | 0 | agrees |  |
| 41 | Financial control, case B2: weighted deviation, no forwarding | 0.00 | 0 | agrees |  |
| 41 | Financial control, case B2: weighted deviation, required release record | 0.80 | 0.8 | agrees |  |
| 41 | Financial control: score of case A1 | 0.80 | 0.8 | agrees |  |
| 41 | Financial control: score of case A2 | 0.90 | 0.9 | agrees |  |
| 41 | Financial control: score of case B1 | 0.20 | 0.2 | agrees |  |
| 41 | Financial control: score of case B2 | 0.20 | 0.2 | agrees |  |
| 41 | Processing effort: reference mean (all four scored cases) | 0.600 | 0.6 | agrees |  |
| 41 | Processing effort: mean score of the Plant A slice | 0.40 | 0.4 | agrees |  |
| 41 | Processing effort: Priority Index of Plant A | 0.40 | 0.4 | agrees |  |
| 41 | Processing effort: Priority Index of Plant B | 0 | 0 | agrees |  |
| 41 | Processing effort: first priority | Plant A | Plant A | agrees |  |
| 41 | Financial control: reference mean (all four scored cases) | 0.525 | 0.525 | agrees |  |
| 41 | Financial control: mean score of the Plant B slice | 0.20 | 0.2 | agrees |  |
| 41 | Financial control: Priority Index of Plant A | 0 | 0 | agrees |  |
| 41 | Financial control: Priority Index of Plant B | 0.65 | 0.65 | agrees |  |
| 41 | Financial control: first priority | Plant B | Plant B | agrees |  |
| 42 | deviation values unchanged after shuffling the event-table rows (bundled examples) | yes | yes | agrees |  |
| 42 | case scores preserved after serialising and reloading the norm (bundled examples) | yes | yes | agrees |  |
