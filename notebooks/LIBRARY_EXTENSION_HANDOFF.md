# Evaluation extension handoff

## Working boundary

The existing notebooks call the frozen library for all numerical operations. The three extended notebooks already use core APIs for view/gamma/mode sensitivity, whole-case regrouping, per-group evidence coverage, criterion availability and mean severity, signed layer explanations and integrity tests. Keep those operations in the library. Preserve the paper baseline and expose new experiments through separately versioned configurations.

## P0: shared diagnostic facade

Proposed module: `wise.evaluation.analysis`. This module does not exist yet.

- `population_summary(application, data=None)`: source identity, case/event units, scored/unscored counts, scope/evidence-state counts and explicit denominators.
- `criterion_summary(application, by=None, view=None, data=None)`: evaluated/in-scope counts, unavailable reasons, raw/severity quantiles, positive-concern counts and coverage distributions. Existing generic aggregation already produces means and counts; centralise that contract and add the remaining diagnostics.
- `case_evidence(application, case_id, criterion=None, data=None)`: actual ordered source records, source event identities, witnesses supporting raw quantities, scope/evidence state, severity, effective weights and contributions. Distinguish original traces from the one-row assessment carrier.
- `shortlist_summary(backlogs, capacities=(5, 10, 20))`: positive-list sizes, keys, cutoff ties, ordering changes, overlap counts and Jaccard. Existing `top_k_overlap` gives Jaccard alone and cannot show whether fewer than k positive slices exist.

Acceptance: schema and identity match across all three processes; no local file path in returned tables or errors intended for display; unavailable and out-of-scope evidence remain distinct; signed offsets remain visible; no expected-value file is an input to empirical analysis.

## P1: whole-case context and versioned sensitivity

- `case_context(application, data=None)`: observed start/end instants and months, observed span, reviewed terminal outcome and explicitly justified censoring flags. Select whole case IDs, retaining every event and parent/object relation of each selected case. Never substitute event month for start/end month.
- `ranking_sensitivity(application, scenarios, data=None)`: declared view weights, gamma, modes, criterion omissions and raw-rule threshold/width scenarios; retain the original baseline and return case/priority/shortlist changes with full provenance.

Raw threshold sensitivity must rerun the domain adapter. Altering the carrier identity metric changes an already prepared severity and does not simulate a source rule. Retain the source checksum, complete adapter-configuration digest, adapter identifier/version and scoring norm fingerprint. The native norm fingerprint alone does not fingerprint all source interpretation rules.

Acceptance: a case spanning two months remains complete in a start-month cohort; cohort/reference policy is explicit; reordered case records and JSON norm roundtrips preserve results; threshold changes produce a separately identified assessment configuration.

## P1: source interpretation tests

Prepared-assessment consistency establishes arithmetic parity, not correctness of the adapter's event interpretation. Add independent adapter regression tests and verify actual source witnesses:

- Purchase-to-pay: endpoint selection with an unparseable candidate plus a valid candidate; earliest parsed endpoint outside the plausible range; tied endpoints; negative lags; legitimate repeated goods/invoice/payment instances; item/document relations; resource-marker availability and flow-specific scope. Clarify the current minimum-parsed-timestamp policy before changing it.
- Incidents: compressed A-A-B-A, non-immediate returns, missing teams without bridging, conflicting timestamp ties, changing product values, single-event cases, and active states after Completed. Record which cases are unavailable and why.
- Lending: lifecycle START versus resume/suspend/complete, offer identity reconciliation, no offer versus unusable offer evidence, resource completeness, timestamp-offset equivalence and boundary ramps. Counts and breadth do not assert work duration or ownership.

Synthetic fixtures are labelled rule tests and never empirical figures. Pair them with a small set of real source witnesses and describe witness selection bias.

## P2: uncertainty and outcome evaluation

- `stability(application, by, sampling_unit, seed, repetitions, data=None)`: whole-case or justified cluster resampling, priority intervals, shortlist selection frequency and cutoff diagnostics. Purchase-order items from the same document require a considered dependence policy. Gamma shrinkage is not statistical uncertainty.
- Optional lifecycle/congestion analysis: declared interval-pairing and overlap policies; active recorded intervals and queue episodes are proxies, not staff costs.
- Domain validation: process-owner review of norms, scope and weights; outcome labels and policy definitions; a prospective intervention/comparator design.
- Human evaluation: accuracy of concern identification, recognition of unavailable evidence, defensible evidence selection, inappropriate causal claims and time to investigation choice. Compare the same data and priorities with/without explanations.

Do not promise causal effects, savings, policy breaches or improved analyst decisions from current descriptive scores. Measure those outcomes separately.
