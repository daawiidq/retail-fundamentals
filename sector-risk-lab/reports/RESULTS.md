# Research results

Frozen input: 312 months × 10 industry portfolios. Evaluation: 2005-01 through 2025-12 (252 months).

Net results assume 10 bps per dollar traded, monthly rebalancing, and a 60-month trailing window.

| Strategy | CAGR | Annual volatility | Max drawdown | VaR breach rate |
| --- | ---: | ---: | ---: | ---: |
| Shops only | 12.07% | 15.55% | -38.02% | 5.95% |
| Equal weight | 10.61% | 15.11% | -48.09% | 5.56% |
| Inverse volatility | 10.25% | 14.16% | -46.40% | 5.56% |

Paired 12-month block-bootstrap 95% percentile interval for the inverse-volatility minus equal-weight CAGR difference: **-1.16% to 0.36%**.

## Interpretation

Compare volatility and drawdown as well as return. Inverse-volatility weights do not use correlations and therefore are not equal-risk-contribution weights. A lower-volatility strategy can still sustain a large equity drawdown.

The VaR check compares each month’s gross loss with a historical loss quantile estimated only from the previous 60 months under that month’s weights. A 95% model has a nominal 5% breach rate, but a sample rate alone is not a calibration proof.

The bootstrap resamples both strategies together and retains local dependence in 12-month blocks. It does not refit weights, correct for choosing the strategies after seeing history, or demonstrate future outperformance.

See stress_windows.csv for explicitly named historical windows, window_sensitivity.csv for 36/60-month comparisons over the same evaluation dates, and risk_contributions.csv for end-sample covariance-based risk attribution.

## Main finding

Inverse-volatility weighting reduced annualized volatility from 15.11% to 14.16%, but CAGR was also lower (10.25% versus 10.61%). Its maximum drawdown remained -46.40%.

The bootstrap interval crosses zero in this sample: it does not support a clear return advantage. The concentrated Shops benchmark happened to outperform both diversified allocations on CAGR and maximum drawdown in this selected period. Diversification is not a guarantee of a better realized outcome than every individual component.
