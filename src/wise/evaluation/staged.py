"""Run the BPIC'19 staged profile and the frozen comparison from the raw CSV."""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

import pandas as pd

import wise

from . import data, native, paper, replay
from .adapters import bpic2019, bpic2019_staged

CONTEXT = ["document", "vendor", "flow"]
WITNESS_IDS = ["4507005472_00040", "4508046750_00010", "4507007351_00010", "2000013508_00001"]


def evaluate(folder: Path | None, output: Path, *, figures: bool = True) -> dict:
    """Write the baseline/candidate BPIC'19 comparison and check native parity."""
    baseline, candidate = bpic2019_staged.assess_both(data.locate(bpic2019.APPLICATION, folder))
    names = candidate.configuration["baseline_views"]
    output.mkdir(parents=True, exist_ok=True)
    summary, backlogs, layer_parts, policy_rows, concentration, overlap, criteria = [], [], [], [], [], [], []
    score_export = candidate.features[CONTEXT + [
        "group", "completion_stage", "completion_assessment_reason", "goods_reversal_records", "df2_clearing_before_receipt_review",
        "repeat_invoice_review", "user_events", "user_identities", "all_resources_usable",
        "post_required_receipts_days", "goods_reversal_event_ids",
        "chronology_invoice_event_id", "chronology_receipt_event_id", "chronology_clear_event_id",
    ]].copy()
    diagnostics = score_export[[
        "group", "flow", "goods_reversal_records", "df2_clearing_before_receipt_review",
        "repeat_invoice_review", "all_resources_usable",
    ]].assign(goods_reversal_items=score_export.goods_reversal_records.gt(0))
    diagnostics.groupby(["group", "flow"]).agg(
        items=("goods_reversal_items", "size"),
        goods_reversal_items=("goods_reversal_items", "sum"),
        goods_reversal_records=("goods_reversal_records", "sum"),
        df2_chronology_items=("df2_clearing_before_receipt_review", "sum"),
        repeated_invoice_items=("repeat_invoice_review", "sum"),
        complete_resource_items=("all_resources_usable", "sum"),
    ).to_csv(output / "review_signals.csv")
    score_export.groupby(["group", "flow", "completion_stage", "completion_assessment_reason"]).size().rename("items").to_csv(
        output / "completion_stages.csv"
    )
    rankings = {}
    verification = {}
    for profile, assessment in (("baseline", baseline), ("staged", candidate)):
        scored = native.replay(assessment, attributes=assessment.features[CONTEXT])
        if profile == "staged":
            verification = replay.consistency(assessment, scored)
            verification["further_checks"] = replay.further_checks(assessment)
            if not verification["passed"] or not verification["further_checks"]["passed"]:
                raise ArithmeticError("staged norm failed native and reference checks")
        score_export = score_export.join(assessment.severity.add_prefix(f"{profile}_deviation_"))
        score_export = score_export.join(assessment.state.add_prefix(f"{profile}_state_"))
        for criterion in assessment.criteria:
            frame = assessment.features[["group", "flow"]].assign(
                state=assessment.state[criterion], positive=assessment.severity[criterion].gt(0),
                severity=assessment.severity[criterion],
            )
            criteria.append(frame.groupby(["group", "flow", "state"]).agg(
                items=("positive", "size"), positive=("positive", "sum"), mean_severity=("severity", "mean")
            ).reset_index().assign(profile=profile, criterion=criterion))
        for name, legacy in names.items():
            view = legacy if profile == "baseline" else name
            score = scored.scores[view]
            coverage = scored.coverage(view)
            score_export[f"{profile}_score_{name}"] = score
            score_export[f"{profile}_coverage_{name}"] = coverage
            summary.append({
                "profile": profile, "view": name, "native_view": view,
                "scored_items": int(score.notna().sum()), "mean_score": float(score.mean()),
                "mean_coverage": float(coverage.mean()),
            })
            for key in (native.GROUP, "document", "vendor"):
                backlog = wise.prioritize(scored, by=key, view=view)
                table = backlog.table.rename_axis("key").reset_index().assign(
                    profile=profile, view=name, grain=key,
                    rank=range(1, len(backlog.table) + 1),
                )
                backlogs.append(table)
                if key == native.GROUP:
                    signed = wise.layer_contributions(scored, backlog)
                    layer_parts.append(signed.rename_axis("group").reset_index().assign(profile=profile, view=name))
                    stable = wise.prioritize(scored, by=key, view=view, gamma=20).table
                    for rank, (label, row) in enumerate(stable.iterrows(), 1):
                        policy_rows.append({"profile": profile, "view": name, "group": label,
                                            "gamma": 20, "rank": rank, "priority": row.stable_PI})
                if key == "document":
                    rankings[profile, name] = table.key.tolist()
                    positive = table.loc[table.PI.gt(0), "PI"]
                    for threshold in (0.8, 0.95):
                        count = int((positive.cumsum() < threshold * positive.sum()).sum() + 1) if len(positive) else 0
                        concentration.append({"profile": profile, "view": name, "threshold": threshold,
                                              "documents": count, "positive_documents": len(positive),
                                              "all_documents": len(table)})
            packaging = assessment.groups.eq(paper.PACKAGING)
            vendor = (1 - score[packaging]).groupby(assessment.features.vendor[packaging]).agg(
                n_items="size", total_penalty="sum", mean_penalty="mean"
            ).sort_values("total_penalty", ascending=False, kind="stable")
            vendor.assign(profile=profile, view=name).to_csv(output / f"vendors_{profile}_{legacy}.csv")
        for a, b in combinations(names, 2):
            overlap.append({"comparison": profile, "view_a": a, "view_b": b,
                            "shared_top20": len(set(rankings[profile, a][:20]) & set(rankings[profile, b][:20]))})
    for name in names:
        old, new = (rankings[profile, name] for profile in ("baseline", "staged"))
        overlap.append({"comparison": "baseline_vs_staged", "view_a": name, "view_b": name,
                        "shared_top20": len(set(old[:20]) & set(new[:20])),
                        "shared_top100": len(set(old[:100]) & set(new[:100]))})
    pd.DataFrame(summary).to_csv(output / "view_summary.csv", index=False)
    pd.DataFrame(overlap).to_csv(output / "shortlist_overlap.csv", index=False)
    pd.DataFrame(policy_rows).to_csv(output / "group_gamma20.csv", index=False)
    pd.DataFrame(concentration).to_csv(output / "document_concentration.csv", index=False)
    pd.concat(criteria).to_csv(output / "criterion_states.csv", index=False)
    pd.concat(layer_parts).to_csv(output / "signed_group_layers.csv", index=False)
    ranked = pd.concat(backlogs, ignore_index=True)
    for grain, rows in ranked.groupby("grain"):
        rows.to_csv(output / f"backlog_{grain}.csv.gz", index=False)
    score_export.to_csv(output / "item_assessments.csv.gz")
    score_export.reindex(WITNESS_IDS).to_csv(output / "worked_items.csv")
    score_export.loc[score_export.goods_reversal_records.gt(0) |
                     score_export.df2_clearing_before_receipt_review].to_csv(output / "review_witnesses.csv.gz")
    if figures:
        _figures(ranked, summary, output)
    report = {
        "source": dict(candidate.source),
        "baseline_configuration_sha256": paper.configuration_sha256(baseline.configuration),
        "staged_configuration_sha256": paper.configuration_sha256(candidate.configuration),
        "staged_native_norm_fingerprint": native.native_norm(candidate.application).fingerprint(),
        "view_summary": summary, "shortlist_overlap": overlap, "verification": verification,
    }
    (output / "run_record.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report


def _figures(ranked: pd.DataFrame, summary: list[dict], output: Path) -> None:
    import matplotlib.pyplot as plt

    summaries = pd.DataFrame(summary)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
    for ax, measure, title in zip(axes, ("mean_score", "mean_coverage"), ("Mean score", "Mean weighted coverage")):
        summaries.pivot(index="view", columns="profile", values=measure).plot.bar(
            ax=ax, rot=12, color=["#8db6ab", "#155e54"], ylim=(0, 1), title=title
        )
        ax.set_xlabel("")
    fig.savefig(output / "view_comparison.png", dpi=175)
    plt.close(fig)
    groups = ranked.loc[ranked.grain.eq(native.GROUP) & ranked["rank"].le(5)]
    for name, rows in groups.groupby("view", sort=False):
        title = "Top business groups · " + name
        stem = next(x["native_view"] for x in summary if x["profile"] == "baseline" and x["view"] == name)
        fig, ax = plt.subplots(figsize=(9, 4), layout="constrained")
        rows.pivot(index="key", columns="profile", values="PI").plot.barh(ax=ax, title=title)
        ax.set(xlabel="Priority Index under each profile’s own reference", ylabel="")
        fig.savefig(output / f"groups_{stem}.png", dpi=175)
        plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, help="folder holding the verified BPIC'19 CSV")
    parser.add_argument("--output", type=Path, required=True, help="folder for the comparison")
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args(argv)
    result = evaluate(args.data, args.output, figures=not args.no_figures)
    print(json.dumps(result["view_summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
