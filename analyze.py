"""Validate a sourced financial panel, compute SQL metrics, and export research outputs."""
import argparse
import csv
from datetime import date
import json
from pathlib import Path
import sqlite3
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
AMOUNTS = ['revenue_usd_m', 'operating_income_usd_m', 'cfo_usd_m', 'capex_usd_m']
COLUMNS = ['ticker', 'fiscal_year', 'period_end', 'weeks'] + AMOUNTS + ['source_id']

def validate(rows, sources):
    seen = set()
    cleaned = []
    for number, original in enumerate(rows, 2):
        row = dict(original)
        if set(row) != set(COLUMNS):
            raise ValueError(f'Row {number}: unexpected schema')
        row['fiscal_year'] = int(row['fiscal_year'])
        for col in AMOUNTS:
            row[col] = int(row[col])
        row['weeks'] = int(row['weeks']) if row['weeks'] else None
        date.fromisoformat(row['period_end'])
        if row['weeks'] not in (None, 52, 53):
            raise ValueError('Weeks must be 52, 53, or blank')
        if row['revenue_usd_m'] <= 0 or row['capex_usd_m'] < 0:
            raise ValueError('Revenue must be positive; capex must use a positive outflow convention')
        if row['source_id'] not in sources:
            raise ValueError('Missing source attribution')
        if not row['ticker'].isalpha() or not row['ticker'].isupper():
            raise ValueError('Expected uppercase alphabetic ticker')
        key = row['ticker'], row['fiscal_year']
        if key in seen:
            raise ValueError(f'Duplicate company-year: {key}')
        seen.add(key)
        cleaned.append(row)
    if not cleaned:
        raise ValueError('No financial records')
    for ticker in {r['ticker'] for r in cleaned}:
        ends = [r['period_end'] for r in sorted(cleaned, key=lambda x: x['fiscal_year']) if r['ticker']==ticker]
        if ends != sorted(set(ends)):
            raise ValueError('Period ends must strictly increase within each company')
    return cleaned

def calculate(rows, connection):
    connection.execute('DROP TABLE IF EXISTS financials')
    connection.execute('''CREATE TABLE financials (
        ticker TEXT, fiscal_year INTEGER, period_end TEXT, weeks INTEGER,
        revenue_usd_m INTEGER, operating_income_usd_m INTEGER,
        cfo_usd_m INTEGER, capex_usd_m INTEGER, source_id TEXT,
        PRIMARY KEY(ticker, fiscal_year))''')
    connection.executemany('INSERT INTO financials VALUES (?,?,?,?,?,?,?,?,?)',
                           [tuple(r[k] for k in COLUMNS) for r in rows])
    connection.commit()
    connection.row_factory = sqlite3.Row
    return [dict(r) for r in connection.execute((ROOT/'sql/metrics.sql').read_text())]

def export(metrics, output):
    with (output/'metrics.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=metrics[0].keys())
        writer.writeheader()
        writer.writerows(metrics)
    latest = {}
    for row in metrics:
        latest[row['ticker']] = row
    rows = list(latest.values())
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.7))
    plt.rcParams['svg.hashsalt'] = 'retail-fundamentals'
    colors = ['#2563eb', '#0d9488', '#d97706']
    labels = [f"{r['ticker']}\nFY{r['fiscal_year']}" for r in rows]
    for ax, key, title in zip(axes, ['operating_margin_pct','cfo_margin_pct','fcf_margin_pct'],
                              ['Operating margin', 'Operating cash flow / revenue', 'Free cash flow / revenue']):
        values = [r[key] for r in rows]
        bars = ax.bar(labels, values, color=colors, width=.6)
        ax.bar_label(bars, labels=[f'{v:.2f}%' for v in values], padding=4)
        ax.set_title(title, fontsize=11)
        ax.set_ylabel('% of revenue')
        ax.set_ylim(0, max(values)*1.3)
        ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Retail fundamentals · latest fiscal year in the frozen dataset', fontsize=14)
    fig.text(.5, .02, 'Different fiscal year ends; historical 2025 filings. FCF = operating cash flow − cash capital expenditure.', ha='center', fontsize=9)
    fig.tight_layout(rect=[0,.05,1,.93])
    fig.savefig(output/'margins.svg', metadata={'Date': None})
    plt.close(fig)
    lines = ['# Calculated snapshot', '', 'Amounts are USD millions. Fiscal labels are company-specific; these are not aligned calendar-year comparisons.', '',
             '| Company | Fiscal year | Revenue growth | Operating margin | FCF | FCF change |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for r in rows:
        growth = 'N/A' if r['revenue_growth_pct'] is None else f"{r['revenue_growth_pct']:.2f}%"
        change = 'N/A' if r['fcf_change_usd_m'] is None else f"{r['fcf_change_usd_m']:+,}"
        lines.append(f"| {r['ticker']} | {r['fiscal_year']} | {growth} | {r['operating_margin_pct']:.2f}% | {r['fcf_usd_m']:,} | {change} |")
    lines += ['', '## Cash-flow bridge', '', 'Change in FCF = change in operating cash flow − change in capex. A higher FCF number can reflect lower investment, not stronger trading.', '']
    for r in rows:
        if r['fcf_change_usd_m'] is not None:
            lines.append(f"- **{r['ticker']}**: CFO change {r['cfo_change_usd_m']:+,}; capex change {r['capex_change_usd_m']:+,}; FCF change {r['fcf_change_usd_m']:+,}.")
    (output/'SNAPSHOT.md').write_text('\n'.join(lines)+'\n')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=ROOT/'data/financials.csv')
    parser.add_argument('--output', type=Path, default=ROOT/'reports')
    args = parser.parse_args()
    sources = json.loads((ROOT/'data/sources.json').read_text())
    with args.data.open(newline='') as f:
        rows = validate(list(csv.DictReader(f)), sources)
    args.output.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.output/'fundamentals.sqlite') as connection:
        metrics = calculate(rows, connection)
    export(metrics, args.output)
    audit = {'records': len(rows), 'companies': len({r['ticker'] for r in rows}),
             'currency': 'USD', 'amount_unit': 'millions', 'source_links_verified': '2026-10-06',
             'dataset': 'Frozen extract from annual reports published in 2025; not current data',
             'validation': 'schema, numeric values, duplicate keys, source attribution, period order, capex sign'}
    (args.output/'audit.json').write_text(json.dumps(audit, indent=2)+'\n')
    print(json.dumps(audit, indent=2))

if __name__ == '__main__':
    main()
