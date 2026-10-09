"""Accession-aware financial extraction and label-availability-aware annual prediction."""
from datetime import date
import hashlib
import json
from pathlib import Path
import math
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score, log_loss, average_precision_score

BASE=Path(__file__).resolve().parent
CFO='NetCashProvidedByUsedInOperatingActivities'
CONTROLS=['cfo_assets','log_assets']
FEATURES=CONTROLS+['accruals_assets']
SEED=20261009

def days(a,b): return (date.fromisoformat(b)-date.fromisoformat(a)).days

def exact_fact(facts,tag,accn,end,start=None):
    """Require same accession/period. Reject conflicting values, never silently take last."""
    candidates=[f for f in facts.get(tag,[]) if f.get('accn')==accn and f.get('end')==end
                and (f.get('start')==start if start is not None else 'start' not in f)]
    if not candidates: raise ValueError('missing '+tag)
    vals={float(f['val']) for f in candidates}
    if len(vals)!=1: raise ValueError('conflicting '+tag)
    v=vals.pop()
    if not math.isfinite(v):raise ValueError('nonfinite '+tag)
    return v

def extract_company(source,cutoff='2025-12-31'):
    facts=source['facts'];ticker=source['ticker']
    # Earliest timely original 10-K for this exact annual period. Do not replace an
    # incomplete original with a later filing containing revised comparative values.
    candidates={}
    for f in facts.get(CFO,[]):
        if f.get('form')!='10-K' or f.get('filed','9999')>cutoff or 'start' not in f:continue
        if f['start']<'2009-01-01' or not 350<=days(f['start'],f['end'])<=380:continue
        if not 0<days(f['end'],f['filed'])<=180:continue
        candidates.setdefault(f['end'],[]).append(f)
    rows=[];exclusions=[]
    for end,options in sorted(candidates.items()):
        first=min(options,key=lambda f:(f['filed'],f['accn']))
        accn,start,filed=first['accn'],first['start'],first['filed']
        try:
            # A single filing/date is the feature information set.
            vals={tag:exact_fact(facts,tag,accn,end,start if tag==CFO else None) for tag in [CFO,'Assets']}
            income_tag='ProfitLoss' if any(f.get('accn')==accn and f.get('start')==start and f.get('end')==end for f in facts.get('ProfitLoss',[])) else 'NetIncomeLoss'
            income=exact_fact(facts,income_tag,accn,end,start)
            if vals['Assets']<=0:raise ValueError('nonpositive assets')
            assets=vals['Assets']
            rows.append({'ticker':ticker,'cik':source['cik'],'company':source['entityName'],
                'start':start,'end':end,'filed':filed,'accn':accn,'period_days':days(start,end)+1,
                'cfo':vals[CFO],'net_income':income,'income_tag':income_tag,'assets':assets,
                'cfo_assets':vals[CFO]/assets,
                'log_assets':np.log(assets),'accruals_assets':(income-vals[CFO])/assets,
                'filing_url':f"https://www.sec.gov/Archives/edgar/data/{int(source['cik'])}/{accn.replace('-','')}/{accn}-index.html"})
        except ValueError as e:
            exclusions.append({'ticker':ticker,'end':end,'accn':accn,'reason':str(e)})
    return rows,exclusions

def make_panel(annual):
    rows=[]
    for ticker,g in annual.groupby('ticker'):
        records=g.sort_values('end').to_dict('records')
        for a,b in zip(records,records[1:]):
            # No gap jumping. Require next period to begin immediately after this one.
            if days(a['end'],b['start'])!=1 or not 350<=days(a['end'],b['end'])<=380:continue
            if b['filed']<=a['filed']:continue
            change=b['cfo_assets']-a['cfo_assets']
            rows.append({**a,'label_filed':b['filed'],'next_end':b['end'],'next_accn':b['accn'],
                         'next_cfo_assets':b['cfo_assets'],'next_cfo':b['cfo'],'next_income_tag':b['income_tag'],'change_cfo_assets':change,'target':int(change<-.02)})
    if not rows: raise ValueError('No consecutive annual pairs remain')
    return pd.DataFrame(rows).sort_values(['filed','ticker']).reset_index(drop=True)

def split_year(panel,year):
    cutoff=f'{year}-01-01'
    train=panel[(panel.filed<cutoff)&(panel.label_filed<cutoff)].copy()
    test=panel[(panel.filed>=cutoff)&(panel.filed<f'{year+1}-01-01')].copy()
    return train,test

def predict(panel,years):
    predictions=[];audit=[];coefficients=[]
    for year in years:
        train,test=split_year(panel,year)
        if len(train)<40 or train.target.nunique()<2 or test.empty:
            raise ValueError(f'Insufficient fold {year}: train={len(train)} test={len(test)}')
        models={
            'logit_controls':(CONTROLS,make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=2000,random_state=SEED))),
            'logit_accruals':(FEATURES,make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=2000,random_state=SEED))),
            'tree_accruals':(FEATURES,DecisionTreeClassifier(max_depth=2,min_samples_leaf=15,random_state=SEED))}
        probs={'prevalence':np.full(len(test),train.target.mean())}
        for name,(cols,model) in models.items():
            model.fit(train[cols],train.target)
            probs[name]=model.predict_proba(test[cols])[:,1]
            if name.startswith('logit'):
                coefficients.extend({'year':year,'model':name,'feature':c,'standardized_coefficient':float(v)}
                    for c,v in zip(cols,model[-1].coef_[0]))
        audit.append({'year':year,'n_train':len(train),'n_test':len(test),'train_event_rate':train.target.mean(),
            'test_event_rate':test.target.mean(),'max_train_label_filed':train.label_filed.max(),
            'test_first_filed':test.filed.min(),'model_asof':f'{year}-01-01'})
        for i,(_,r) in enumerate(test.iterrows()):
            predictions.append({**r.to_dict(),'test_year':year,**{k:float(v[i]) for k,v in probs.items()}})
    return pd.DataFrame(predictions),pd.DataFrame(audit),pd.DataFrame(coefficients)

def metrics(frame):
    rows=[]
    for name in ['prevalence','logit_controls','logit_accruals','tree_accruals']:
        y,p=frame.target,frame[name]
        rows.append({'model':name,'n':len(frame),'event_rate':y.mean(),'brier':brier_score_loss(y,p),
            'roc_auc':roc_auc_score(y,p) if y.nunique()>1 else np.nan,
            'log_loss':log_loss(y,p,labels=[0,1]),'average_precision':average_precision_score(y,p) if y.sum()>0 else np.nan})
    return pd.DataFrame(rows)

def bootstrap_difference(frame,group,n=2000):
    """Paired loss differences; sample whole companies or years, not iid rows."""
    diff=(frame.logit_accruals-frame.target)**2-(frame.logit_controls-frame.target)**2
    groups=[diff[frame[group]==g].to_numpy() for g in sorted(frame[group].unique())]
    rng=np.random.default_rng(SEED);values=[]
    for _ in range(n):
        sample=rng.integers(len(groups),size=len(groups))
        values.append(np.concatenate([groups[i] for i in sample]).mean())
    return {'group':group,'clusters':len(groups),'resamples':n,'seed':SEED,
        'brier_difference_accruals_minus_controls':float(diff.mean()),
        'ci95':np.quantile(values,[.025,.975]).tolist(),
        'scope':'Conditional on fitted predictions; no model refitting, no two-way clustering or model-selection adjustment'}

def load_snapshot(path):
    manifest=json.loads((path/'manifest.json').read_text())
    sources=[]
    for f in manifest['files']:
        b=(path/(f['ticker']+'.json')).read_bytes()
        if hashlib.sha256(b).hexdigest()!=f['extract_sha256']:raise ValueError('Snapshot hash mismatch: '+f['ticker'])
        sources.append(json.loads(b))
    return sources

def table(frame):
    # Keep report rendering independent of optional tabulate.
    lines=['| '+' | '.join(frame.columns)+' |','| '+' | '.join(['---']*len(frame.columns))+' |']
    for row in frame.itertuples(index=False,name=None):
        lines.append('| '+' | '.join(f'{v:.4f}' if isinstance(v,float) else str(v) for v in row)+' |')
    return '\n'.join(lines)

def main():
    design=json.loads((BASE/'design.json').read_text());out=BASE/'reports';out.mkdir(exist_ok=True)
    rows=[];excluded=[]
    for source in load_snapshot(BASE/'data/sec'):
        r,e=extract_company(source,design['source_cutoff']);rows.extend(r);excluded.extend(e)
    annual=pd.DataFrame(rows).sort_values(['ticker','end']);panel=make_panel(annual)
    annual.to_csv(out/'annual_facts.csv',index=False)
    panel.to_csv(out/'labeled_panel.csv',index=False)
    pd.DataFrame(excluded,columns=['ticker','end','accn','reason']).to_csv(out/'exclusions.csv',index=False)
    pred,audit,coef=predict(panel,design['test_filing_years'])
    pred.to_csv(out/'predictions.csv',index=False);audit.to_csv(out/'fold_audit.csv',index=False);coef.to_csv(out/'coefficients.csv',index=False)
    score=metrics(pred);score.to_csv(out/'metrics.csv',index=False)
    year_metrics=pd.concat([metrics(g).assign(year=y) for y,g in pred.groupby('test_year')],ignore_index=True)
    year_metrics.to_csv(out/'year_metrics.csv',index=False)
    # Post-primary diagnostic sensitivities. They do not replace the primary target.
    sensitivities=[]
    for label,alternative in [
        ('consolidated_income_only',panel[panel.income_tag=='ProfitLoss'].copy()),
        ('fixed_current_asset_denominator',panel.assign(target=(((panel.next_cfo-panel.cfo)/panel.assets)<-.02).astype(int)))]:
        alt_pred,_,_=predict(alternative,design['test_filing_years'])
        sensitivities.append(metrics(alt_pred).assign(sensitivity=label))
    pd.concat(sensitivities,ignore_index=True).to_csv(out/'sensitivity.csv',index=False)
    intervals=[bootstrap_difference(pred,g) for g in ['ticker','test_year']]
    (out/'uncertainty.json').write_text(json.dumps(intervals,indent=2)+'\n')
    # Calibration bins fixed before inspecting data, not optimized for appearance.
    calibration=[]
    for name in score.model:
        b=pd.cut(pred[name],bins=[0,.2,.4,.6,.8,1],include_lowest=True)
        for interval,g in pred.groupby(b,observed=True):
            calibration.append({'model':name,'bin':str(interval),'n':len(g),'mean_prediction':g[name].mean(),'event_rate':g.target.mean()})
    pd.DataFrame(calibration).to_csv(out/'calibration.csv',index=False)
    # Company case selection is descriptive, explicit and reproducible.
    last=pred[pred.test_year==pred.test_year.max()].copy()
    last['abs_error']=(last.logit_accruals-last.target).abs()
    cases=pd.concat([last.nsmallest(2,'abs_error').assign(case='smallest error'),last.nlargest(2,'abs_error').assign(case='largest error')])
    cases.to_csv(out/'case_studies.csv',index=False)
    scope={'companies':annual.ticker.nunique(),'annual_rows':len(annual),'labeled_rows':len(panel),'test_rows':len(pred),
        'test_events':int(pred.target.sum()),'excluded_annual_rows':len(excluded),'first_period':annual.start.min(),
        'last_period':annual.end.max(),'first_test_filed':pred.filed.min(),'last_test_filed':pred.filed.max(),
        'design_sha256':hashlib.sha256((BASE/'design.json').read_bytes()).hexdigest()}
    (out/'audit.json').write_text(json.dumps(scope,indent=2)+'\n')
    diff=intervals[0]['brier_difference_accruals_minus_controls']
    conclusion=('Adding accruals improved' if diff<0 else 'Adding accruals worsened')+f' the pooled Brier score by {abs(diff):.4f} relative to controls.'
    crosses=any(x['ci95'][0]<=0<=x['ci95'][1] for x in intervals)
    conclusion+=' At least one grouped bootstrap interval crosses zero; incremental value is not robustly established.' if crosses else 'Both conditional intervals exclude zero; this remains a small, selected observational sample, not a causal or trading result.'
    note=f'''# Earnings quality research results

Question: does the income-to-cash gap add information about a next-year decline greater than 2 percentage points in operating cash flow / end-of-year assets?

## Scope

{scope['companies']} selected consumer companies; {len(annual)} annual observations; {len(panel)} consecutive-period labeled observations; {len(pred)} out-of-time predictions in filing years 2018–2024, including {int(pred.target.sum())} deterioration events. Source facts filed by 2025-12-31. Excluded annual observations: {len(excluded)}.

## Pooled out-of-time results

{table(score)}

Brier and log loss: lower is better. ROC AUC and average precision: higher is better. The prevalence model uses only the relevant fold's training labels, not the final sample's event rate.

{conclusion}

## Paired uncertainty

Brier difference = accruals logistic minus controls logistic; negative favors adding accruals.

'''
    for x in intervals:note+=f"- Resampling {x['clusters']} {x['group']} clusters: 95% percentile interval [{x['ci95'][0]:.4f}, {x['ci95'][1]:.4f}].\n"
    note+='''
Intervals are conditional on the realized fitted predictions. Company resampling preserves each company's history but misses shared year shocks; year resampling preserves contemporaneous dependence but uses only seven year clusters and misses company dependence across years. Neither is a two-way-cluster confidence guarantee. Models are not refit inside resamples.

## Diagnostic sensitivities

sensitivity.csv reports two analyses added after the primary run: (1) retain only rows whose current income tag is consolidated ProfitLoss; (2) define deterioration as (next CFO - current CFO) / current assets < -0.02, holding the scaling denominator fixed. Models are refit with the same temporal rules and unchanged hyperparameters. These address income-definition and denominator concerns; they are exploratory checks, not extra independent confirmations.

A year with no positive outcomes has undefined average precision and ROC AUC, exported as missing rather than treated as evidence of good ranking. Tree probabilities of zero/one can incur very large log loss when wrong.

## Time integrity

Each annual row uses the earliest timely original 10-K's exact accession and period, with income/cash flow covering the same start/end dates and balance-sheet facts at that end date. A fold's training outcomes must have been disclosed before January 1 of its prediction year. Preprocessing is fit only to that training set. See fold_audit.csv and accession URLs in annual_facts.csv.

## What this does not prove

No stock returns or investment performance are measured. The cohort is selected from familiar surviving companies. Accounting-tag coverage, same-issuer dependence, overlapping next-year outcomes, acquisitions, asset revaluations, discontinued operations, and 52/53-week calendars limit interpretation. The target ratio can fall because assets grow; it is not pure operating deterioration or fraud detection. CFO can already differ from earnings for ordinary working-capital reasons. Current SEC API extraction is not a certified archived point-in-time database.

## Case review

case_studies.csv shows the two smallest and two largest absolute errors from the last test filing year. Selection deliberately includes successes and failures. These are descriptive examples, not independent validation. Read original filings before assigning an economic explanation to any error.
'''
    (out/'RESULTS.md').write_text(note)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4.4),layout='constrained')
    for name in score.model:
        d=year_metrics[year_metrics.model==name]
        axes[0].plot(d.year,d.brier,marker='o',label=name.replace('_',' '))
    axes[0].set(title='Out-of-time Brier score by filing year',xlabel='Prediction filing year',ylabel='Brier score (lower is better)')
    axes[0].legend(fontsize=8);axes[0].grid(alpha=.25)
    for name in ['logit_controls','logit_accruals']:
        d=pd.DataFrame(calibration);d=d[d.model==name]
        axes[1].plot(d.mean_prediction,d.event_rate,marker='o',label=name.replace('_',' '))
    axes[1].plot([0,1],[0,1],linestyle='--',color='gray');axes[1].set(xlim=(0,1),ylim=(0,1),xlabel='Mean predicted probability',ylabel='Observed event frequency',title='Pooled calibration (fixed probability bins)')
    axes[1].legend(fontsize=8);axes[1].grid(alpha=.25)
    fig.savefig(out/'diagnostics.svg');plt.close(fig)
    print(json.dumps(scope));print(score.to_string(index=False));print(conclusion)
if __name__=='__main__':main()
