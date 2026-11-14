#!/usr/bin/env python3
"""Import documented St. Louis vacancy indicators from a public ArcGIS table.

Only exact parcel-ID matches to the local Missouri baseline are mapped. Never
interpret absent values as proof of vacancy, foreclosure, or utility shutoff.
"""
import csv
import datetime as dt
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TABLE = os.environ.get('STL_VACANCY_ARCGIS_TABLE', 'https://services.arcgis.com/uHAHKfH1Z5ye1Oe0/ArcGIS/rest/services/Candidate_Lots_for_Small_Urban_Gardens_in_St__Louis_WFL1/FeatureServer/16')
OUT = ROOT / 'STL_Property_Distress_Indicators.csv'
FIELDS = ['address','parcel_id','latitude','longitude','indicator_type','record_date','source_name','source_url','notes']

def get(url, params):
    target = url + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(target, headers={'User-Agent':'STL-Property-Research/1.0'})
    with urllib.request.urlopen(req, timeout=90) as resp:
        result = json.load(resp)
    if 'error' in result:
        raise RuntimeError(str(result['error']))
    return result

def key(s):
    return re.sub('[^a-z0-9]','',str(s or '').lower())

def lookup(a, *names):
    idx = {key(k):v for k,v in a.items()}
    for name in names:
        v=idx.get(key(name))
        if v is not None and str(v).strip() not in ('','None','null'):
            return str(v).strip()
    return ''

def yes(v):
    return str(v).strip().lower() in ('1','true','yes','y','t')

def main():
    with (ROOT/'STL_Properties_v2.csv').open(encoding='utf-8-sig',newline='') as f:
        baseline = {key(r['id']):r for r in csv.DictReader(f) if r.get('id')}
    meta = get(TABLE, {'f':'json'})
    oid = meta.get('objectIdField') or next((f['name'] for f in meta.get('fields',[]) if f.get('type')=='esriFieldTypeOID'), None)
    if not oid:
        raise RuntimeError('Source table has no object ID field; not overwriting output')
    count = get(TABLE+'/query', {'where':'1=1','returnCountOnly':'true','f':'json'}).get('count',0)
    if not count:
        raise RuntimeError('Source returned no records; not overwriting output')
    results = []
    found=set()
    for offset in range(0,count,1000):
        response=get(TABLE+'/query',{'where':'1=1','outFields':'*','returnGeometry':'false','orderByFields':oid,'resultOffset':offset,'resultRecordCount':1000,'f':'json'})
        features=response.get('features',[])
        if not features:
            raise RuntimeError(f'Source pagination failed at {offset}; not overwriting output')
        for feature in features:
            a=feature.get('attributes') or {}
            pid=lookup(a,'ParcelId','parcel_id','parcelid','handle')
            b=baseline.get(key(pid))
            if not b: continue  # Avoid inaccurate coordinate/address joins.
            address=b.get('a','')
            # Interpret only explicit affirmative flags; never interpret a score as confirmation.
            flags=[
                ('official vacant-building indicator',('VacantBuilding','VacantBldg','VBR','VacantBuildingRegistry','VacantStructure')),
                ('condemnation indicator',('Condemned','Condemnation','IsCondemned')),
                ('tax delinquency indicator',('TaxDelinquent','TaxDelinq','DelinquentTax','TaxDelinquency')),
                ('commercial classification',('Commercial','IsCommercial')),
                ('dissolved business indicator',('DissolvedBusiness','BusinessDissolved')),
            ]
            for label,aliases in flags:
                value=lookup(a,*aliases)
                if not yes(value): continue
                row=(pid,label)
                if row in found:continue
                found.add(row)
                results.append(dict(address=address,parcel_id=pid,latitude=b['lat'],longitude=b['lng'],indicator_type=label,record_date='',source_name='STL Vacancy Collaborative (ArcGIS hosted snapshot)',source_url=TABLE,notes='Public dataset indicator; current status and legal access not independently verified.'))
    # Keep manually entered rows, but replace prior rows from this same importer.
    manual=[]
    if OUT.exists():
        with OUT.open(encoding='utf-8-sig',newline='') as f:
            manual=[{k:r.get(k,'') for k in FIELDS} for r in csv.DictReader(f) if r.get('source_name')!='STL Vacancy Collaborative (ArcGIS hosted snapshot)']
    with OUT.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerows(manual+results)
    print(f'Source rows: {count}; exact parcel matches with explicit flags: {len(results)}; preserved manual rows: {len(manual)}')
    print('Available source columns:', ', '.join(f['name'] for f in meta.get('fields',[])))
    if not results:
        print('No explicit matching indicator fields found. Inspect source columns and extend the flag mapping; no vacancy claims made.')

if __name__=='__main__': main()
