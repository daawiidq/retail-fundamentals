-- Explicit REAL arithmetic avoids SQLite integer division.
WITH history AS (
    SELECT *,
        LAG(fiscal_year) OVER w AS previous_year,
        LAG(revenue_usd_m) OVER w AS previous_revenue,
        LAG(cfo_usd_m) OVER w AS previous_cfo,
        LAG(capex_usd_m) OVER w AS previous_capex
    FROM financials
    WINDOW w AS (PARTITION BY ticker ORDER BY fiscal_year)
)
SELECT ticker, fiscal_year, period_end, weeks, source_id,
    revenue_usd_m, operating_income_usd_m, cfo_usd_m, capex_usd_m,
    CASE WHEN previous_year = fiscal_year - 1
        THEN 100.0 * (revenue_usd_m - previous_revenue) / NULLIF(previous_revenue, 0)
        END AS revenue_growth_pct,
    100.0 * operating_income_usd_m / NULLIF(revenue_usd_m, 0) AS operating_margin_pct,
    100.0 * cfo_usd_m / NULLIF(revenue_usd_m, 0) AS cfo_margin_pct,
    100.0 * capex_usd_m / NULLIF(revenue_usd_m, 0) AS capex_intensity_pct,
    cfo_usd_m - capex_usd_m AS fcf_usd_m,
    100.0 * (cfo_usd_m - capex_usd_m) / NULLIF(revenue_usd_m, 0) AS fcf_margin_pct,
    CASE WHEN previous_year = fiscal_year - 1 THEN cfo_usd_m - previous_cfo END AS cfo_change_usd_m,
    CASE WHEN previous_year = fiscal_year - 1 THEN capex_usd_m - previous_capex END AS capex_change_usd_m,
    CASE WHEN previous_year = fiscal_year - 1
        THEN (cfo_usd_m - capex_usd_m) - (previous_cfo - previous_capex)
        END AS fcf_change_usd_m
FROM history
ORDER BY ticker, fiscal_year;
