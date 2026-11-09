#!/usr/bin/env python3
"""Create auditable current-condition review records from municipal demolition leads.
Does not infer demolition completion, current vacancy, or permission to enter.
"""
import csv, datetime as dt, re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
MATCH=ROOT/'Illinois_Evidence_Match_Review.csv'
REVIEW=ROOT/'Illinois_Current_Condition_Review.csv'
EVIDENCE=ROOT/'Property_Evidence.csv'
STAMP=dt.date.today().isoformat()
REVIEW_FIELDS=['address','parcel_id','parcel_address','parcel_city','match_status','source_date','source_document','source_url','historical_finding','historical_evidence_score','current_building_status','current_vacancy_status','latest_condition_evidence_date','latest_condition_evidence_url','demolition_completion_evidence_url','parcel_identity_verified','review_status','review_notes','last_reviewed_utc']
EVIDENCE_FIELDS=['state','parcel_id','title','source_name','source_url','source_date','finding','notes','image_url','image_permission']
def read(p):
 if not p.exists():return []
 with p.open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def write(p,fields,rows):
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def main():
 if not MATCH.exists():raise SystemExit('Run create_illinois_evidence_queue.py first.')
 matches=read(MATCH)
 existing={(r.get('address',''),r.get('parcel_id','')):r for r in read(REVIEW)}
 out=[]
 for r in matches:
  key=(r.get('address',''),r.get('parcel_id',''))
  prior=existing.get(key,{})
  row={f:prior.get(f,'') for f in REVIEW_FIELDS}
  for f in ['address','parcel_id','parcel_address','parcel_city','match_status','source_date','source_document','source_url','historical_finding']:
   row[f]=r.get(f,'')
  row['historical_evidence_score']='30' if r.get('source_url') else '0'
  row['current_building_status']=prior.get('current_building_status') or 'unknown'
  row['current_vacancy_status']=prior.get('current_vacancy_status') or 'unverified'
  row['parcel_identity_verified']=prior.get('parcel_identity_verified') or 'no'
  row['review_status']=prior.get('review_status') or 'pending'
  row['review_notes']=prior.get('review_notes') or ('Ambiguous or missing parcel match; manual identity review required.' if r.get('match_status') in ('ambiguous','unmatched') else 'Check official demolition completion/permit records and dated imagery; historical listing alone is insufficient.')
  out.append(row)
 write(REVIEW,REVIEW_FIELDS,out)
 evidence=read(EVIDENCE)
 existing_keys={(x.get('state',''),x.get('parcel_id',''),x.get('source_url',''),x.get('title','')) for x in evidence}
 added=0
 for r in matches:
  pid=r.get('parcel_id','').strip();url=r.get('source_url','').strip()
  if not pid or not url:continue
  title='Historical municipal demolition solicitation: '+r.get('address','')
  key=('IL',pid,url,title)
  if key in existing_keys:continue
  evidence.append({'state':'IL','parcel_id':pid,'title':title,'source_name':r.get('source_document') or 'City of East St. Louis','source_url':url,'source_date':r.get('source_date',''),'finding':'Historical demolition/condemnation lead; current condition unverified','notes':'Address match requires verification. Solicitation is not proof demolition occurred or structure remains vacant.','image_url':'','image_permission':''})
  existing_keys.add(key);added+=1
 write(EVIDENCE,EVIDENCE_FIELDS,evidence)
 print(f'Current-condition review: {len(out)} rows; evidence added: {added}; current vacancies automatically verified: 0')
 print(f'Generated {REVIEW.name} and updated {EVIDENCE.name}')
if __name__=='__main__':main()
