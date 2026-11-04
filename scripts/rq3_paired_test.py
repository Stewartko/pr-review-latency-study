"""Supplementary RQ3 signed-rank test; never changes existing data or analyses.

The two-sided alternative and asymptotic computation were selected before
the supplementary test was first run. The original RQ is nondirectional
and its descriptive ordering was already known; this is exploratory inference.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
from scipy.stats import rankdata, spearmanr, wilcoxon


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('data/analysis_prs.csv'))
    parser.add_argument('--expected', type=Path,
                        default=Path('reference/article/rq3_per_repository.csv'))
    parser.add_argument('--output-dir', type=Path, default=Path('results'))
    args = parser.parse_args()

    cols = ['repo', 'pr_size', 'first_review_latency_hours', 'merge_latency_hours',
            'eligible_rq1_basic', 'eligible_merge_latency', 'author_is_bot']
    df = pd.read_csv(args.input, usecols=cols)
    common = df.loc[df.eligible_rq1_basic.eq(1)
                    & df.eligible_merge_latency.eq(1)
                    & df.author_is_bot.eq(0)].copy()
    required = ['repo', 'pr_size', 'first_review_latency_hours', 'merge_latency_hours']
    if common[required].isna().any().any():
        raise ValueError('Missing common-sample data: do not silently change eligibility.')
    rows = []
    for repo, group in common.groupby('repo', sort=True):
        if len(group) < 50:
            continue
        review = float(spearmanr(group.pr_size, group.first_review_latency_hours).statistic)
        merge = float(spearmanr(group.pr_size, group.merge_latency_hours).statistic)
        rows.append({'repo': repo, 'n': len(group), 'review_rho': review,
                     'merge_rho': merge, 'difference': merge-review})
    pairs = pd.DataFrame(rows).sort_values('repo').reset_index(drop=True)
    if len(common) != 243463 or len(pairs) != 84:
        raise ValueError('Frozen sample differs: expected 243,463 PRs and 84 repositories.')
    if not np.isfinite(pairs[['review_rho', 'merge_rho', 'difference']]).all().all():
        raise ValueError('Undefined correlation; no repository is silently removed.')
    expected = pd.read_csv(args.expected).sort_values('repo').reset_index(drop=True)
    if pairs.repo.tolist() != expected.repo.tolist():
        raise ValueError('Repository identities differ from the final comparison.')
    for column in ['n', 'review_rho', 'merge_rho', 'difference']:
        if not np.allclose(pairs[column], expected[column], atol=1e-14, rtol=0):
            raise ValueError(f'Final comparison differs in {column}.')

    # Fixed before execution; do not select an alternative based on the p-value.
    d = pairs.difference.to_numpy()
    result = wilcoxon(d, alternative='two-sided', zero_method='wilcox',
                      correction=False, method='asymptotic')
    nonzero = d[d != 0]
    ranks = rankdata(np.abs(nonzero))
    summary = {
        'common_sample_prs': len(common), 'common_sample_repositories': common.repo.nunique(),
        'n_repositories': len(pairs), 'minimum_prs_per_repository': 50,
        'positive_differences': int((d > 0).sum()),
        'negative_differences': int((d < 0).sum()),
        'zero_differences': int((d == 0).sum()),
        'tied_absolute_differences': len(nonzero)-len(np.unique(np.abs(nonzero))),
        'median_difference': float(np.median(d)),
        'review_rho_global': float(spearmanr(common.pr_size, common.first_review_latency_hours).statistic),
        'merge_rho_global': float(spearmanr(common.pr_size, common.merge_latency_hours).statistic),
        'test': 'Wilcoxon signed-rank', 'alternative': 'two-sided',
        'zero_method': 'wilcox', 'method': 'asymptotic', 'continuity_correction': False,
        'statistic': float(result.statistic), 'p_value': float(result.pvalue),
        'positive_rank_sum': float(ranks[nonzero > 0].sum()),
        'negative_rank_sum': float(ranks[nonzero < 0].sum()),
        'scipy_version': scipy.__version__, 'matches_final_comparison': True,
        'input_sha256': hashlib.file_digest(args.input.open('rb'), 'sha256').hexdigest(),
        'interpretation_scope': 'Exploratory unweighted repository-level comparison; not a test of the pooled rho difference or of causality.',
        'assumptions': 'Independent repository differences and a symmetric location model for a median-shift interpretation; heterogeneous rho estimates have unequal precision.'
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pairs.to_csv(args.output_dir/'rq3_paired_differences.csv', index=False)
    pd.DataFrame([summary]).to_csv(args.output_dir/'rq3_paired_test.csv', index=False)
    (args.output_dir/'rq3_paired_test.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    report = '\n'.join(f'{key}: {value}' for key, value in summary.items())+'\n'
    (args.output_dir/'rq3_paired_test.txt').write_text(report, encoding='utf-8')
    print(report)


if __name__ == '__main__':
    main()
