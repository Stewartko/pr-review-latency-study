import pandas as pd
import numpy as np
import statsmodels.formula.api as smf

# Load dataset
df = pd.read_csv("data/analysis_prs.csv")

# Keep only valid human-reviewed PRs for RQ2
d = df[
    (df["eligible_rq1_basic"] == 1)
    & (df["author_is_bot"] == 0)
].copy()

# Drop missing values needed for the model
d = d.dropna(
    subset=[
        "pr_size",
        "contributor_experience",
        "first_review_latency_hours",
        "repo",
    ]
)

# Log-transform highly skewed variables
d["log_pr_size"] = np.log1p(d["pr_size"])
d["log_experience"] = np.log1p(d["contributor_experience"])
d["log_review_latency"] = np.log1p(d["first_review_latency_hours"])

# Center predictors before creating the interaction term
d["c_log_pr_size"] = (
    d["log_pr_size"] - d["log_pr_size"].mean()
)

d["c_log_experience"] = (
    d["log_experience"] - d["log_experience"].mean()
)

print("Rows used:", len(d))
print("Repositories:", d["repo"].nunique())

# Regression:
# - centered predictors
# - interaction term
# - repository fixed effects
# - cluster-robust standard errors by repository
model = smf.ols(
    formula="""
    log_review_latency
    ~ c_log_pr_size
    + c_log_experience
    + c_log_pr_size:c_log_experience
    + C(repo)
    """,
    data=d,
).fit(
    cov_type="cluster",
    cov_kwds={"groups": d["repo"]}
)

print(model.summary())

print("\nKEY COEFFICIENTS")

for name in [
    "c_log_pr_size",
    "c_log_experience",
    "c_log_pr_size:c_log_experience",
]:
    print(
        name,
        "coef=",
        round(model.params[name], 6),
        "p=",
        model.pvalues[name],
    )

print("\nMODEL INFO")
print("R-squared:", round(model.rsquared, 6))
print("Adjusted R-squared:", round(model.rsquared_adj, 6))
print("N:", int(model.nobs))
print("Repositories:", d["repo"].nunique())