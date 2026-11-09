#!/usr/bin/env python3
"""Unified MO/IL research updater. Indexed leads only; never infers vacancy or access."""
import csv, datetime as dt, html, json, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
BASE=Path(__file__).resolve().parent
NOW=dt.datetime.now(dt.timezone.utc).isoformat()
PLACES=['East St. Louis','Washington Park Illinois','Brooklyn Illinois','Cahokia Heights','Sauget Illinois','Fairmont City','Granite City Illinois','Madison Illinois','Venice Illinois','St. Louis Missouri']
SITES=['site:reddit.com/r/StLouis','site:reddit.com/r/urbanexploration','site:reddit.com/r/abandoned','site:undergroundozarks.com','site:builtstlouis.net']
QUERIES=[f'"{place}" (abandoned OR vacant OR demolition OR historic)' for place in PLACES]+[f'{site} "{place}" abandoned' for site in SITES for place in ['East St. Louis','St. Louis']]
def normalize(s):return re.sub(r'[^a-z0-9]+',' ',str(s).lower()).strip()
def rss(q):
 u='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':q,'hl':'en-US','gl':'US','ceid':'US:en'})
 req=urllib.request.Request(u,headers={'User-Agent':'STL-Urbex-Explorer/2.0 (public indexed research)'})
 with urllib.request.urlopen(req,timeout=25) as r: data=r.read(2_000_000)
 root=ET.fromstring(data)
 return [{'title':(i.findtext('title') or '').strip(),'url':(i.findtext('link') or '').strip(),'published':(i.findtext('pubDate') or '').strip(),'query':q,'source':'Indexed research lead'} for i in root.findall('.//item') if i.findtext('link')]
def csvrows(path):
 if not path.exists():return []
 with path.open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def main():
 mo=csvrows(BASE/'STL_Properties_v2.csv')
 if not mo:raise FileNotFoundError('STL_Properties_v2.csv missing or empty')
 il=csvrows(BASE/'Illinois_Parcel_Review_Queue.csv')
 curated=csvrows(BASE/'STL_Urbex_Research_Initial.csv')
 # Explicitly reviewed entries only. Do not treat GIS parcel records as abandoned buildings.
 reviewed=csvrows(BASE/'Illinois_Verified_Properties.csv')
 approved=[r for r in reviewed if r.get('review_status','').strip().lower()=='approved' and r.get('latitude','') and r.get('longitude','')]
 leads={};errors=[]
 for q in QUERIES:
  try:
   for item in rss(q):leads[item['url']]=item
  except Exception as e:errors.append({'query':q,'error':str(e)})
 # Candidate address matches are leads, not verified matches.
 address_index=[]
 for r in il:
  a=normalize(r.get('siteadr1',''))
  if len(a)>=12:address_index.append((a,r.get('parcelid',''),r.get('sitecity','')))
 for a in leads.values():
  title=normalize(a['title']);a['candidate_illinois_parcels']=[{'parcel_id':pid,'city':city,'match':'address in title, unverified'} for addr,pid,city in address_index if addr in title][:5]
  a['review_status']='Unverified research lead';a['legal_access']='Unknown / permission required'
 output={'updated_at_utc':NOW,'missouri_baseline_count':len(mo),'illinois_parcels_for_review':len(il),'illinois_approved_entries':len(approved),'research_leads':list(leads.values()),'existing_references':curated,'fetch_errors':errors,'notice':'GIS parcels do not establish vacancy. Search-indexed links do not establish physical access, current conditions, or legal permission.'}
 (BASE/'urbex_research_updates.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
 # Read immutable baseline, never index.html, so daily runs do not accumulate panels.
 template=BASE/'STL_Explorer_Map_v2.html'
 if not template.exists():raise FileNotFoundError('STL_Explorer_Map_v2.html missing')
 page=template.read_text(encoding='utf-8')
 if '</body>' not in page:raise ValueError('Map HTML lacks closing body')
 def card(a):
  title=html.escape(a.get('title') or a.get('location_reference') or 'Untitled');url=html.escape(a.get('url') or a.get('source_url') or '',quote=True)
  return f'<article class="research-card"><a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a><small>{html.escape(a.get("published") or a.get("mentioned_on") or "")} · Unverified source lead</small></article>'
 cards=''.join(card(x) for x in curated+list(leads.values()))
 panel='''<style>#research-btn{position:fixed;right:12px;bottom:16px;z-index:99999;background:#17314b;color:white;border:0;border-radius:10px;padding:12px}#research-panel{display:none;position:fixed;z-index:100000;inset:5%;overflow:auto;background:white;padding:18px;border-radius:12px;box-shadow:0 0 0 100vmax #0009;font:14px system-ui}.research-card{border-top:1px solid #ddd;padding:10px 0}.research-card a{display:block}.research-card small{color:#555}</style><button id="research-btn" onclick="document.getElementById('research-panel').style.display='block'">Urbex research MO + IL</button><section id="research-panel"><button onclick="document.getElementById('research-panel').style.display='none'">Close</button><h2>Missouri + Illinois research</h2><p>Illinois parcels awaiting verification: '''+str(len(il))+'''. Approved Illinois entries: '''+str(len(approved))+'''. Research leads do not prove vacancy or permission to enter.</p><input placeholder="Search research" aria-label="Filter research" oninput="document.querySelectorAll('.research-card').forEach(e=>e.style.display=e.textContent.toLowerCase().includes(this.value.toLowerCase())?'':'none')" style="width:90%;padding:9px"><div>'''+cards+'''</div></section>'''
 # Only add vetted Illinois records as map markers; same Leaflet styling as existing map.
 # Base map has its own data schema; integration requires inspection of live repository version.
 output_page=page.replace('</body>',panel+'</body>')
 (BASE/'index.html').write_text(output_page,encoding='utf-8')
 print(f'MO baseline {len(mo)}; IL parcel review {len(il)}; IL approved {len(approved)}; indexed leads {len(leads)}; errors {len(errors)}')
if __name__=='__main__':main()
