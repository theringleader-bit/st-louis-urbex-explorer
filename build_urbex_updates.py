#!/usr/bin/env python3
"""Daily, source-linked St Louis urbex research updater.
Uses Google News RSS (public article links). Reddit API intentionally not scraped.
Produces a self-contained HTML map using the existing baseline and a JSON review queue.
"""
import csv, datetime as dt, html, json, os, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
BASE=Path(__file__).resolve().parent
TODAY=dt.datetime.now(dt.timezone.utc).isoformat()
QUERY=[
 '"St. Louis" "abandoned" "school"',
 '"St. Louis" "abandoned" "church"',
 '"St. Louis" "vacant" "hospital"',
 '"St. Louis" "abandoned" "factory"',
 '"St. Louis County" "vacant building"',
 'site:undergroundozarks.com "St. Louis"',
 'site:builtstlouis.net abandoned',
 'site:builtstlouis.net "St. Louis" school',
 'site:reddit.com/r/StLouis abandoned',
 'site:reddit.com/r/urbanexploration "St. Louis"',
 'site:reddit.com/r/abandoned "St. Louis"',
]

def norm(s):return re.sub(r'[^a-z0-9]+',' ',str(s).lower()).strip()
def get_news(query):
 url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':query,'hl':'en-US','gl':'US','ceid':'US:en'})
 req=urllib.request.Request(url,headers={'User-Agent':'STLPropertyResearch/1.0 (personal noncommercial research)'})
 with urllib.request.urlopen(req,timeout=25) as r: data=r.read(2_000_000)
 root=ET.fromstring(data)
 result=[]
 for item in root.findall('.//item'):
  title=(item.findtext('title') or '').strip(); link=(item.findtext('link') or '').strip()
  date=(item.findtext('pubDate') or '').strip()
  if title and link:
   source=('Underground Ozarks (indexed lead)' if 'site:undergroundozarks.com' in query else 'Built St. Louis (indexed lead)' if 'site:builtstlouis.net' in query else 'Reddit (indexed lead; no API scraping)' if 'site:reddit.com' in query else 'Google News RSS')
   result.append({'title':title,'url':link,'published':date,'source':source,'query':query})
 return result

def main():
 with (BASE/'STL_Properties_v2.csv').open(newline='',encoding='utf-8-sig') as f: properties=list(csv.DictReader(f))
 with (BASE/'STL_Urbex_Research_Initial.csv').open(newline='',encoding='utf-8-sig') as f: curated=list(csv.DictReader(f))
 existing=[]
 for row in curated:
  existing.append({'title':row.get('location_reference',''), 'url':row.get('source_url',''), 'published':row.get('mentioned_on',''), 'source':row.get('source',''), 'summary':row.get('summary',''), 'category':row.get('category',''), 'access_status':row.get('access_status','Unknown'), 'parcel_match':row.get('parcel_match','Unverified'), 'review_status':'Previously curated; parcel not verified'})
 articles=[]; errors=[]
 for q in QUERY:
  try: articles.extend(get_news(q))
  except Exception as e: errors.append({'query':q,'error':str(e)})
 unique={a['url']:a for a in articles}; articles=list(unique.values())
 # Only exact address strings are proposed as candidates. Never auto-assert a match.
 address_index=[]
 for p in properties:
  a=norm(p.get('a',''))
  if len(a)>=12: address_index.append((a,p.get('id',''),p.get('a','')))
 review=[]
 for a in articles:
  title=norm(a['title']); matches=[]
  for addr,pid,raw in address_index:
   if addr in title: matches.append({'parcel_id':pid,'address':raw,'method':'exact normalized address in headline — review required'})
  a['candidate_matches']=matches[:10]; a['review_status']='Needs human review'; a['access_status']='Not established'
  review.append(a)
 research={'updated_at_utc':TODAY,'base_property_count':len(properties),'news_candidates':len(review),'verified_new_parcel_matches':0,'existing_references':existing,'news_review_queue':review,'fetch_errors':errors,'notice':'Search-engine-indexed leads only; no direct Reddit or site scraping. Coverage is incomplete. Leads are not evidence of legal access, current vacancy, or parcel identity.'}
 (BASE/'urbex_research_updates.json').write_text(json.dumps(research,indent=2,ensure_ascii=False),encoding='utf-8')
 # Add research panel to existing standalone map without changing existing map data.
 map_path=BASE/'STL_Explorer_Map_v2.html'
 if not map_path.exists():raise FileNotFoundError(map_path)
 map_html=map_path.read_text(encoding='utf-8')
 if '</body>' not in map_html:raise ValueError('Expected closing body tag in map')
 rows=existing+review
 def row_html(a):
  title=html.escape(a.get('title','')); link=html.escape(a.get('url',''),quote=True)
  date=html.escape(a.get('published','')); source=html.escape(a.get('source',''))
  summary=html.escape(a.get('summary',''))
  status=html.escape(a.get('review_status',''))
  return f'<article class="urbex-item"><div><a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a></div><small>{source} · {date} · {status}</small><p>{summary}</p></article>'
 panel='''<style>#urbex-open{position:fixed;right:14px;bottom:18px;z-index:100000;background:#172e49;color:white;border:1px solid #7ca1c0;border-radius:14px;padding:13px;font:600 14px system-ui;box-shadow:0 2px 12px #0006}#urbex-panel{display:none;position:fixed;z-index:100001;inset:5% 3%;overflow:auto;background:#fff;color:#142238;padding:18px;border-radius:16px;box-shadow:0 0 0 200vw #0008;font:14px system-ui}#urbex-panel h2{margin:4px 0}#urbex-panel button{float:right;padding:7px 12px}#urbex-panel input{padding:10px;width:95%;max-width:480px;margin:10px 0}.urbex-item{border-top:1px solid #ddd;padding:12px 0}.urbex-item a{color:#135c9c;font-weight:600}.urbex-item small{color:#576477}.urbex-item p{margin:5px 0}</style><button id="urbex-open" onclick="document.getElementById('urbex-panel').style.display='block'">Urbex research</button><section id="urbex-panel" role="dialog" aria-label="Urbex research"><button onclick="document.getElementById('urbex-panel').style.display='none'">Close ✕</button><h2>Community &amp; Urbex Research</h2><p>Updated: '''+html.escape(TODAY[:16])+''' UTC. Articles are research leads, <strong>not verified parcel matches or evidence of legal access</strong>. Reddit references are indexed search leads, not direct Reddit scraping; coverage may be incomplete.</p><input id="urbex-filter" placeholder="Filter by location, article or source" oninput="document.querySelectorAll('.urbex-item').forEach(x=>x.style.display=x.textContent.toLowerCase().includes(this.value.toLowerCase())?'':'none')"><div id="urbex-items">'''+''.join(row_html(a) for a in rows)+'''</div></section>'''
 out=map_html.replace('</body>',panel+'</body>')
 (BASE/'STL_Explorer_Auto_Research.html').write_text(out,encoding='utf-8')
 # GitHub Pages serves index.html; update it as part of the scheduled run.
 (BASE/'index.html').write_text(out,encoding='utf-8')
 print(f'Properties in baseline map CSV: {len(properties)}; existing references: {len(existing)}; news leads: {len(review)}; errors: {len(errors)}')
if __name__=='__main__':main()
