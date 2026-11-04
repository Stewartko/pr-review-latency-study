"""Offline reproduction of the frozen ESS study; all generated files go to runs/."""
from pathlib import Path
import argparse,datetime,hashlib,importlib.metadata,json,os,platform,re,shutil,subprocess,sys,time,traceback

ROOT=Path(__file__).resolve().parent
ABS_TOL=1e-10
REL_TOL=1e-10

def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def integrity():
    manifest=json.loads((ROOT/'MANIFEST.json').read_text(encoding='utf-8'))
    issues=[]
    for row in manifest['files']:
        path=ROOT/row['path']
        if not path.is_file(): issues.append(row['path']+': missing')
        elif path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256']:
            issues.append(row['path']+': different content (or an LFS pointer instead of data)')
    return manifest,issues

def csv_comparison(actual,expected,dataset=False):
    import numpy as np
    import pandas as pd
    a=pd.read_csv(actual); b=pd.read_csv(expected)
    if list(a.columns)!=list(b.columns) or a.shape!=b.shape:
        return False,f'shape/columns differ: actual {a.shape}, reference {b.shape}'
    keys=['repo','pr_number'] if dataset else [x for x in ['repo','metric','variable','analysis','outcome','term'] if x in b]
    if keys:
        a=a.sort_values(keys).reset_index(drop=True); b=b.sort_values(keys).reset_index(drop=True)
    failures=[]
    for col in b:
        x,y=a[col],b[col]
        if pd.api.types.is_numeric_dtype(y) and pd.api.types.is_numeric_dtype(x):
            if pd.api.types.is_integer_dtype(y): ok=np.array_equal(x.to_numpy(),y.to_numpy())
            elif col=='p_value':
                ok=np.all(np.isclose(x.to_numpy(),y.to_numpy(),rtol=1e-6,atol=0,equal_nan=True))
            else: ok=np.allclose(x,y,rtol=REL_TOL,atol=ABS_TOL,equal_nan=True)
        else:
            ok=x.fillna('<MISSING>').astype(str).equals(y.fillna('<MISSING>').astype(str))
        if not ok: failures.append(col)
    return not failures,f'{len(b):,} rows, {len(b.columns)} columns; '+('match' if not failures else 'different: '+', '.join(failures))

def original_references():
    # These three tables are byte-identical for original analyses and article.
    shared=['rq1_per_repository.csv','rq1_sensitivity.csv','rq3_per_repository.csv']
    return sorted(list((ROOT/'reference/original').glob('*.csv'))+
                  [ROOT/'reference/article'/name for name in shared])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only',action='store_true',help='Standard-library-only SHA-256 integrity check, no analyses.')
    args=parser.parse_args()
    print('Checking frozen package files...',flush=True)
    manifest,issues=integrity()
    if issues:
        print('\n'.join(issues)); print('INTEGRITY FAIL. Restore original files or run git lfs pull.'); return 1
    print(f'Integrity PASS: {len(manifest["files"])} files.',flush=True)
    if args.verify_only: return 0
    required=['numpy','pandas','scipy','statsmodels']
    try: versions={x:importlib.metadata.version(x) for x in required}
    except importlib.metadata.PackageNotFoundError:
        print('Missing dependencies. Install requirements.txt in a Python 3.13 environment.'); return 1
    run=ROOT/'runs'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    run.mkdir(parents=True); (run/'logs').mkdir()
    project=run/'project'; project.mkdir(); (project/'data').mkdir(); (project/'results').mkdir()
    canonical=run/'canonical'; canonical.mkdir()
    checks=[]; start=time.monotonic(); error=None
    def check(name,passed,details):
        checks.append({'check':name,'passed':bool(passed),'details':details})
        print(('PASS' if passed else 'FAIL')+' | '+name+' | '+details,flush=True)
        if not passed: raise RuntimeError(name+': '+details)
    def execute(name,script,cwd,arguments=()):
        print('Running '+name+' ...',flush=True)
        env=os.environ.copy(); env.pop('GITHUB_TOKEN',None); env.pop('GH_TOKEN',None)
        env['STUDY_DB']=str(project/'study.sqlite3'); env['PYTHONUTF8']='1'; env['MPLBACKEND']='Agg'
        log=run/'logs'/f'{name}.log'
        with log.open('w',encoding='utf-8') as f:
            result=subprocess.run([sys.executable,str(script),*map(str,arguments)],cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT)
        check(name+'_exit',result.returncode==0,f'exit {result.returncode}; logs/{log.name}')
        return log.read_text(encoding='utf-8')
    try:
        print('Creating isolated working copies (about 0.7 GB)...',flush=True)
        shutil.copy2(ROOT/'data/raw/study.sqlite3',project/'study.sqlite3')
        for f in (ROOT/'scripts/original').glob('*.py'): shutil.copy2(f,project/f.name)
        for f in original_references():
            if not f.name.startswith('rq3_paired'): shutil.copy2(f,project/'results'/f.name)

        execute('01_build_dataset',project/'build_dataset.py',project)
        ok,detail=csv_comparison(project/'data/analysis_prs.csv',ROOT/'data/analysis_prs.csv',dataset=True)
        check('rebuilt_dataset_matches_frozen_csv',ok,detail)
        validation=execute('02_validate_data',project/'validate_data.py',project)
        check('critical_integrity','PASS: No critical integrity problem' in validation,'Original validator critical summary; 491 missing-experience diagnostic rows are expected.')
        execute('03_final_analysis',project/'final_analysis.py',project)
        rq2_log=execute('04_rq2_clustered_regression',project/'rq2_regression.py',project)
        check('original_rq2_uses_clustered_covariance',bool(re.search(r'Covariance Type:\s+cluster',rq2_log)),'Repository-clustered original model summary.')
        execute('05_rq3_comparison',project/'rq3_compare.py',project)
        for expected in original_references():
            if expected.name.startswith('rq3_paired'): continue
            ok,detail=csv_comparison(project/'results'/expected.name,expected)
            check('original_results_'+expected.name,ok,detail)

        # Recompute article statistics away from immutable references.
        shutil.copy2(ROOT/'scripts/verify_results.py',canonical/'verify_results.py')
        execute('06_paper_analysis',canonical/'verify_results.py',ROOT,[project])
        generated=canonical/'verified_results'
        for name in ['descriptive_statistics.csv','rq1_sensitivity.csv','rq1_per_repository.csv','rq2_coefficients.csv','rq3_global.csv','rq3_per_repository.csv']:
            ok,detail=csv_comparison(generated/name,ROOT/'reference/article'/name)
            check('paper_results_'+name,ok,detail)
        actual=json.loads((generated/'audit.json').read_text())
        reference=json.loads((ROOT/'reference/article/audit.json').read_text())
        for key in ['csv_rows','csv_repositories','human_prs','bot_prs','rq1','strict','rq2','rq3','merge','rq2_repos','rq3_repos','duplicates','negative_review_rows','negative_review_eligible','missing_experience_rq1','missing_author_rq1','missing_reviewer_rq1','csv_non_done_repositories','experience_mismatches','csv_database_key_match','size_mismatches','rq1_positive','rq1_negative','rq1_repository_n','rq3_repository_n','rq3_merge_stronger','rq3_review_stronger']:
            check('sample_or_integrity_'+key,actual[key]==reference[key],f'actual={actual[key]}, reference={reference[key]}')
        import math
        for key in ['rsquared','adjusted_rsquared','centering_log_size','centering_log_experience','rq1_repository_median']:
            check(key,math.isclose(actual[key],reference[key],rel_tol=REL_TOL,abs_tol=ABS_TOL),f'actual={actual[key]:.12g}, reference={reference[key]:.12g}')
        paired_dir=run/'paired'
        execute('07_rq3_paired_test',ROOT/'scripts/rq3_paired_test.py',ROOT,
                ['--input',project/'data/analysis_prs.csv','--expected',ROOT/'reference/article/rq3_per_repository.csv','--output-dir',paired_dir])
        paired=json.loads((paired_dir/'rq3_paired_test.json').read_text())
        pref=json.loads((ROOT/'reference/rq3_paired_test.json').read_text())
        for key in ['common_sample_prs','n_repositories','positive_differences','negative_differences','zero_differences','statistic','alternative','method','continuity_correction']:
            check('paired_'+key,paired[key]==pref[key],f'actual={paired[key]}, reference={pref[key]}')
        check('paired_median_difference',math.isclose(paired['median_difference'],pref['median_difference'],rel_tol=REL_TOL,abs_tol=ABS_TOL),str(paired['median_difference']))
        check('paired_p_value',math.isclose(paired['p_value'],pref['p_value'],rel_tol=1e-6,abs_tol=0),f'actual={paired["p_value"]:.15g}, reference={pref["p_value"]:.15g}')
        check('original_rq2_printed_key_coefficients',all(x in rq2_log for x in ['coef= 0.248065','coef= -0.181114','coef= 0.001792','Rows used: 269791']), 'Original script agrees with canonical full-precision coefficient comparison.')
        _,after=integrity()
        check('frozen_package_unchanged_after_run',not after,'Frozen inputs, reference outputs and source files remain unchanged.')
    except Exception as exc:
        error=str(exc); (run/'logs/error.log').write_text(traceback.format_exc(),encoding='utf-8')
        print('REPRODUCTION FAILED: '+error,flush=True)
    report={'success':error is None and all(c['passed'] for c in checks),'check_count':len(checks),'checks':checks,'error':error,'elapsed_seconds':round(time.monotonic()-start,2),'python':sys.version,'platform':platform.platform(),'dependencies':versions,'numeric_tolerance':{'absolute':ABS_TOL,'relative':REL_TOL,'p_value_relative':1e-6,'p_value_absolute':0},'frozen_input_hashes':{x['path']:x['sha256'] for x in manifest['files'] if x['path'] in ['data/analysis_prs.csv','data/raw/study.sqlite3']},'run_directory':run.name,'collector_executed':False,'reference_outputs_modified':False}
    (run/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    lines=['# Reproduction report','','Status: **'+('PASS' if report['success'] else 'FAIL')+'**',f'Checks: {len(checks)}; elapsed: {report["elapsed_seconds"]} seconds.','',f'Python: {sys.version.split()[0]}',f'Platform: {platform.platform()}','','No collection or network request was performed by the analysis runner. All generated files are in this run directory.','','| Check | Result | Details |','|---|---|---|']
    lines += [f'| {c["check"]} | {"PASS" if c["passed"] else "FAIL"} | {c["details"].replace("|","/")} |' for c in checks]
    if error: lines+=['','Error: '+error]
    (run/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (ROOT/'runs/LATEST.txt').write_text(run.name+'\n')
    print('\n'+('ALL CHECKS PASS' if report['success'] else 'CHECKS FAILED')+' | '+str(run/'REPORT.md'),flush=True)
    return 0 if report['success'] else 1

if __name__=='__main__':
    raise SystemExit(main())
