"""Create a frozen monthly-return extract from the official French data library."""
from pathlib import Path
import argparse, csv, hashlib, io, json, re, urllib.request, zipfile
from datetime import datetime, timezone
SOURCE='https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/10_Industry_Portfolios_CSV.zip'
ROOT=Path(__file__).resolve().parent

def extract(payload, output):
    archive=zipfile.ZipFile(io.BytesIO(payload))
    names=[n for n in archive.namelist() if n.lower().endswith('.csv')]
    if len(names)!=1: raise ValueError('Unexpected source archive')
    text=archive.read(names[0]).decode('utf-8-sig')
    section=text.split('Average Value Weighted Returns -- Monthly',1)[1].splitlines()
    rows=[]; columns=None
    for line in section:
        if not line.strip():
            if rows: break
            continue
        fields=[s.strip() for s in next(csv.reader([line]))]
        if columns is None:
            columns=['month']+fields[1:]; continue
        if not re.fullmatch(r'\d{6}',fields[0]): break
        if '200001' <= fields[0] <= '202512':
            values=[float(v) for v in fields[1:]]
            if any(v in (-99.99,-999) for v in values): raise ValueError('Missing source data')
            rows.append([fields[0][:4]+'-'+fields[0][4:]]+[f'{v/100:.6f}' for v in values])
    if len(rows)!=312 or len(columns)!=11: raise ValueError('Unexpected panel dimensions')
    output.mkdir(parents=True,exist_ok=True)
    target=output/'monthly_returns.csv'
    if target.exists(): raise FileExistsError('Preserve the snapshot: choose a new --output directory')
    with target.open('w',newline='') as f:
        writer=csv.writer(f,lineterminator='\n'); writer.writerow(columns); writer.writerows(rows)
    manifest={'source_url':SOURCE,'source_name':'Kenneth R. French Data Library — 10 Industry Portfolios',
      'source_header':text.splitlines()[0], 'downloaded_utc':datetime.now(timezone.utc).isoformat(),
      'archive_sha256':hashlib.sha256(payload).hexdigest(),'extract_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
      'table':'Average Value Weighted Returns -- Monthly','unit':'decimal monthly total returns',
      'start':'2000-01','end':'2025-12','rows':len(rows),'industries':columns[1:],
      'details_url':'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library/det_10_ind_port.html',
      'revision_note':'This is a current-vintage historical extract, not an as-of historical database.'}
    (output/'source.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'data')
    args=parser.parse_args()
    with urllib.request.urlopen(SOURCE,timeout=45) as response: payload=response.read()
    print(json.dumps(extract(payload,args.output),indent=2))
