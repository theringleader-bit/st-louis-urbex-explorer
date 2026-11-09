#!/usr/bin/env python3
"""Fetch public St Clair County parcel records into a REVIEW queue (not vacancy claims).
Run in GitHub Actions or Colab. Does not modify Missouri map or index.html.
"""
import csv, json, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
BASE=Path(__file__).resolve().parent
ENDPOINT='https://arcgispublicmap.co.st-clair.il.us/server/rest/services/SCC_parcel_map_data/MapServer/29/query'
TOWNS=[
    'EAST ST LOUIS',
    'E ST LOUIS',
    'EAST SAINT LOUIS',
    'WASHINGTON PARK',
    'BROOKLYN',
    'FAIRMONT CITY',
    'CAHOKIA',
    'CENTREVILLE',
    'ALORTON',
    'SAUGET',
    'BELLEVILLE'
]
FIELDS=['objectid','parcelid','parcel_number','siteadr1','siteadr2','sitecity','sitest','sitezip','landuse','class','bldgval','status']
def query(params):
    url=ENDPOINT+'?'+urllib.parse.urlencode(dict(params,f='json'))
    req=urllib.request.Request(url,headers={'User-Agent':'STL-Explorer-Research/1.0 (public parcel metadata)'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=75) as response: data=json.load(response)
            if 'error' in data: raise RuntimeError(str(data['error']))
            return data
        except Exception:
            if attempt==2: raise
            time.sleep(2**attempt)
def main():
    rows=[]; errors=[]; counts={}
    for town in TOWNS:
        offset=0; townrows=0
        while True:
            params={'where':"UPPER(sitecity) = '"+town.replace("'","''")+"'",'outFields':','.join(FIELDS),'returnGeometry':'true','outSR':'4326','resultOffset':offset,'resultRecordCount':500,'orderByFields':'objectid ASC'}
            try: result=query(params)
            except Exception as e:
                errors.append({'town':town,'offset':offset,'error':str(e)})
                break
            features=result.get('features',[])
            for feature in features:
                a=feature.get('attributes') or {}
                geom=feature.get('geometry') or {}
                rings=geom.get('rings') or []
                pts=[point for ring in rings for point in ring]
                lon=sum(p[0] for p in pts)/len(pts) if pts else ''
                lat=sum(p[1] for p in pts)/len(pts) if pts else ''
                row={k:a.get(k,'') for k in FIELDS}
                row.update({'latitude_approx':lat,'longitude_approx':lon,'coordinate_method':'approx polygon vertex average (not precise centroid)','state':'IL','county':'St. Clair','source':'St. Clair County GIS Parcels','source_url':ENDPOINT,'vacancy_status':'UNVERIFIED','map_ready':'NO — requires independent vacancy evidence'})
                rows.append(row)
            townrows+=len(features); offset+=len(features)
            if not features or (len(features)<500 and not result.get('exceededTransferLimit')): break
            time.sleep(0.25)
        counts[town]=townrows
        print(town,townrows,flush=True)
    # Only add parcel records to a review file; do not imply vacant or abandoned.
    unique={str(r['parcelid'] or r['parcel_number'] or r['objectid']):r for r in rows}
    path=BASE/'Illinois_Parcel_Review_Queue.csv'
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS+['latitude_approx','longitude_approx','coordinate_method','state','county','source','source_url','vacancy_status','map_ready'])
        writer.writeheader();writer.writerows(unique.values())
    report={'run_utc':datetime.now(timezone.utc).isoformat(),'town_counts':counts,'unique_parcels':len(unique),'errors':errors,'note':'Parcel records only. No Illinois vacancy records verified or added to map.'}
    (BASE/'Illinois_Import_Report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
if __name__=='__main__': main()
