# Evaluation: WISE on the BPI Challenge 2019 log

This document summarises the evaluation of WISE on the BPI Challenge 2019 purchase-to-pay log. The complete evaluation, with every constraint, every number and the reason for every step, is the notebook [`notebooks/WISE_BPIC19_Evaluation_Story.ipynb`](notebooks/WISE_BPIC19_Evaluation_Story.ipynb). All numbers below are computed there; its last cell compares the numbers quoted in its text with the computed values.

The log has 1,595,923 events for 251,734 purchase order items in 76,349 purchasing documents. The case is the purchase order item. Every item follows one of four flow types: DF1 (3-way match, invoice after goods receipt), DF2 (3-way match, invoice before goods receipt allowed), 2-way match, and consignment. "Receipt" stands for a goods receipt or a service entry sheet.

## What is evaluated

The company behind the log asks, in the third question of the challenge: *"Which Purchase Documents stand out from the log? Where are deviations from the processes [...] and how severe are these deviations? Deviations may be according to the prescribed high-level process flow, but also with respect to the values of the invoices. Which customers produce a lot of rework as invoices are wrong, etc.?"* The process owner's concern is compliance, defined as: *"the amounts of the line item, the goods receipt messages (if applicable) and the invoices have to match"*.

| Part | The company asks | WISE output that answers it |
|---|---|---|
| Q3a | which purchasing documents stand out | Priority Index per purchasing document, one prioritised list per view |
| Q3b | where the deviations are | Priority Index per slice (spend area and flow type) and per layer; drill-down to vendor |
| Q3c | how severe they are | deviation scores between 0 and 1; rate of deviating cases in a slice against all other cases |
| Q3d | in the process flow, and in the invoice values | separate layers for flow and for values |
| Q3e | who produces rework | a rework layer; Priority Index per vendor |

Answering this question is the task. The evaluation asks whether WISE does the task well:

| ID | Evaluation question | It fails if | Result |
|---|---|---|---|
| EQ1 | Can the owner's stated requirements be written as a WISE norm? | a requirement cannot be expressed, or needs data the log does not have | Twelve constraints: ten use the five constraint types, two need an order constraint, three rest on what a sentence implies. The refined norm adds three constraints of our own |
| EQ2 | Do the leading priorities point where the requirements are most often broken? | a priority only reflects size, missing data or an artefact | Each leading slice shows a large difference in a plain rate, so the priorities are not an effect of slice size. Whether a deviation is a real problem is left to the first check |
| EQ3 | Can a priority be traced back to a constraint, to cases and to the recorded events? | the explanation does not match the records | Every leading slice followed to one constraint, to vendors and documents; one case to its events. The drill-down also corrected the norm once |
| EQ4 | Do different views lead to different priorities? | every view gives the same list | Weights on one combined score did not separate the perspectives, in step 1 and in step 2. One Priority Index per layer and the two combined views do |
| EQ5 | Are the priorities stable when assessment settings are changed within reason? | the order flips under small changes | The first three slices of Flow, Value, Rework and Compliance are stable under seven changed settings; Timeliness only in its first slice |

## The evaluation in three steps

| Step | What is done | What the assessment shows | Why the next step follows |
|---|---|---|---|
| 1. A norm from the owner's words | Twelve constraints are taken sentence by sentence from the challenge description, in three layers: Flow, Value, Invoice rework. All 251,734 cases are scored. | Logistics DF1 has the highest Priority Index in every view. Below it, 16 of the 20 leading documents and the leading vendor consist mostly of deleted or recently created items. | The list says something about the norm, not about the process: the norm judges cases that cannot be judged yet. |
| 2. The refined norm | Deleted items leave the business scope; constraints that wait for an event need 90 days of observation; clearing before receipt is assessed only for recorded invoices; the value constraints become one; Timeliness is added as a layer of its own; Rework is widened. 242,895 cases are scored. | Missing invoice receipts fall from 25,857 to 7,931 and missing clearings from 28,086 to 3,153. Every kind of deviation is visible in a constraint, but one combined ranking puts Packaging DF2 first in all five views. | Timeliness contributes 0.046 of the 0.066 mean case deviation score. One concern hides the others, and the company asks about them separately. |
| 3. One Priority Index per layer | The Priority Index is computed under four single-layer views and two combined views, Compliance (Flow, Value, Rework) and Payment performance (adds Timeliness). | Each layer has one clearly leading slice, in three different places. The two combined views put different slices first. | This step was taken after the weighted views had failed; it answers a negative result. |

## Step 1: the first norm

| ID | Statement in the challenge description | Constraint | Type | Flow types | Violated in step 1 |
|---|---|---|---|---|---:|
| A1 | "Purchase Items that do require a goods receipt message" | a receipt is recorded | presence | DF1, DF2, consignment | 16,210 of 250,690 |
| A2 | "goods receipt messages and corresponding invoices" (implied) | an invoice receipt is recorded | presence | DF1, DF2, 2-way | 25,857 of 237,236 |
| A3 | "corresponding invoices which are subsequently paid" (implied) | a recorded invoice is cleared | presence | DF1, DF2, 2-way | 28,086 of 211,379 |
| A4 | "3-way matching, invoice after goods receipt" | the invoice receipt does not precede the receipt | order | DF1 | 0 of 11,128 |
| A5 | "Invoices should only be cleared if goods are received" | clearing does not precede the receipt | order | DF1, DF2 | 655 of 183,374 |
| A6 | "there are no invoices on PO level" | no invoice receipt and no clearing on the item | exclusion | consignment | 0 of 14,498 |
| B1 | "the value of the goods receipt message should be matched against the value of an invoice receipt message" | receipt value equals invoice value | balance | DF1, DF2 | 1,633 of 210,370 |
| B2 | "... and the value put during creation of the item" | invoice value equals the value at creation | balance | DF1, DF2 | 1,502 of 210,692 |
| B3 | "match the value at creation (in full or partially until PO value is consumed)" | invoice value is not above the value at creation | balance, one-sided | 2-way | 0 of 687 |
| B4 | "corresponding invoices which are subsequently paid" (implied) | cleared value equals invoice value | balance | DF1, DF2, 2-way | 1,354 of 183,293 |
| C1 | "rework as invoices are wrong" | invoice receipts are not cancelled | singularity | DF1, DF2, 2-way | 6,471 of 237,236 |
| C2 | same | no debit memo and no subsequent-invoice correction | singularity | DF1, DF2, 2-way | 6,098 of 237,236 |

Three constraints have no violation at all (A4, A6, B3). This is a sanity check, not a proof: the company's system may not allow these bookings.

Left out on purpose, with the owner's words as the reason: a limit on the number of receipts or invoices ("there can be many goods receipt messages and corresponding invoices"), and a limit on payment time (the owner asks how long payment takes, not how long is too long).

The layers: **Flow** is about whether and when the prescribed steps happen, **Value** about whether the amounts ordered, received, invoiced and cleared agree, and **Invoice rework** about invoices that had to be corrected.

What the first assessment shows about the norm:

| Observation | Count |
|---|---|
| The log ends before recent orders can finish | cases with an invoice but no clearing: 1.5% of items created in January, 90.4% of items created in December |
| Deleted items are judged as if they were live | of 25,857 cases without invoice receipt, 8,106 are deleted and 12,820 were created from September; 95.8% of deleted 3-way items have no receipt, against 3.1% of the others |
| The value constraints count one deviation several times | 1,331 of 1,498 cases that violate B1, B2 or B4 violate all three |
| A clearing is not always a payment | of 566 cases cleared with no receipt recorded, 376 have no invoice receipt either and 511 carry an invoice cancellation: the clearing closes a reversal |
| Some recorded behaviour has no constraint | 26,489 items with a price or quantity change (25,441 of 33,872 change events before the first invoice receipt); 2,470 items with a cancelled goods receipt; payment time measurable for 77.2% of invoiced cases |

## Step 2: the refined norm

| Change | Caused by | Why in this form |
|---|---|---|
| Deleted items are outside business scope | deleted items lack receipts by nature | neither a deviation nor a satisfied constraint would be right; both would distort the comparison reference |
| A1 to A3 are evaluated only after 90 days of observation | the log ends before recent items can finish | recent cases stay in the assessment for everything already known about them; 90 days because the share of missing records is flat until the summer and rises in the last three to four months |
| A2 in DF1 waits for a receipt; A3 waits for an invoice and, in 3-way flows, a receipt | one missing step was counted again as the next | each case is asked only the next open question |
| A5 applies only to cases with an invoice receipt | a clearing can also close a cancellation | the concern is paying before the goods arrive |
| One value constraint B1: the largest mismatch among the value pairs | 1,331 of 1,498 cases violated three constraints together | the pairs compare the same few amounts; one disagreement counts once |
| New layer Timeliness (T1): days from readiness to clearing, no deviation up to the median (44.4 days), full deviation from the 90th percentile (99.0 days) | payment time is measurable but had no constraint | the owner asks how long payment takes; no payment terms are known, so the scale is relative to the log and kept in a layer of its own |
| Rework gains C3 (price or quantity changes) and C4 (cancelled goods receipts) | recorded corrections on orders and receipts had no constraint | the owner asks about rework "etc."; counts of receipts or invoices remain no deviation |
| The case score is the weighted mean of layer deviation scores (two-stage weighting, normalised inside each layer first) | layers have different numbers of constraints | a layer's influence should not depend on how many constraints it has |
| Consignment cases are compared with other consignment cases | only Flow and Rework apply to them | scores built from different constraints should not share one reference |

| ID | Layer | In scope | Evaluated | Violated | Share of evaluated |
|---|---|---:|---:|---:|---:|
| A1 | Flow | 241,860 | 205,764 | 2,901 | 1.41% |
| A2 | Flow | 228,488 | 193,896 | 7,931 | 4.09% |
| A3 | Flow | 210,772 | 166,770 | 3,153 | 1.89% |
| A4 | Flow | 14,853 | 11,121 | 0 | 0% |
| A5 | Flow | 182,715 | 182,715 | 255 | 0.14% |
| A6 | Flow | 14,076 | 14,076 | 0 | 0% |
| B1 | Value | 228,819 | 211,068 | 1,659 | 0.79% |
| T1 | Timeliness | 210,772 | 160,677 | 80,312 | 49.98% |
| C1 | Rework | 228,819 | 228,819 | 6,431 | 2.81% |
| C2 | Rework | 228,819 | 228,819 | 6,058 | 2.65% |
| C3 | Rework | 242,895 | 242,895 | 25,975 | 10.69% |
| C4 | Rework | 241,860 | 241,860 | 2,395 | 0.99% |

A constraint is, for each case, outside business scope, in scope with evidence unavailable, or evaluated. Only an evaluated constraint produces a deviation score. T1 exceeds the median for half of its cases by construction and is evaluated only for cleared cases with at least 100 days of observation. In the table of changes, Timeliness, C3 and C4 are additions of our own; the other changes are corrections that follow from counts.

Payment time, measured (days from readiness to clearing, median): Packaging about 71; Latex & Monomers, Specialty Resins, Solvents and Additives 55 to 58; Trading & End Products 27; Sales and Logistics 24; CAPEX & SOCS 17. The pattern looks like payment terms that differ by category. The log has no due dates, so a Timeliness deviation means "cleared more slowly than most invoices in this log", not "late".

## Step 3: one Priority Index per layer

Priority Index of the slices that lead a layer (slice = spend area and flow type; number of scored cases in brackets):

| Slice | Flow | Value | Timeliness | Rework | Compliance | Payment performance |
|---|---:|---:|---:|---:|---:|---:|
| Logistics, DF1 (4,565) | 986 | 1,200 | 0 | 28 | 903 | 639 |
| Trading & End Products, DF2 (20,147) | 176 | 0 | 0 | 458 | 246 | 0 |
| Logistics, DF2 (614) | 182 | 0 | 0 | 0 | 89 | 61 |
| Trading & End Products, DF1 (837) | 30 | 40 | 0 | 7 | 29 | 4 |
| Packaging, DF2 (92,361) | 0 | 0 | 15,465 | 0 | 0 | 3,378 |

Any two single-layer views share at most two of their five leading slices. The Compliance view puts Logistics DF1 first; the Payment performance view puts Packaging DF2 first.

## Findings

| # | Finding | Constraint and rate (slice against all other evaluated cases) | What it means for the company | First check |
|---|---|---|---|---|
| 1 | Logistics services are received, but no invoice is recorded | A2: 2,080 of 3,744 = 55.6% against 3.1% | the receipt has booked the cost and the amount waits for an invoice that never arrives on the order: old open amounts, or carrier invoices posted without order reference, so that the check against order and receipt did not take place | are there invoices from the leading carriers without an order reference? |
| 2 | For logistics services, the recorded values do not agree | B1: 1,393 of 1,825 = 76.3% against 0.1% | the owner's definition of compliance cannot be confirmed for transport services; most likely a convention in how values are recorded for service items | compare a few items with the company's system; what does the value column contain for service items? |
| 3 | Packaging, labels in particular, is cleared much later than the rest | T1: 51,277 of 67,901 = 75.5% against 31.3%; about 70 days with or without a removed payment block | cash stays in the company for longer; a risk only if the agreed terms are shorter | what are the payment terms of the four leading label vendors? |
| 4 | Orders for trading goods are changed after they are placed | C3: 4,897 of 20,147 = 24.3% against 9.6%; two thirds are quantity changes; 6,222 of 7,724 change events before the first invoice receipt; one vendor holds about half of the priority | corrections to placed orders; the source is the order, not the invoice | why are this vendor's orders changed, and which were changed after the invoice? |
| 5 | Some orders consist only of reversals | 817 cases in 170 documents hold a cancelled receipt and a cancelled invoice, but neither the receipt nor the invoice receipt; two vendors hold 442 of them | a delivery was booked in, invoiced and taken back completely: work done twice for a whole order | what was reversed in the leading documents, and why? |

Documents: under the Compliance view 16,805 of 74,382 assessed documents have a positive Priority Index, and 4,672 of them hold 80% of it. The first document is one of the reversed orders of finding 5. For the Value layer the vendor is the better unit, because the deviations sit in many small documents.

The notebook gives, for each finding, possible explanations and possible actions. These come from general purchasing practice and depend on the outcome of the first check.

## Checks

- **Slicing scheme.** 63 schemes built from one to three of seven case attributes were compared per layer by their concentration (Priority Index of the five leading slices divided by the attainable priority). The stabilised Priority Index with shrinkage constant 20 is used. Spend area and flow type is within a few points of the best scheme in every layer: Flow 0.24 against 0.30, Value 0.91 against 0.91, Timeliness 0.61 against 0.63, Rework 0.16 against 0.18. It is not the best scheme in any single layer; spend area alone, or with company, is slightly better for Flow and Rework. The flow type is kept because it decides which constraints apply and separates Logistics DF1 from Logistics DF2.
- **Assessment settings.** Seven settings were changed one at a time (evidence after 60 and 120 days; three alternative scales of the lag constraint; balance tolerance 5%; singularity saturation at 5). Value keeps all five leading slices. Flow, Rework and Compliance keep their first three and at least four of the five. Timeliness always keeps Packaging first; the slices below it move with the scale.
- **Drill-down.** One case of the leading Flow slice is followed to its recorded events and to the state and deviation score of every constraint. The drill-down of the leading document produced finding 5.

## What stays open

- The log shows where records deviate from the constraints, not why. An invoice may be missing or only not linked; a payment may be late or on agreed terms; values may be wrong or recorded by a convention.
- A clearing is not a payment. The log has no payment event, no due dates, no payment terms and no links that say which invoice belongs to which receipt.
- The norm was refined on the log it is applied to; there is no second log on which the refined norm could be tested. The requirements were read from a text, not agreed with the company.
- The norm does not see what is unusual without violating a constraint. It uses the first event of a kind and counts of events, not matched receipt, invoice and payment cycles.
- The scale of Timeliness, the 90 days of observation, the 1% value tolerance and the saturation at three events are settings. The checks show which results depend on them. With 90 days, an invoice on longer terms can be assessed as not cleared: about one cleared case in eight takes longer than 90 days.
- The findings are places to look, not confirmed problems.
- Three constraints of the first norm rest on what the owner's text implies (A2, A3, B4).

## Additional tests

The package also holds reference assessments of three logs with expected values, used as regression tests. They use other norms and are listed in [`tests/evaluation/EXPECTED_VALUES.md`](tests/evaluation/EXPECTED_VALUES.md).
