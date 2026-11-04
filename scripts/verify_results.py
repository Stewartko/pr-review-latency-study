"""Audit the supplied study without modifying it; write paper-specific results."""
from pathlib import Path
import argparse, json, sqlite3, warnings
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import statsmodels.formula.api as smf

p=argparse.ArgumentParser()
p.add_argument('project', type=Path)
a=p.parse_args()
src=a.project.resolve()
out=Path(__file__).resolve().parent
r=out/'verified_results'; r.mkdir(exist_ok=True)
df=pd.read_csv(src/'data/analysis_prs.csv')
con=sqlite3.connect((src/'study.sqlite3').as_uri()+'?mode=ro&immutable=1',uri=True)
statuses=pd.read_sql_query('SELECT status,COUNT(*) AS n FROM repositories GROUP BY status',con)
repos=pd.read_sql_query('SELECT * FROM repositories',con)
checks={}
checks['csv_rows']=len(df); checks['csv_repositories']=df.repo.nunique()
checks['csv_non_done_repositories']=int((repos.set_index('name').loc[df.repo.unique(),'status']!='done').sum())
checks['duplicates']=int(df.duplicated(['repo','pr_number']).sum())
checks['negative_review_rows']=int((df.first_review_latency_hours<0).sum())
checks['negative_review_eligible']=int(((df.first_review_latency_hours<0)&(df.eligible_rq1_basic==1)).sum())
checks['csv_database_key_match']=set(zip(df.repo,df.pr_number))==set(con.execute("SELECT p.repo,p.number FROM pull_requests p JOIN repositories r ON r.name=p.repo WHERE p.is_analysis_period=1 AND r.status='done'"))
checks['size_mismatches']=int((df.pr_size!=(df.additions+df.deletions)).sum())
checks['created_min']=df.created_at.min(); checks['created_max']=df.created_at.max()
checks['selected_min']=repos.selected_at.min(); checks['selected_max']=repos.selected_at.max()
checks['completed_updated_min']=repos.loc[repos.status=='done','updated_at'].min()
checks['completed_updated_max']=repos.loc[repos.status=='done','updated_at'].max()
checks['push_2026_or_later_done']=int(((repos.status=='done')&(repos.pushed_at>='2026-01-01')).sum())
q1=df[(df.eligible_rq1_basic==1)&(df.author_is_bot==0)].copy()
strict=df[(df.eligible_rq1_strict_no_draft_history==1)&(df.author_is_bot==0)]
q2=q1.dropna(subset=['pr_size','contributor_experience','first_review_latency_hours','repo']).copy()
q3=q1[q1.eligible_merge_latency==1]
merged=df[(df.eligible_merge_latency==1)&(df.author_is_bot==0)]
checks.update(human_prs=int((df.author_is_bot==0).sum()), bot_prs=int(df.author_is_bot.sum()),rq1=len(q1),strict=len(strict),rq2=len(q2),rq3=len(q3),merge=len(merged),rq2_repos=q2.repo.nunique(),rq3_repos=q3.repo.nunique(),missing_experience_rq1=int(q1.contributor_experience.isna().sum()),missing_author_rq1=int(q1.author_login.isna().sum()),missing_reviewer_rq1=int(q1.first_external_human_reviewer.isna().sum()))
# Replay the exact experience lookup against the database (including pre-window history).
import bisect
from collections import defaultdict
hist=defaultdict(list)
for repo,author,t in con.execute("SELECT p.repo,p.author_login,p.merged_at FROM pull_requests p JOIN repositories r ON r.name=p.repo WHERE p.merged=1 AND p.merged_at IS NOT NULL AND p.author_login IS NOT NULL AND r.status='done' ORDER BY p.repo,p.author_login,p.merged_at"):
    hist[repo,author].append(t)
checks['experience_mismatches']=sum(bisect.bisect_left(hist[row.repo,row.author_login],row.created_at)!=row.contributor_experience for row in df[['repo','author_login','created_at','contributor_experience']].itertuples(index=False) if pd.notna(row.author_login))
checks['review_rows_done']=con.execute("SELECT COUNT(*) FROM reviews v JOIN repositories r ON r.name=v.repo WHERE r.status='done'").fetchone()[0]
checks['pre2020_history_done']=con.execute("SELECT COUNT(*) FROM pull_requests p JOIN repositories r ON r.name=p.repo WHERE r.status='done' AND p.created_at<'2020-01-01'").fetchone()[0]
con.close()
def corr(d,y='first_review_latency_hours'):
    v=spearmanr(d.pr_size,d[y]); return {'n':len(d),'rho':float(v.statistic),'p_value':float(v.pvalue)}
cut_size=q1.pr_size.quantile(.99); cut_latency=q1.first_review_latency_hours.quantile(.99)
checks['size_cutoff']=cut_size; checks['review_cutoff_hours']=cut_latency
variants={'main':q1,'strict_no_draft_history':strict,'remove_top_1pct_pr_size':q1[q1.pr_size<=cut_size],'remove_top_1pct_review_latency':q1[q1.first_review_latency_hours<=cut_latency],'remove_top_1pct_both':q1[(q1.pr_size<=cut_size)&(q1.first_review_latency_hours<=cut_latency)]}
v1=pd.DataFrame([{'analysis':k,**corr(v)} for k,v in variants.items()]); v1.to_csv(r/'rq1_sensitivity.csv',index=False)
rp1=pd.DataFrame([{'repo':repo,**corr(g)} for repo,g in q1.groupby('repo') if len(g)>=50]); rp1.to_csv(r/'rq1_per_repository.csv',index=False)
checks.update(rq1_positive=int((rp1.rho>0).sum()),rq1_negative=int((rp1.rho<0).sum()),rq1_repository_median=rp1.rho.median(),rq1_repository_n=len(rp1))
v3=pd.DataFrame([{'outcome':y,**corr(q3,y)} for y in ['first_review_latency_hours','merge_latency_hours']]); v3.to_csv(r/'rq3_global.csv',index=False)
rp3=pd.DataFrame([{'repo':repo,'n':len(g),'review_rho':corr(g)['rho'],'merge_rho':corr(g,'merge_latency_hours')['rho']} for repo,g in q3.groupby('repo') if len(g)>=50])
rp3['difference']=rp3.merge_rho-rp3.review_rho; rp3.to_csv(r/'rq3_per_repository.csv',index=False)
checks.update(rq3_repository_n=len(rp3),rq3_merge_stronger=int((rp3.difference>0).sum()),rq3_review_stronger=int((rp3.difference<0).sum()),rq3_medians=rp3[['review_rho','merge_rho','difference']].median().to_dict())
desc=[]
for name,d,col in [('PR size (RQ1)',q1,'pr_size'),('First-review hours (RQ1)',q1,'first_review_latency_hours'),('Merge hours (merge eligible)',merged,'merge_latency_hours'),('Experience (RQ2)',q2,'contributor_experience')]:
    s=d[col]; desc.append({'variable':name,'n':len(s),'q1':s.quantile(.25),'median':s.median(),'q3':s.quantile(.75),'min':s.min(),'max':s.max()})
pd.DataFrame(desc).to_csv(r/'descriptive_statistics.csv',index=False)
for col in ['pr_size','contributor_experience']:
    q2['log_'+col]=np.log1p(q2[col]); q2['c_log_'+col]=q2['log_'+col]-q2['log_'+col].mean()
q2['log_review_latency']=np.log1p(q2.first_review_latency_hours)
print('Fitting final repository-clustered model...',flush=True)
model=smf.ols('log_review_latency ~ c_log_pr_size * c_log_contributor_experience + C(repo)',data=q2).fit(cov_type='cluster',cov_kwds={'groups':q2.repo})
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always')
    (r/'rq2_model_summary.txt').write_text(str(model.summary()),encoding='utf-8')
checks['model_warnings']=[str(w.message) for w in caught]
checks.update(rsquared=model.rsquared,adjusted_rsquared=model.rsquared_adj,condition_number=model.condition_number,centering_log_size=q2.log_pr_size.mean(),centering_log_experience=q2.log_contributor_experience.mean())
ci=model.conf_int()
terms=['c_log_pr_size','c_log_contributor_experience','c_log_pr_size:c_log_contributor_experience']
pd.DataFrame([{'term':t,'beta':model.params[t],'cluster_se':model.bse[t],'p_value':model.pvalues[t],'ci_low':ci.loc[t,0],'ci_high':ci.loc[t,1]} for t in terms]).to_csv(r/'rq2_coefficients.csv',index=False)
shares=df.repo.value_counts()/len(df); checks['largest_repo']=shares.index[0]; checks['largest_share']=shares.iloc[0]; checks['top2_share']=shares.iloc[:2].sum()
checks['rq2_experience_quantiles']=q2.contributor_experience.quantile([.25,.5,.75]).to_dict()
# Compare recalculated final CSVs against archived result files.
for name,recalc in [('rq1_sensitivity.csv',v1),('rq1_per_repository.csv',rp1),('rq3_per_repository.csv',rp3)]:
    old=pd.read_csv(src/'results'/name)
    checks['matches_'+name]=len(old)==len(recalc) and all(np.allclose(old[c],recalc[c],equal_nan=True) for c in old.select_dtypes('number').columns)
(r/'audit.json').write_text(json.dumps(checks,indent=2,default=lambda v:v.item() if hasattr(v,'item') else str(v)),encoding='utf-8')
print(json.dumps(checks,indent=2,default=str),flush=True)
print(pd.read_csv(r/'rq2_coefficients.csv').to_string(index=False),flush=True)
print(pd.DataFrame(desc).to_string(index=False),flush=True)
