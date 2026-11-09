#!/usr/bin/env python3
"""Phase 3: gather dated, unverified web research leads; never certify vacancy."""
import csv, datetime as dt, json, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
P=Path(__file__).resolve().parent
IN=P/'Illinois_Current_Condition_Review.csv'
OUT=P/'Illinois_Online_Research_Leads.csv'
FIELDS=['address','parcel_id','source_title','source_url','source_date','query','research_status','review_notes','collected_utc']
def norm(s):return re.sub(r'[^a-z0-9]+',' ',str(s).lower()).strip()
def fetch(query):
 u='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':query,'hl':'en-US','gl':'US','ceid':'US:en'})
 req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0 (property research, public sources)'})
 with urllib.request.urlopen(req,timeout=18) as response:raw=response.read(1000000)
 root=ET.fromstring(raw)
 return [(x.findtext('title') or '',x.findtext('link') or '',x.findtext('pubDate') or '') for x in root.findall('.//item')]
def main():
 if not IN.exists():raise FileNotFoundError(IN.name)
 with IN.open(newline='',encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
 prior={}
 if OUT.exists():
  with OUT.open(newline='',encoding='utf-8-sig') as f:
   for r in csv.DictReader(f):prior[(r['address'],r['source_url'])]=r
 now=dt.datetime.now(dt.timezone.utc).isoformat()
 failures=[];found=0
 for row in rows:
  address=row.get('address','').strip();parcel=row.get('parcel_id','').strip()
  if not address:continue
  q=f'"{address}" "East St. Louis" (demolition OR condemned OR vacant OR rebuilt)'
  try:items=fetch(q)
  except Exception as e:failures.append({'address':address,'error':str(e)});continue
  for title,url,date in items:
   if not url:continue
   key=(address,url)
   if key in prior:continue
   # Search matches are leads, not address-verified evidence.
   prior[key]={'address':address,'parcel_id':parcel,'source_title':title,'source_url':url,'source_date':date,'query':q,'research_status':'unverified search result','review_notes':'Open source and confirm exact address, event, and date. Do not infer present vacancy or demolition completion.','collected_utc':now}
   found+=1
 with OUT.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(prior.values())
 (P/'Illinois_Research_Run_Report.json').write_text(json.dumps({'review_records':len(rows),'new_search_leads':found,'total_leads':len(prior),'errors':failures,'updated_at_utc':now,'note':'No current building status or vacancy is automatically verified.'},indent=2),encoding='utf-8')
 print(f'Phase 3: {len(rows)} review records; {found} new leads; {len(failures)} search errors; no automatic approvals')
if __name__=='__main__':main()
