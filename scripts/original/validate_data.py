import sqlite3
from pathlib import Path
import pandas as pd

CSV_PATH = Path('data/analysis_prs.csv')
DB_PATH = Path('study.sqlite3')


def section(title):
    print('\n' + '=' * 72)
    print(title)
    print('=' * 72)


def check(name, condition, details=''):
    status = 'PASS' if condition else 'FAIL'
    print(f'[{status}] {name}')
    if details:
        print(f'       {details}')
    return condition


def info(name, value):
    print(f'[INFO] {name}: {value}')


def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f'Missing {CSV_PATH}. Run build_dataset.py first.')

    df = pd.read_csv(CSV_PATH)

    required = [
        'repo', 'pr_number', 'author_login', 'author_is_bot', 'pr_size',
        'created_at', 'first_external_human_review_at',
        'first_review_latency_hours', 'merged_at', 'merge_latency_hours',
        'contributor_experience', 'eligible_rq1_basic',
        'eligible_rq1_strict_no_draft_history', 'eligible_merge_latency'
    ]

    section('1. DATASET STRUCTURE')
    missing = [c for c in required if c not in df.columns]
    check('All required columns are present', not missing,
          'Missing: ' + ', '.join(missing) if missing else '')
    if missing:
        return

    info('Rows', f'{len(df):,}')
    info('Repositories', f"{df['repo'].nunique():,}")
    info('Unique authors', f"{df['author_login'].nunique(dropna=True):,}")

    section('2. DUPLICATES')
    duplicate_prs = df.duplicated(subset=['repo', 'pr_number']).sum()
    check('No duplicate PRs by (repo, pr_number)', duplicate_prs == 0,
          f'Duplicate rows: {duplicate_prs:,}')

    section('3. BOT FILTERING')
    bot_rows = df[df['author_is_bot'] == 1]
    human_rows = df[df['author_is_bot'] == 0]
    info('Bot-authored PRs', f'{len(bot_rows):,}')
    info('Human-authored PRs', f'{len(human_rows):,}')

    bots_in_rq1 = bot_rows['eligible_rq1_basic'].fillna(0).astype(int).sum()
    check('Bot PRs are excluded from RQ1 eligibility', bots_in_rq1 == 0,
          f'Bot PRs marked eligible_rq1_basic=1: {bots_in_rq1:,}')

    bots_merge_eligible = bot_rows['eligible_merge_latency'].fillna(0).astype(int).sum()
    info('Bot PRs with eligible_merge_latency=1',
         f'{bots_merge_eligible:,} (acceptable only if RQ3 also filters author_is_bot == 0)')

    section('4. FIRST-REVIEW LATENCY')
    negative_review = df[
        df['first_review_latency_hours'].notna()
        & (df['first_review_latency_hours'] < 0)
    ]
    info('Negative first-review latency rows', len(negative_review))

    neg_eligible = (
        negative_review['eligible_rq1_basic'].fillna(0).astype(int) == 1
    ).sum()
    check('No negative-latency PR is eligible for RQ1', neg_eligible == 0,
          f'Eligible negative rows: {neg_eligible:,}')

    if len(negative_review) > 0:
        print('\nNegative first-review latency examples:')
        cols = ['repo', 'pr_number', 'created_at',
                'first_external_human_review_at', 'first_review_latency_hours']
        print(negative_review[cols].head(20).to_string(index=False))

    rq1 = df[(df['eligible_rq1_basic'] == 1) & (df['author_is_bot'] == 0)].copy()
    check('All RQ1 rows have non-negative first-review latency',
          (rq1['first_review_latency_hours'] >= 0).all())
    check('All RQ1 rows have a first-review timestamp',
          rq1['first_external_human_review_at'].notna().all())
    check('All RQ1 rows have non-negative PR size', (rq1['pr_size'] >= 0).all())
    section('5. MERGE LATENCY')
    merge = df[(df['eligible_merge_latency'] == 1) & (df['author_is_bot'] == 0)].copy()
    check('All merge-eligible human PRs have non-negative merge latency',
          (merge['merge_latency_hours'] >= 0).all())
    check('All merge-eligible human PRs have merged_at', merge['merged_at'].notna().all())

    section('6. CONTRIBUTOR EXPERIENCE')
    exp_missing = rq1['contributor_experience'].isna().sum()
    exp_negative = (rq1['contributor_experience'].fillna(0) < 0).sum()
    check('Contributor experience is present for all RQ1 PRs', exp_missing == 0,
          f'Missing values: {exp_missing:,}')
    check('Contributor experience is never negative', exp_negative == 0,
          f'Negative values: {exp_negative:,}')
    info('Contributor experience median', rq1['contributor_experience'].median())
    info('Contributor experience max', rq1['contributor_experience'].max())

    section('7. RQ SAMPLE SIZES')
    rq1_strict = df[
        (df['eligible_rq1_strict_no_draft_history'] == 1)
        & (df['author_is_bot'] == 0)
    ].copy()
    rq2 = rq1.dropna(subset=['pr_size', 'contributor_experience',
                             'first_review_latency_hours', 'repo'])
    rq3 = df[
        (df['eligible_rq1_basic'] == 1)
        & (df['eligible_merge_latency'] == 1)
        & (df['author_is_bot'] == 0)
    ].copy()

    info('RQ1 main sample', f'{len(rq1):,}')
    info('RQ1 strict no-draft sample', f'{len(rq1_strict):,}')
    info('RQ2 model sample', f'{len(rq2):,}')
    info('RQ3 common sample', f'{len(rq3):,}')
    check('Strict RQ1 sample is a subset of basic RQ1 sample', len(rq1_strict) <= len(rq1))
    check('RQ3 common sample is not larger than RQ1', len(rq3) <= len(rq1))

    section('8. EXTREME VALUES')
    info('RQ1 PR size 99th percentile', round(rq1['pr_size'].quantile(0.99), 3))
    info('RQ1 review latency 99th percentile (hours)',
         round(rq1['first_review_latency_hours'].quantile(0.99), 3))
    info('Merge latency 99th percentile (hours)',
         round(merge['merge_latency_hours'].quantile(0.99), 3))
    info('Maximum PR size', rq1['pr_size'].max())
    info('Maximum first-review latency (hours)', rq1['first_review_latency_hours'].max())
    info('Maximum merge latency (hours)', merge['merge_latency_hours'].max())

    section('9. REPOSITORY COVERAGE')
    rq1_counts = rq1.groupby('repo').size()
    rq3_counts = rq3.groupby('repo').size()
    info('Repositories represented in RQ1', rq1['repo'].nunique())
    info('Repositories with >=50 RQ1 PRs', int((rq1_counts >= 50).sum()))
    info('Repositories represented in RQ3', rq3['repo'].nunique())
    info('Repositories with >=50 RQ3 PRs', int((rq3_counts >= 50).sum()))

    repo_share = df.groupby('repo').size().sort_values(ascending=False) / len(df)
    if len(repo_share):
        info('Largest repository share', f'{repo_share.iloc[0]*100:.2f}% ({repo_share.index[0]})')
    if len(repo_share) >= 2:
        info('Two largest repositories combined', f'{repo_share.iloc[:2].sum()*100:.2f}%')

    not_done = None
    section('10. DATABASE REPOSITORY STATUS')
    if DB_PATH.exists():
        con = sqlite3.connect(DB_PATH)
        statuses = pd.read_sql_query(
            'SELECT status, COUNT(*) AS n FROM repositories GROUP BY status ORDER BY status',
            con,
        )
        print(statuses.to_string(index=False))

        csv_repos = list(df['repo'].dropna().unique())
        if csv_repos:
            placeholders = ','.join('?' for _ in csv_repos)
            query = f'''
                SELECT name, status, stage, last_error
                FROM repositories
                WHERE name IN ({placeholders})
                  AND COALESCE(status, '') != 'done'
                ORDER BY name
            '''
            not_done = pd.read_sql_query(query, con, params=csv_repos)
        else:
            not_done = pd.DataFrame()

        check("Every repository in analysis_prs.csv is marked status='done'",
              len(not_done) == 0,
              f'Non-done repos present in CSV: {len(not_done):,}')
        if len(not_done) > 0:
            print('\nRepositories in CSV that are not done:')
            print(not_done.to_string(index=False))
        con.close()
    else:
        print('[WARN] study.sqlite3 not found. Repository completion status was not validated.')

    section('11. FINAL SANITY CHECK')
    core_checks = [
        duplicate_prs == 0,
        neg_eligible == 0,
        (rq1['first_review_latency_hours'] >= 0).all(),
        rq1['first_external_human_review_at'].notna().all(),
        (rq1['pr_size'] >= 0).all(),
        (merge['merge_latency_hours'] >= 0).all(),
        merge['merged_at'].notna().all(),
        exp_negative == 0,
    ]
    if not_done is not None:
        core_checks.append(len(not_done) == 0)

    if all(core_checks):
        print('PASS: No critical integrity problem was detected in the final analysis dataset.')
    else:
        print('FAIL: At least one critical integrity check failed. Review the sections above before freezing the dataset.')

    print('\nNOTE: This script checks dataset integrity and sample construction. It cannot independently prove that contributor_experience was computed without look-ahead; that must also be verified in build_dataset.py and documented in the methodology.')


if __name__ == '__main__':
    main()
