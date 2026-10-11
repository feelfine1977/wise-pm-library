# Process analysis notebooks

Start with the notebook for the challenge of interest. Each challenge analysis follows PM² from the business question through source checks, measured deviations, case evidence and proposals for a feasible process-improvement pilot.

Use the isolated **WISE paper (frozen)** environment for this repository. It prevents the frozen `wise` import from colliding with another package using the same import name.

The [Mac Jupyter guide](JUPYTER_ON_MAC.md) explains first setup, daily launch, kernel selection and stopping the server.

From this folder, run:

```sh
bash setup_environment.sh
bash start_jupyter.sh DATA_FOLDER
```

`DATA_FOLDER` is the folder containing the public logs. You can also set `WISE_PAPER_DATA` and call `start_jupyter.sh` without an argument. Select **WISE paper (frozen)** as the kernel. The launcher passes the data folder to the kernel without saving its value in a notebook. Setup creates the environment and installation snapshot inside this folder. After a library update, rerun setup and restart the kernel.

## Process evaluation

[WISE_Evaluation.ipynb](WISE_Evaluation.ipynb) calls the library for the 38 result items and draws Figures 4–6 from the verified purchase-to-pay dataset. Its comparison tables distinguish agreement, numerical differences and values that could not be computed.

## BPIC challenge analyses

There is one notebook per available challenge. The five BPIC 2015 municipalities and five BPIC 2020 travel extracts stay together in their challenge notebooks, with separate populations and results. BPIC 2013 includes the incident log and both problem-management logs. Archives and duplicate exports are not treated as additional challenges.

| Challenge | Process | Notebook | Main investigation |
|---|---|---|---|
| 2011 | Hospital patient histories | [Healthcare](BPIC2011_Healthcare_Analysis.ipynb) | Recorded activity intensity, patient context and the limits of episode interpretation |
| 2012 | Loan applications | [Lending](BPIC2012_Lending_Analysis.ipynb) | Document completion, customer contact and decision timing |
| 2013 | Incidents and problems | [Service management](BPIC2013_Incidents_Extended.ipynb) | Reassignment, problem lifecycle and unavailable endpoints |
| 2014 | Service restoration | [Service management](BPIC2014_Service_Analysis.ipynb) | Coordination, vendor dependencies and incident context |
| 2015 | Building permits | [Permits](BPIC2015_Permits_Analysis.ipynb) | Intake, acknowledgment and routing across five municipalities |
| 2017 | Loan applications | [Lending](BPIC2017_Lending_Extended.ipynb) | Stakeholder views, signed drivers and offer-related review |
| 2018 | Agricultural grants | [Grants](BPIC2018_Grants_Analysis.ipynb) | Payment exceptions, decision revisions and document-aware investigation |
| 2019 | Purchase-to-pay | [Purchase-to-pay](BPIC2019_PurchaseToPay_Extended.ipynb) | Business goals, receipt and payment evidence |
| 2020 | Travel administration | [Travel](BPIC2020_Travel_Analysis.ipynb) | Approval, returns and payment across five distinct extracts |

The BPIC 2011, 2012, 2014, 2015, 2018 and 2020 notebooks read the full bound source logs through [bpic_analysis.py](bpic_analysis.py). The compact [dataset specification](bpic_datasets.json) declares sources, native WISE norms, views, case attributes and unresolved business requirements. WISE performs constraint evaluation, scoring, grouped quantities, priorities, shortlist overlap and signed decomposition. The helper binds source records, prepares whole-case context and presents library results.

Each includes activity occurrence and case counts, severity beside evidence coverage, alternative whole-case cohorts, preference and cut-point sensitivity, original source witnesses, integrity checks, figures and an analysis journal. The proposals concern process changes, with an owner role, a business outcome and a quality safeguard. Diagnostic cut points require process-owner review; they are not inferred service agreements.

The BPIC 2013 notebook includes source-based problem-management analysis alongside its incident analysis.

The notebooks use the six stages of [PM²](https://vdaalst.com/publications/p824.pdf): Planning, Extraction, Data Processing, Mining & Analysis, Evaluation, and Process Improvement & Support. Their analysis journals distinguish executed checks from business interpretation and proposed pilots. Source-system review, process-owner validation and operational interventions remain open.

Case context belongs to the entire case. Start month, last-observed month and observed-span band are different choices; event-month fragments are not substituted. Derived months use UTC timestamps and recorded boundaries, rather than verified operational start or closure. Changing source attributes are flagged before cohort comparisons. Source witnesses retain their original fields; an assessment carrier is never presented as an original execution trace. Document-cycle matching and approved business policy remain separate requirements where the log does not establish them.

Each dataset has its own norm; its scores and priorities should be interpreted within that assessment. The separate [library extension guidance](LIBRARY_EXTENSION_HANDOFF.md) is intended for software developers.

## Sharing and outputs

Run all cells to obtain current tables, figures and the execution journal from the supplied data. The evaluation notebook contains saved results from a verified run; the nine challenge notebooks are saved without outputs. Compare source identity and norm with your current run before using saved results. Exports are optional. In the current saved configuration, `WISE_Evaluation.ipynb` enables figure export (`SAVE_FIGURES = True`), and the BPIC 2013, 2017 and 2019 notebooks enable result export (`SAVE_OUTPUTS = True`). Export is disabled in the BPIC 2011, 2012, 2014, 2015, 2018 and 2020 notebooks (`SAVE_OUTPUTS = False` or `EXPORT_RESULTS = False`). Set the relevant flag to `False` to display results without writing exports, or to `True` to create the local output folder declared by that notebook and save computed evidence there. Exported files are created when the notebook runs. Review saved case evidence and clear outputs as appropriate before sharing or committing.

Keep raw logs, configured data-folder values, environments, caches, extracted manuscript text and temporary executed notebooks out of version control.
