#!/usr/bin/env python3
"""Match documented East St Louis condemnation leads to parcel queue; never auto-approve."""
import csv,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SRC=ROOT/'Illinois_Documented_Condemnation_Leads.csv'
PARCELS=ROOT/'Illinois_Parcel_Review_Queue.csv'
OUT=ROOT/'Illinois_Evidence_Match_Review.csv'
def norm(v):
 s=str(v or '').upper().replace('.',' ')
 s=re.sub(r'\b(STREET|ST)\b','ST',s);s=re.sub(r'\b(AVENUE|AVE|AV)\b','AVE',s)
 s=re.sub(r'\b(NORTH|N)\b','N',s);s=re.sub(r'\b(SOUTH|S)\b','S',s)
 return re.sub(r'[^A-Z0-9]','',s)
def rows(p):
 with p.open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def main():
 if not PARCELS.exists():sys.exit('Missing Illinois_Parcel_Review_Queue.csv; run importer first.')
 leads=rows(SRC); parcels=rows(PARCELS)
 idx={}
 for p in parcels:
  city=(p.get('sitecity') or '').upper()
  if city not in ('EAST SAINT LOUIS','EAST ST LOUIS','E ST LOUIS'):continue
  key=norm(p.get('siteadr1'))
  if key:idx.setdefault(key,[]).append(p)
 fields=['address','city','source_date','source_url','source_document','historical_finding','parcel_id','parcel_address','parcel_city','match_status','current_building_status','review_status','review_notes']
 with OUT.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for lead in leads:
   matches=idx.get(norm(lead['address']),[])
   for p in (matches or [{}]):
    w.writerow(dict(address=lead['address'],city='East St. Louis',source_date=lead['source_date'],source_url=lead['source_url'],source_document=lead['source_document'],historical_finding='Listed for demolition / condemned in source document',parcel_id=p.get('parcelid',''),parcel_address=p.get('siteadr1',''),parcel_city=p.get('sitecity',''),match_status=('unmatched' if not matches else 'ambiguous' if len(matches)>1 else 'address candidate - requires parcel review'),current_building_status='unknown - may have been demolished',review_status='pending',review_notes='Verify parcel identity, current structure existence and current vacancy; do not approve automatically'))
 print(f'{len(leads)} documented leads; {sum(bool(idx.get(norm(x["address"]))) for x in leads)} address-matched; output {OUT}')
if __name__=='__main__':main()
