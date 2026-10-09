"""Fetch a compact, accession-preserving SEC Company Facts snapshot.
One request at a time with >=0.25 seconds between requests; raw responses cached locally.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.request

TAGS = ['ProfitLoss', 'NetIncomeLoss', 'NetCashProvidedByUsedInOperatingActivities', 'Assets']
BASE = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--user-agent', required=True, help='Identify your research application and contact email')
    p.add_argument('--cache', type=Path, default=BASE / '.cache')
    p.add_argument('--output', type=Path, default=BASE / 'data_refresh')
    a = p.parse_args()
    if a.output.exists():
        raise SystemExit('Use a new output directory; snapshots are never overwritten.')
    a.output.mkdir(parents=True)
    a.cache.mkdir(parents=True, exist_ok=True)
    universe = list(csv.DictReader((BASE/'data/universe.csv').open()))
    provenance=[]
    for row in universe:
        ticker,cik=row['ticker'],int(row['cik'])
        url=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json'
        cache=a.cache/f'{ticker}.json'
        if cache.exists():
            raw=cache.read_bytes()
            origin_time=datetime.fromtimestamp(cache.stat().st_mtime,timezone.utc).isoformat()
        else:
            time.sleep(.25)
            request=urllib.request.Request(url,headers={'User-Agent':a.user_agent,'Accept':'application/json'})
            with urllib.request.urlopen(request,timeout=60) as response: raw=response.read()
            cache.write_bytes(raw)
            origin_time=datetime.now(timezone.utc).isoformat()
        source=json.loads(raw)
        if int(source['cik'])!=cik: raise ValueError('CIK mismatch')
        facts=source['facts']['us-gaap']
        compact={'cik':cik,'ticker':ticker,'entityName':source['entityName'],'facts':{
            tag:[f for f in facts.get(tag,{}).get('units',{}).get('USD',[])
                 if f.get('form')=='10-K' and f.get('filed','9999')<='2025-12-31'
                 and f.get('end','')>='2009-01-01'] for tag in TAGS}}
        target=a.output/f'{ticker}.json'
        target.write_text(json.dumps(compact,separators=(',',':'))+'\n')
        provenance.append({'ticker':ticker,'cik':cik,'url':url,'retrieved_utc':origin_time,
             'raw_sha256':hashlib.sha256(raw).hexdigest(),'extract_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
             'extraction':'USD, four standard US-GAAP tags, original 10-K form, filed <= 2025-12-31, period end >= 2009-01-01'})
        print(ticker,source['entityName'],sum(map(len,compact['facts'].values())),flush=True)
    (a.output/'manifest.json').write_text(json.dumps({'source':'SEC Company Facts','files':provenance},indent=2)+'\n')
if __name__=='__main__': main()
