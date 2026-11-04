import pandas as pd
import numpy as np
from scipy.stats import spearmanr

df = pd.read_csv("data/analysis_prs.csv")

# Použijeme len ľudské PR, ktoré majú zároveň:
# - valid first review
# - valid merge latency
d = df[
    (df["eligible_rq1_basic"] == 1)
    & (df["eligible_merge_latency"] == 1)
    & (df["author_is_bot"] == 0)
].copy()

d = d.dropna(
    subset=[
        "pr_size",
        "first_review_latency_hours",
        "merge_latency_hours",
    ]
)

print("Common dataset size:", len(d))
print("Repositories:", d["repo"].nunique())

rho_review, p_review = spearmanr(
    d["pr_size"],
    d["first_review_latency_hours"]
)

rho_merge, p_merge = spearmanr(
    d["pr_size"],
    d["merge_latency_hours"]
)

print("\nRQ3 - COMMON DATASET")
print(
    "PR size vs first-review latency:",
    "rho =", round(rho_review, 6),
    "p =", p_review
)

print(
    "PR size vs merge latency:",
    "rho =", round(rho_merge, 6),
    "p =", p_merge
)

print(
    "\nDifference in rho:",
    round(rho_merge - rho_review, 6)
)

# Per-repository comparison
rows = []

for repo, g in d.groupby("repo"):
    if len(g) < 50:
        continue

    review_rho = spearmanr(
        g["pr_size"],
        g["first_review_latency_hours"]
    ).statistic

    merge_rho = spearmanr(
        g["pr_size"],
        g["merge_latency_hours"]
    ).statistic

    rows.append({
        "repo": repo,
        "N": len(g),
        "review_rho": review_rho,
        "merge_rho": merge_rho,
        "difference": merge_rho - review_rho,
    })

result = pd.DataFrame(rows)

print("\nPER-REPOSITORY COMPARISON")
print(
    result
    .sort_values("N", ascending=False)
    .head(50)
    .to_string(index=False)
)

print("\nSUMMARY OF PER-REPOSITORY EFFECTS")
print(
    result[
        ["review_rho", "merge_rho", "difference"]
    ].describe()
)

print("\nRepositories where merge relationship is stronger:")
print((result["difference"] > 0).sum())

print("Repositories where review relationship is stronger:")
print((result["difference"] < 0).sum())

print("Total repositories compared:")
print(len(result))