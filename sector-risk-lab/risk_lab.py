"""Walk-forward industry allocation with explicit timing and trading-cost conventions."""
from pathlib import Path
import argparse, hashlib, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
STRATEGIES=['Shops only','Equal weight','Inverse volatility']

def validate(data):
    if data.empty or data.shape[1]<2: raise ValueError('Need a nonempty multi-industry panel')
    if data.index.has_duplicates or not data.index.is_monotonic_increasing: raise ValueError('Duplicate or unordered months')
    index=pd.PeriodIndex(data.index,freq='M')
    if not index.equals(pd.period_range(index[0],index[-1],freq='M')): raise ValueError('Missing month')
    if not np.isfinite(data.to_numpy()).all() or (data<=-1).any().any(): raise ValueError('Invalid monthly return')
    if 'Shops' not in data: raise ValueError('Missing Shops benchmark')
    return data

def target_weights(history, strategy):
    n=history.shape[1]
    if strategy=='Shops only': return (history.columns=='Shops').astype(float)
    if strategy=='Equal weight': return np.ones(n)/n
    if strategy!='Inverse volatility': raise ValueError('Unknown strategy')
    vol=history.std(ddof=1).to_numpy()
    if not np.isfinite(vol).all() or (vol<=0).any(): raise ValueError('Cannot weight a zero-volatility series')
    inverse=1/vol
    return inverse/inverse.sum()

def backtest(data, strategy, lookback=60, cost_bps=10, start_month=None):
    validate(data)
    if lookback<12 or lookback>=len(data): raise ValueError('Insufficient history')
    if not np.isfinite(cost_bps) or not 0<=cost_bps<=100: raise ValueError('Cost must be 0–100 bps')
    previous=np.zeros(data.shape[1]); rows=[]; allocations=[]
    start=lookback if start_month is None else max(lookback, data.index.get_loc(start_month))
    for t in range(start,len(data)):
        # Exclusive upper slice: realized month t never enters its own signal.
        history=data.iloc[t-lookback:t]
        w=target_weights(history,strategy)
        current=data.iloc[t].to_numpy()
        gross=float(w@current)
        traded=float(np.abs(w-previous).sum())
        fee=traded*cost_bps/10000
        net=(1-fee)*(1+gross)-1
        historical_losses=-(history.to_numpy()@w)
        var=float(np.quantile(historical_losses,.95,method='higher'))
        rows.append({'month':data.index[t],'gross_return':gross,'net_return':net,
                     'traded_fraction':traded,'cost_fraction':fee,'forecast_var95':var,
                     'var_breach':int(-gross>var)})
        allocations.append(w)
        previous=w*(1+current)/(1+gross)
    return pd.DataFrame(rows).set_index('month'),pd.DataFrame(allocations,index=data.index[start:],columns=data.columns)

def drawdown(returns):
    wealth=np.cumprod(1+np.asarray(returns))
    peak=np.maximum.accumulate(np.r_[1.,wealth])[1:]
    return wealth/peak-1

def metrics(result):
    r=result.net_return.to_numpy(); losses=-r
    var=float(np.quantile(losses,.95,method='higher'))
    return {'cagr':float(np.prod(1+r)**(12/len(r))-1),'annual_vol':float(np.std(r,ddof=1)*np.sqrt(12)),
            'max_drawdown':float(drawdown(r).min()),'worst_month':float(r.min()),
            'historical_var95':var,'historical_es95':float(losses[losses>=var].mean()),
            'annual_traded_fraction':float(result.traded_fraction.mean()*12),
            'forecast_var_breach_rate':float(result.var_breach.mean())}

def paired_bootstrap(a,b,block=12,samples=1000,seed=20261007):
    """Circular block bootstrap of the realized paired monthly net return paths."""
    a=np.asarray(a);b=np.asarray(b)
    if len(a)!=len(b) or len(a)<block: raise ValueError('Incompatible bootstrap inputs')
    rng=np.random.default_rng(seed); n=len(a); deltas=[]
    for _ in range(samples):
        starts=rng.integers(0,n,size=int(np.ceil(n/block)))
        idx=((starts[:,None]+np.arange(block))%n).ravel()[:n]
        deltas.append(np.prod(1+a[idx])**(12/n)-np.prod(1+b[idx])**(12/n))
    return np.quantile(deltas,[.025,.975]).tolist()

def run(output):
    path=ROOT/'data/monthly_returns.csv'; manifest=json.loads((ROOT/'data/source.json').read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['extract_sha256']:raise ValueError('Data snapshot hash mismatch')
    data=validate(pd.read_csv(path,index_col='month'))
    output.mkdir(parents=True,exist_ok=True); all_rows=[]; base={}; weights={}; sensitivity=[]
    for cost in [0,10,25]:
        for strategy in STRATEGIES:
            result,w=backtest(data,strategy,cost_bps=cost)
            all_rows.append({'strategy':strategy,'cost_bps':cost,**metrics(result)})
            if cost==10:
                base[strategy]=result;weights[strategy]=w
                result.to_csv(output/(strategy.lower().replace(' ','_')+'_monthly.csv'))
                w.to_csv(output/(strategy.lower().replace(' ','_')+'_weights.csv'))
    summary=pd.DataFrame(all_rows);summary.to_csv(output/'summary.csv',index=False)
    # Same test months in every window comparison; earlier returns only initialize weights.
    for lookback in [36,60]:
        for strategy in STRATEGIES:
            result,_=backtest(data,strategy,lookback=lookback,start_month="2005-01")
            sensitivity.append({'lookback_months':lookback,'strategy':strategy,**metrics(result)})
    pd.DataFrame(sensitivity).to_csv(output/'window_sensitivity.csv',index=False)
    stress=[]
    for name,(start,end) in {'2008 crisis':('2008-01','2009-03'),'COVID onset':('2020-02','2020-03'),'2022':('2022-01','2022-12')}.items():
        for strategy,r in base.items():
            stress.append({'window':name,'strategy':strategy,'start':start,'end':end,
                           'cumulative_return':float((1+r.loc[start:end,'net_return']).prod()-1)})
    pd.DataFrame(stress).to_csv(output/'stress_windows.csv',index=False)
    attribution=[]
    cov=data.iloc[-61:-1].cov().to_numpy()
    for strategy,w in weights.items():
        last=w.iloc[-1].to_numpy();fraction=last*(cov@last)/float(last@cov@last)
        for industry,weight,risk in zip(data.columns,last,fraction):
            attribution.append({'strategy':strategy,'month':data.index[-1],'industry':industry,'weight':weight,'variance_contribution':risk})
    pd.DataFrame(attribution).to_csv(output/'risk_contributions.csv',index=False)
    ci=paired_bootstrap(base['Inverse volatility'].net_return,base['Equal weight'].net_return)
    (output/'bootstrap.json').write_text(json.dumps({'comparison':'Inverse volatility minus equal-weight CAGR',
       'cost_bps':10,'block_months':12,'samples':1000,'seed':20261007,'percentile_95_interval':ci,
       'note':'Conditional descriptive interval for realized paths, not a forecast or strategy-selection-adjusted inference.'},indent=2)+'\n')
    fig,axes=plt.subplots(2,1,figsize=(11,7),sharex=True)
    for strategy,r in base.items():
        dates=pd.to_datetime(r.index)
        axes[0].plot(dates,(1+r.net_return).cumprod(),label=strategy)
        axes[1].plot(dates,drawdown(r.net_return)*100,label=strategy)
    axes[0].set(ylabel='Growth of $1 (net)',title='Industry allocation: 2005–2025 · 10 bps per dollar traded')
    axes[1].set(ylabel='Drawdown (%)',xlabel='Month');axes[0].legend(frameon=False)
    for ax in axes:ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
    fig.tight_layout();fig.savefig(output/'risk_dashboard.png',dpi=160);plt.close(fig)
    rows=summary[summary.cost_bps==10]
    lines=['# Research results','',f'Frozen input: {len(data)} months × {data.shape[1]} industry portfolios. Evaluation: 2005-01 through 2025-12 (252 months).',
      '', 'Net results assume 10 bps per dollar traded, monthly rebalancing, and a 60-month trailing window.', '',
      '| Strategy | CAGR | Annual volatility | Max drawdown | VaR breach rate |', '| --- | ---: | ---: | ---: | ---: |']
    for r in rows.itertuples():lines.append(f'| {r.strategy} | {r.cagr:.2%} | {r.annual_vol:.2%} | {r.max_drawdown:.2%} | {r.forecast_var_breach_rate:.2%} |')
    lines+=['',f'Paired 12-month block-bootstrap 95% percentile interval for the inverse-volatility minus equal-weight CAGR difference: **{ci[0]:.2%} to {ci[1]:.2%}**.',
      '', '## Interpretation','',
      'Compare volatility and drawdown as well as return. Inverse-volatility weights do not use correlations and therefore are not equal-risk-contribution weights. A lower-volatility strategy can still sustain a large equity drawdown.',
      '', 'The VaR check compares each month’s gross loss with a historical loss quantile estimated only from the previous 60 months under that month’s weights. A 95% model has a nominal 5% breach rate, but a sample rate alone is not a calibration proof.',
      '', 'The bootstrap resamples both strategies together and retains local dependence in 12-month blocks. It does not refit weights, correct for choosing the strategies after seeing history, or demonstrate future outperformance.',
      '', 'See stress_windows.csv for explicitly named historical windows, window_sensitivity.csv for 36/60-month comparisons over the same evaluation dates, and risk_contributions.csv for end-sample covariance-based risk attribution.']
    indexed=rows.set_index('strategy')
    inverse=indexed.loc['Inverse volatility']; equal=indexed.loc['Equal weight']
    lines += ['', '## Main finding', '',
      f"Inverse-volatility weighting reduced annualized volatility from {equal.annual_vol:.2%} to {inverse.annual_vol:.2%}, but CAGR was also lower ({inverse.cagr:.2%} versus {equal.cagr:.2%}). Its maximum drawdown remained {inverse.max_drawdown:.2%}.",
      '', 'The bootstrap interval crosses zero in this sample: it does not support a clear return advantage. The concentrated Shops benchmark happened to outperform both diversified allocations on CAGR and maximum drawdown in this selected period. Diversification is not a guarantee of a better realized outcome than every individual component.']
    (output/'RESULTS.md').write_text('\n'.join(lines)+'\n')
    print(rows.to_string(index=False));print('Bootstrap interval:',ci)
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'reports')
    run(parser.parse_args().output)
