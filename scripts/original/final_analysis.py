import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


INPUT = Path("data/analysis_prs.csv")
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)


def spearman_result(df, x, y):
    d = df.dropna(subset=[x, y])

    if len(d) < 3:
        return {
            "n": len(d),
            "rho": np.nan,
            "p_value": np.nan,
        }

    result = spearmanr(d[x], d[y])

    return {
        "n": len(d),
        "rho": result.statistic,
        "p_value": result.pvalue,
    }


def describe_series(series):
    s = series.dropna()

    return {
        "count": len(s),
        "mean": s.mean(),
        "std": s.std(),
        "min": s.min(),
        "q25": s.quantile(0.25),
        "median": s.median(),
        "q75": s.quantile(0.75),
        "max": s.max(),
    }


def main():
    print("Loading dataset...")
    df = pd.read_csv(INPUT)

    print(f"Rows: {len(df):,}")
    print(f"Repositories: {df['repo'].nunique():,}")

    # ---------------------------------------------------------
    # BASIC DATASET SUMMARY
    # ---------------------------------------------------------

    human_df = df[df["author_is_bot"] == 0].copy()

    summary = {
        "repositories": df["repo"].nunique(),
        "all_prs": len(df),
        "human_prs": len(human_df),
        "bot_prs": int(df["author_is_bot"].sum()),
        "rq1_eligible": int(df["eligible_rq1_basic"].sum()),
        "rq1_strict_eligible": int(
            df["eligible_rq1_strict_no_draft_history"].sum()
        ),
        "merge_eligible": int(df["eligible_merge_latency"].sum()),
        "unique_human_contributors": human_df["author_login"].nunique(),
    }

    summary_df = pd.DataFrame(
        [{"metric": k, "value": v} for k, v in summary.items()]
    )

    summary_df.to_csv(
        RESULTS_DIR / "dataset_summary.csv",
        index=False
    )

    print("\nDATASET SUMMARY")
    print(summary_df.to_string(index=False))

    # ---------------------------------------------------------
    # DESCRIPTIVE STATISTICS
    # ---------------------------------------------------------

    variables = {
        "pr_size": human_df["pr_size"],
        "first_review_latency_hours": human_df[
            "first_review_latency_hours"
        ],
        "merge_latency_hours": human_df[
            "merge_latency_hours"
        ],
        "contributor_experience": human_df[
            "contributor_experience"
        ],
    }

    descriptive_rows = []

    for variable, series in variables.items():
        values = describe_series(series)
        values["variable"] = variable
        descriptive_rows.append(values)

    descriptive_df = pd.DataFrame(descriptive_rows)

    columns_order = [
        "variable",
        "count",
        "mean",
        "std",
        "min",
        "q25",
        "median",
        "q75",
        "max",
    ]

    descriptive_df = descriptive_df[columns_order]

    descriptive_df.to_csv(
        RESULTS_DIR / "descriptive_statistics.csv",
        index=False
    )

    print("\nDESCRIPTIVE STATISTICS")
    print(descriptive_df.to_string(index=False))

    # ---------------------------------------------------------
    # RQ1 MAIN ANALYSIS
    # ---------------------------------------------------------

    rq1 = df[
        (df["eligible_rq1_basic"] == 1)
        & (df["author_is_bot"] == 0)
    ].copy()

    rq1_main = spearman_result(
        rq1,
        "pr_size",
        "first_review_latency_hours"
    )

    # ---------------------------------------------------------
    # RQ1 STRICT: NO DRAFT HISTORY
    # ---------------------------------------------------------

    rq1_strict = df[
        (df["eligible_rq1_strict_no_draft_history"] == 1)
        & (df["author_is_bot"] == 0)
    ].copy()

    rq1_no_drafts = spearman_result(
        rq1_strict,
        "pr_size",
        "first_review_latency_hours"
    )

    # ---------------------------------------------------------
    # RQ1 SENSITIVITY: REMOVE TOP 1% PR SIZE
    # ---------------------------------------------------------

    pr_size_cutoff = rq1["pr_size"].quantile(0.99)

    rq1_no_large_prs = rq1[
        rq1["pr_size"] <= pr_size_cutoff
    ]

    rq1_size_trimmed = spearman_result(
        rq1_no_large_prs,
        "pr_size",
        "first_review_latency_hours"
    )

    # ---------------------------------------------------------
    # RQ1 SENSITIVITY: REMOVE TOP 1% LATENCY
    # ---------------------------------------------------------

    latency_cutoff = rq1[
        "first_review_latency_hours"
    ].quantile(0.99)

    rq1_no_long_latency = rq1[
        rq1["first_review_latency_hours"] <= latency_cutoff
    ]

    rq1_latency_trimmed = spearman_result(
        rq1_no_long_latency,
        "pr_size",
        "first_review_latency_hours"
    )

    # ---------------------------------------------------------
    # RQ1 SENSITIVITY: REMOVE BOTH TOP 1%
    # ---------------------------------------------------------

    rq1_trimmed_both = rq1[
        (rq1["pr_size"] <= pr_size_cutoff)
        & (
            rq1["first_review_latency_hours"]
            <= latency_cutoff
        )
    ]

    rq1_both_trimmed = spearman_result(
        rq1_trimmed_both,
        "pr_size",
        "first_review_latency_hours"
    )

    rq1_rows = [
        {
            "analysis": "main",
            **rq1_main
        },
        {
            "analysis": "strict_no_draft_history",
            **rq1_no_drafts
        },
        {
            "analysis": "remove_top_1pct_pr_size",
            **rq1_size_trimmed
        },
        {
            "analysis": "remove_top_1pct_review_latency",
            **rq1_latency_trimmed
        },
        {
            "analysis": "remove_top_1pct_both",
            **rq1_both_trimmed
        },
    ]

    rq1_df = pd.DataFrame(rq1_rows)

    rq1_df.to_csv(
        RESULTS_DIR / "rq1_sensitivity.csv",
        index=False
    )

    print("\nRQ1 SENSITIVITY ANALYSIS")
    print(rq1_df.to_string(index=False))

    print("\nRQ1 CUT-OFFS")
    print(
        f"99th percentile PR size: "
        f"{pr_size_cutoff:,.2f}"
    )

    print(
        f"99th percentile first-review latency: "
        f"{latency_cutoff:,.2f} hours"
    )

    # ---------------------------------------------------------
    # RQ1 PER-REPOSITORY ANALYSIS
    # ---------------------------------------------------------

    per_repo_rows = []

    for repo, group in rq1.groupby("repo"):

        if len(group) < 50:
            continue

        result = spearman_result(
            group,
            "pr_size",
            "first_review_latency_hours"
        )

        per_repo_rows.append({
            "repo": repo,
            **result
        })

    per_repo_df = pd.DataFrame(per_repo_rows)

    per_repo_df.to_csv(
        RESULTS_DIR / "rq1_per_repository.csv",
        index=False
    )

    positive = (per_repo_df["rho"] > 0).sum()
    negative = (per_repo_df["rho"] < 0).sum()

    print("\nRQ1 PER REPOSITORY")
    print(
        f"Repositories with >=50 valid PRs: "
        f"{len(per_repo_df)}"
    )

    print(
        f"Positive rho: {positive}"
    )

    print(
        f"Negative rho: {negative}"
    )

    print(
        f"Median repository rho: "
        f"{per_repo_df['rho'].median():.4f}"
    )

    # ---------------------------------------------------------
    # RQ3 COMMON DATASET
    # ---------------------------------------------------------

    rq3 = df[
        (df["eligible_rq1_basic"] == 1)
        & (df["eligible_merge_latency"] == 1)
        & (df["author_is_bot"] == 0)
    ].copy()

    review_result = spearman_result(
        rq3,
        "pr_size",
        "first_review_latency_hours"
    )

    merge_result = spearman_result(
        rq3,
        "pr_size",
        "merge_latency_hours"
    )

    rq3_global = pd.DataFrame([
        {
            "outcome": "first_review_latency",
            **review_result
        },
        {
            "outcome": "merge_latency",
            **merge_result
        },
    ])

    rq3_global["rho_difference_from_review"] = (
        rq3_global["rho"]
        - review_result["rho"]
    )

    rq3_global.to_csv(
        RESULTS_DIR / "rq3_global.csv",
        index=False
    )

    print("\nRQ3 GLOBAL")
    print(rq3_global.to_string(index=False))

    # ---------------------------------------------------------
    # RQ3 PER REPOSITORY
    # ---------------------------------------------------------

    rq3_repo_rows = []

    for repo, group in rq3.groupby("repo"):

        if len(group) < 50:
            continue

        review = spearman_result(
            group,
            "pr_size",
            "first_review_latency_hours"
        )

        merge = spearman_result(
            group,
            "pr_size",
            "merge_latency_hours"
        )

        rq3_repo_rows.append({
            "repo": repo,
            "n": len(group),
            "review_rho": review["rho"],
            "merge_rho": merge["rho"],
            "difference": (
                merge["rho"] - review["rho"]
            ),
        })

    rq3_repo_df = pd.DataFrame(rq3_repo_rows)

    rq3_repo_df.to_csv(
        RESULTS_DIR / "rq3_per_repository.csv",
        index=False
    )

    merge_stronger = (
        rq3_repo_df["difference"] > 0
    ).sum()

    review_stronger = (
        rq3_repo_df["difference"] < 0
    ).sum()

    print("\nRQ3 PER REPOSITORY")
    print(
        f"Repositories compared: "
        f"{len(rq3_repo_df)}"
    )

    print(
        f"Merge relationship stronger: "
        f"{merge_stronger}"
    )

    print(
        f"Review relationship stronger: "
        f"{review_stronger}"
    )

    print(
        f"Median review rho: "
        f"{rq3_repo_df['review_rho'].median():.4f}"
    )

    print(
        f"Median merge rho: "
        f"{rq3_repo_df['merge_rho'].median():.4f}"
    )

    print(
        f"Median difference: "
        f"{rq3_repo_df['difference'].median():.4f}"
    )

    # ---------------------------------------------------------
    # REPOSITORY SIZE CONTRIBUTION
    # ---------------------------------------------------------

    repo_counts = (
        df.groupby("repo")
        .size()
        .sort_values(ascending=False)
        .reset_index(name="pr_count")
    )

    repo_counts["dataset_share"] = (
        repo_counts["pr_count"] / len(df)
    )

    repo_counts.to_csv(
        RESULTS_DIR / "repository_distribution.csv",
        index=False
    )

    print("\nTOP REPOSITORIES")
    print(
        repo_counts.head(20).to_string(index=False)
    )

    # ---------------------------------------------------------
    # FINAL MESSAGE
    # ---------------------------------------------------------

    print("\n--------------------------------")
    print("FINAL ANALYSIS COMPLETE")
    print("--------------------------------")

    print(
        f"Results saved to: "
        f"{RESULTS_DIR.resolve()}"
    )


if __name__ == "__main__":
    main()