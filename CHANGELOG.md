# Changelog

This repository is frozen at the state of the paper *WISE: Actionable Norm-Based Scoring for Process Mining* and changes only as numbered versions. A version is tied to a state of the paper: any change of a printed number, a norm, an adapter configuration or an expected value is a new version, and tags are never moved. Use the version listed below for its documented evaluation settings.

## 1.0.0

The method and evaluation settings of the October 2026 paper (manuscript dated 11 October 2026). The values printed in that paper are computed with this version: to check them, use the state of the repository tagged 1.0.0.

### Contents

- The method of Section 4 as the package `wise`: the event log and its case-level primitives; the constraint types presence, lag, balance, occurrence limit and exclusion, and the metric constraint on a case attribute; applicability rules for business scope; the process norm with layers and views and its JSON document format; case scoring in the flat and the layer-balanced mode with layer contributions and weighted evidence coverage; the Priority Index with the small-slice adjustment and exposure scaling; the signed layer contributions to the aggregate penalty gap; the running example of Tables 3 and 4 and the illustration of Section 3 (Figure 2).
- The evaluation of Section 5 and Appendix B as the subpackage `wise.evaluation`: the domain adapters for BPI Challenge 2019, BPI Challenge 2013 (incidents) and BPI Challenge 2017 with their configurations; the serialised native norms; the input catalogue with source identities and input hashes; the reference arithmetic and the replay with the numerical check of Section 5.6 (nine primary view evaluations, eighteen mode–view combinations, each at γ = 0 and γ = 20) and with three further checks per application (complete cases reordered, norm serialised and read back, whole-case context attached); one function per result item, table and figure; a calculation record for each application, with the parts that Appendix B.2 lists; the expected values of every result item and compact aggregate reference tables.
- `scripts/evaluate_paper.py`, the notebooks, unit tests, constructed contract tests and the dataset evaluation test.

### Evaluation results

38 result items (35 numeric or textual results, 3 figures) with 259 printed values. Every computed value agrees with the printed one at the printed precision. One of them, the largest absolute difference of the consistency check of Section 5.6, is a floating-point residual whose digits depend on the machine and on the versions of NumPy and pandas; it is compared by its order of magnitude, and the dataset evaluation test asserts that it is below the declared tolerance of 10⁻⁸. See [Evaluation results](EVALUATION.md) and the [evaluation notebook guide](notebooks/README.md).

### Relation to `wise-pm`

The code was derived from the full library `wise-pm` and reduced to what the paper uses: the method modules from the development line that follows version 0.1.0, the adapters, configurations and reference arithmetic from its evaluation directory (commit `52cc4b2e9a3c94ec6f8e8ba5874f220a3155f484`). On logs and norms that use only what both libraries implement, this library, `wise-pm` 0.1.0 and the development line give identical violations, scopes, scores, layer contributions and rankings.

Not taken over: the command-line interface; derived case attributes and their recipes; the diagnostics for censoring, replication and timestamps; the precedence constraint; the options of constraints that the paper does not define (scoped counts, activation and response variants of the lag, censoring, aggregations other than the sum, the low direction of a metric); the applicability operators `not`, `ne`, `not_in`, `isna`, `notna`, `regex`, `has` and `lacks`; a fixed comparison reference, a minimum slice size and a lower bound in the ranking; period comparison, shrinkage estimation, the hotspot typology, view agreement, penalty mass and concentration helpers; readers for other norm document versions and the migration between them; the twelve evaluation configurations that the paper does not report.

Where this library differs in behaviour, it follows the text of the paper:

- **Default scoring mode.** A norm that does not state its mode is scored flat, the primary mode of Sections 4.4 and 5.1. `wise-pm` defaults to layer-balanced. Every shipped norm states its mode.
- **Lag bound.** A lag constraint states `delta` and `width`; there is no default, and the width is positive (δ ≥ 0, Δ > 0 in Section 4.2). The saturation width of every graded constraint is positive.
- **Missing amounts.** A balance constraint has no value for a case in which a selected event lacks a usable number; the amount is not replaced by zero (Section 4.1). In `wise-pm` such an amount counts as zero.
- **Business scope.** A case whose applicability rule reads a missing attribute has unknown scope, is not scored on the constraint and carries the reason `scope_unknown`. The retained operators (`in`, `eq`, `gt`, `gte`, `lt`, `lte`, with `all` and `any`) select the same cases as in `wise-pm`.
- **Norm documents.** Read and written in schema version 3 only, with `"missing_values": "three_valued"`. A version 3 document of `wise-pm` is read when it uses only what this library implements.
- **Coverage and signed layer contributions.** `ScoreResult.coverage(view)` and `wise.layer_contributions(...)` are part of the library, as Sections 4.4 and 4.5 and Appendix A.3 define them. In `wise-pm` the same arithmetic is done by its evaluation code.
- **Ranking record.** `wise.prioritize` returns a record with the ranked table and the comparison settings (grouping, view, scale, γ, comparison reference, norm fingerprint, tie order), as Appendix A.4 asks.
- **Native norms.** The native norm of an application carries the identifier and version of its adapter configuration (`wise-bpic19-transparent-ten-v1`, `wise-bpic2013-transfer-six-v1`, `loan_application_recorded_concerns_v1`) and names the configuration file that holds the criteria definitions.
- **Adapters.** Reduced to the applications of the paper: the BPIC'19 adapter without the sensitivity and resampling runs that the paper does not print, the BPIC'13 adapter to the incident log, the lending adapter to BPI Challenge 2017. They read XES with the standard library and refuse a file that declares a document type or an entity. The BPIC'19 adapter counts distinct user identities after removing surrounding whitespace and differences of letter case, as Appendix B.1 states the rule for resource identities; the log has no identities that differ only in this way, so no value changes.
- **Section 5 analysis, figures and checks.** The interval medians, the worked purchase-order item, the vendor concentration, the document shortlists with their overlaps, the comparisons with the small-slice adjustment and the three figures are computed by `wise.evaluation.paper` and `wise.evaluation.figures`; the numerical check of Section 5.6 and three further checks per application by `wise.evaluation.replay`; the calculation record by `wise.evaluation.paper.calculation_record`.
- **Examples.** In the running example the layers carry the names of Table 3, and the purchase-order events carry an amount; the values of Table 4 are unchanged. The illustration of Section 3 is added.
