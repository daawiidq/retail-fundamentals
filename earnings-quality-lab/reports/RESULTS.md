# Earnings quality research results

Question: does the income-to-cash gap add information about a next-year decline greater than 2 percentage points in operating cash flow / end-of-year assets?

## Scope

20 selected consumer companies; 267 annual observations; 237 consecutive-period labeled observations; 130 out-of-time predictions in filing years 2018–2024, including 42 deterioration events. Source facts filed by 2025-12-31. Excluded annual observations: 8.

## Pooled out-of-time results

| model | n | event_rate | brier | roc_auc | log_loss | average_precision |
| --- | --- | --- | --- | --- | --- | --- |
| prevalence | 130 | 0.3231 | 0.2311 | 0.4953 | 0.6625 | 0.3339 |
| logit_controls | 130 | 0.3231 | 0.2050 | 0.7262 | 0.5948 | 0.5683 |
| logit_accruals | 130 | 0.3231 | 0.1977 | 0.7511 | 0.5776 | 0.6020 |
| tree_accruals | 130 | 0.3231 | 0.2186 | 0.6115 | 2.1909 | 0.5072 |

Brier and log loss: lower is better. ROC AUC and average precision: higher is better. The prevalence model uses only the relevant fold's training labels, not the final sample's event rate.

Adding accruals improved the pooled Brier score by 0.0073 relative to controls. At least one grouped bootstrap interval crosses zero; incremental value is not robustly established.

## Paired uncertainty

Brier difference = accruals logistic minus controls logistic; negative favors adding accruals.

- Resampling 20 ticker clusters: 95% percentile interval [-0.0260, 0.0100].
- Resampling 7 test_year clusters: 95% percentile interval [-0.0294, 0.0117].

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
