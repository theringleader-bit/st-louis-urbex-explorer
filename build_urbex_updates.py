#!/usr/bin/env python3
"""Unified Missouri/Illinois map and indexed research updater.

Approved Illinois entries and uniquely matched historical leads are mapped separately.
The immutable Missouri HTML template is never modified.
"""
import csv
import datetime as dt
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parent
NOW = dt.datetime.now(dt.timezone.utc).isoformat()
PLACES = ['East St. Louis', 'Washington Park Illinois', 'Brooklyn Illinois',
          'Cahokia Heights', 'Sauget Illinois', 'Fairmont City',
          'Granite City Illinois', 'Madison Illinois', 'Venice Illinois',
          'St. Louis Missouri']
SITES = ['site:reddit.com/r/StLouis', 'site:reddit.com/r/urbanexploration',
         'site:reddit.com/r/abandoned', 'site:undergroundozarks.com',
         'site:builtstlouis.net']
QUERIES = ([f'"{place}" (abandoned OR vacant OR demolition OR historic)' for place in PLACES]
           + [f'{site} "{place}" abandoned' for site in SITES
              for place in ['East St. Louis', 'St. Louis']])


def csvrows(path):
    if not path.exists():
        return []
    with path.open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def normalize(s):
    return re.sub(r'[^a-z0-9]+', ' ', str(s).lower()).strip()


def rss(query):
    url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode(
        {'q': query, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})
    req = urllib.request.Request(url, headers={'User-Agent': 'STL-Urbex-Explorer/2.1'})
    with urllib.request.urlopen(req, timeout=25) as response:
        root = ET.fromstring(response.read(2_000_000))
    return [{'title': (i.findtext('title') or '').strip(),
             'url': (i.findtext('link') or '').strip(),
             'published': (i.findtext('pubDate') or '').strip(),
             'query': query, 'source': 'Indexed research lead'}
            for i in root.findall('.//item') if i.findtext('link')]


def approved_illinois(rows):
    """Require explicit review, supporting URL, valid Illinois coordinates."""
    approved = []
    seen = set()
    for r in rows:
        if r.get('review_status', '').strip().lower() != 'approved':
            continue
        evidence = r.get('vacancy_evidence_url', '').strip()
        parsed = urllib.parse.urlparse(evidence)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            continue
        if r.get('state', 'IL').strip().upper() not in ('IL', 'ILLINOIS'):
            continue
        try:
            lat, lon = float(r['latitude']), float(r['longitude'])
        except (KeyError, ValueError, TypeError):
            continue
        if not (37.0 <= lat <= 40.0 and -91.5 <= lon <= -88.0):
            continue
        parcel = r.get('parcel_id', '').strip()
        address = r.get('address', '').strip()
        city = r.get('city', '').strip()
        if not address or not city or not parcel:
            continue
        key = parcel.upper()
        if key in seen:
            continue
        seen.add(key)
        approved.append({'id': 'IL-' + parcel, 'a': address,
                         'n': city + ', IL', 't': r.get('property_type', '').strip() or 'Unclassified',
                         'lat': lat, 'lng': lon, 's': 'illinois', 'evidence': evidence})
    return approved


def historical_illinois(rows, parcel_rows, approved):
    """Map uniquely matched historical leads only when coordinates are available."""
    index = {}
    for parcel in parcel_rows:
        pid = str(parcel.get('parcelid') or parcel.get('parcel_id') or '').strip().upper()
        if pid:
            index.setdefault(pid, []).append(parcel)
    existing = {p['id'].removeprefix('IL-').upper() for p in approved}
    found, skipped = [], []
    for r in rows:
        if r.get('match_status', '').strip().lower() != 'address candidate - requires parcel review':
            continue
        pid = r.get('parcel_id', '').strip()
        if not pid or pid.upper() in existing or len(index.get(pid.upper(), [])) != 1:
            skipped.append({'address': r.get('address'), 'reason': 'parcel missing or not unique'})
            continue
        parcel = index[pid.upper()][0]
        def coordinate(*keys):
            for k in keys:
                try:
                    return float(parcel.get(k) or r.get(k))
                except (TypeError, ValueError):
                    pass
            return None
        lat = coordinate('latitude_approx', 'latitude', 'lat', 'Latitude', 'LATITUDE', 'y', 'Y')
        lon = coordinate('longitude_approx', 'longitude', 'lng', 'lon', 'Longitude', 'LONGITUDE', 'x', 'X')
        if lat is None or lon is None or not (37 <= lat <= 40 and -91.5 <= lon <= -88):
            skipped.append({'address': r.get('address'), 'reason': 'no valid WGS84 coordinates in parcel CSV'})
            continue
        url = r.get('source_url', '').strip()
        if not url.startswith('https://'):
            skipped.append({'address': r.get('address'), 'reason': 'missing HTTPS evidence'})
            continue
        found.append({'id': 'IL-' + pid, 'a': r.get('address', ''),
                      'n': r.get('city', 'East St. Louis') + ', IL',
                      't': 'Historical demolition/condemnation lead (current status unknown)', 'lat': lat, 'lng': lon,
                      's': 'il_historical', 'evidence': url})
        existing.add(pid.upper())
    return found, skipped


def main():
    mo = csvrows(BASE / 'STL_Properties_v2.csv')
    if not mo:
        raise FileNotFoundError('STL_Properties_v2.csv missing or empty')
    il = csvrows(BASE / 'Illinois_Parcel_Review_Queue.csv')
    curated = csvrows(BASE / 'STL_Urbex_Research_Initial.csv')
    reviewed = csvrows(BASE / 'Illinois_Verified_Properties.csv')
    evidence_rows = csvrows(BASE / 'Property_Evidence.csv')
    approved = approved_illinois(reviewed)
    historical, skipped = historical_illinois(
        csvrows(BASE / "Illinois_Evidence_Match_Review.csv"), il, approved)
    leads, errors = {}, []
    for query in QUERIES:
        try:
            for item in rss(query):
                leads[item['url']] = item
        except Exception as exc:
            errors.append({'query': query, 'error': str(exc)})

    # Build a lightweight index; no property is verified by an indexed mention.
    address_index = []
    for row in il:
        addr = normalize(row.get('siteadr1', ''))
        if len(addr) >= 12:
            address_index.append((addr, row.get('parcelid', ''), row.get('sitecity', '')))
    for item in leads.values():
        title = normalize(item['title'])
        item['candidate_illinois_parcels'] = [
            {'parcel_id': parcel, 'city': city, 'match': 'address in title, unverified'}
            for addr, parcel, city in address_index if addr in title][:5]
        item['review_status'] = 'Unverified research lead'
        item['legal_access'] = 'Unknown / permission required'

    output = {'updated_at_utc': NOW, 'missouri_baseline_count': len(mo),
              'illinois_parcels_for_review': len(il),
              'illinois_approved_entries': len(approved),
              'illinois_historical_markers': len(historical),
              'illinois_historical_skipped': skipped,
              'research_leads': list(leads.values()), 'existing_references': curated,
              'fetch_errors': errors,
              'notice': 'Parcels and indexed links do not establish vacancy, conditions, or legal access.'}
    (BASE / 'urbex_research_updates.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')

    template = BASE / 'STL_Explorer_Map_v2.html'
    if not template.exists():
        raise FileNotFoundError('STL_Explorer_Map_v2.html missing')
    page = template.read_text(encoding='utf-8')
    if '</body>' not in page or 'const data=[' not in page or 'const map=L.map(' not in page:
        raise ValueError('Unexpected map template; refusing to overwrite index.html')

    # Evidence is manually reviewed and keyed to exact state + parcel ID.
    # Indexed search leads are never automatically promoted to verified evidence.
    evidence_by_key = {}
    allowed_status = {'supports vacancy', 'contradicts vacancy', 'historical context', 'unverified lead'}
    for row in evidence_rows:
        state = row.get('state', '').strip().upper()
        parcel = row.get('parcel_id', '').strip()
        status = row.get('finding', '').strip().lower()
        url = row.get('source_url', '').strip()
        parsed = urllib.parse.urlparse(url)
        if state not in ('MO', 'IL') or not parcel or status not in allowed_status:
            continue
        if parsed.scheme != 'https' or not parsed.netloc:
            continue
        item = {'title': row.get('title', '').strip()[:200],
                'url': url, 'source': row.get('source_name', '').strip()[:100],
                'date': row.get('source_date', '').strip()[:30],
                'finding': status, 'notes': row.get('notes', '').strip()[:500],
                'image_url': row.get('image_url', '').strip(),
                'image_permission': row.get('image_permission', '').strip().lower()}
        # Only display external images inline with an affirmative permission flag.
        img = urllib.parse.urlparse(item['image_url'])
        if item['image_permission'] != 'yes' or img.scheme != 'https' or not img.netloc:
            item['image_url'] = ''
        evidence_by_key.setdefault(state + ':' + parcel.upper(), []).append(item)
    output['property_evidence_entries'] = sum(map(len, evidence_by_key.values()))
    (BASE / 'urbex_research_updates.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')

    # Add a conservative, source-based nonresidential filter for Missouri.
    # Unknown property types remain unclassified; no visual review is implied.
    nonres_types = {'commercial', 'industrial', 'mixed-use'}
    nonres_ids = [str(r.get('id', '')).strip() for r in mo
                  if r.get('t', '').strip().lower() in nonres_types]
    filter_js = """
const knownNonresidential = new Set(__IDS__);
const nonresFilter = document.createElement('label');
nonresFilter.style.cssText = 'display:inline-flex;align-items:center;gap:6px;padding:7px 10px;background:white;border-radius:6px;font:13px system-ui;';
nonresFilter.innerHTML = '<input type="checkbox" id="nonres-only" style="width:17px;height:17px"> Nonresidential candidates (source-classified)';
const categorySelect = document.querySelector('#category');
categorySelect.parentNode.insertBefore(nonresFilter, categorySelect.nextSibling);
nonresFilter.querySelector('input').addEventListener('change', update);
""".replace('__IDS__', json.dumps(nonres_ids))
    if 'const cache=new Map();' not in page:
        raise ValueError('Missing marker cache insertion point for nonresidential filter')
    page = page.replace('const cache=new Map();', filter_js + '\nconst cache=new Map();', 1)
    filter_needle = "const selected=data.filter(p=>(!s||p.s===s)&&(!t||p.t===t)&&(!q||(p.a+' '+p.n+' '+p.id).toLowerCase().includes(q)));"
    filter_replacement = "const selected=data.filter(p=>(!document.querySelector('#nonres-only').checked||(p.s!=='illinois'&&p.s!=='il_historical'&&knownNonresidential.has(String(p.id))))&&(!s||p.s===s)&&(!t||p.t===t)&&(!q||(p.a+' '+p.n+' '+p.id).toLowerCase().includes(q)));"
    if filter_needle not in page:
        raise ValueError('Missing exact map filter insertion point')
    page = page.replace(filter_needle, filter_replacement, 1)
    output['missouri_source_classified_nonresidential'] = len(nonres_ids)

    # South City building-footprint review layer; independent of existing registry filters.
    south_rows = csvrows(BASE / 'South_City_Building_Imagery_Review.csv')
    south_markers = []
    for row in south_rows:
        try:
            lat, lng = float(row.get('latitude', '')), float(row.get('longitude', ''))
        except (ValueError, TypeError):
            continue
        if not (38.45 < lat < 38.70 and -90.45 < lng < -90.10):
            continue
        south_markers.append({
            'id': row.get('building_id', ''), 'lat': lat, 'lng': lng,
            'area': row.get('footprint_area_sqft_approx', ''),
            'status': row.get('nonresidential_status', 'UNVERIFIED'),
            'url': row.get('imagery_review_url', ''),
        })
    output['south_city_imagery_review_candidates'] = len(south_markers)
    south_payload = json.dumps(south_markers, ensure_ascii=False).replace('</', '<\\/')
    south_js = r"""
// Building footprints are review candidates, not verified nonresidential or vacant sites.
const southCityCandidates = __SOUTH_DATA__;
const southCityLayer = (typeof L.markerClusterGroup === 'function')
    ? L.markerClusterGroup({chunkedLoading:true, maxClusterRadius:55}) : L.layerGroup();
const southCityToggle = document.createElement('label');
southCityToggle.style.cssText = 'position:fixed;left:12px;bottom:20px;z-index:1100;background:white;padding:10px 12px;border:2px solid #7441a7;border-radius:8px;font:14px system-ui;box-shadow:0 2px 8px #0003;max-width:70vw;';
southCityToggle.innerHTML = '<input type="checkbox" id="south-city-review-toggle" checked> <b>South City building review ('+southCityCandidates.length+')</b>';
document.body.appendChild(southCityToggle);
const southEscape = x => String(x == null ? '' : x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
for (const b of southCityCandidates) {
  const m = L.circleMarker([b.lat,b.lng],{radius:5,color:'#7441a7',weight:1,fillColor:'#7441a7',fillOpacity:0.7});
  const href = /^https:\/\//.test(b.url) ? '<br><a target="_blank" rel="noopener noreferrer" href="'+southEscape(b.url)+'">Review aerial imagery</a>' : '';
  m.bindPopup('<b>South City building candidate</b><br>ID: '+southEscape(b.id)+'<br>Footprint: '+southEscape(b.area)+' sq ft<br>Nonresidential: '+southEscape(b.status)+'<br>Vacancy: unknown'+href);
  southCityLayer.addLayer(m);
}
southCityLayer.addTo(map);
southCityToggle.querySelector('input').addEventListener('change', e => {
  if(e.target.checked) map.addLayer(southCityLayer);
  else map.removeLayer(southCityLayer);
});
""".replace('__SOUTH_DATA__', south_payload)
    if 'const cache=new Map();' not in page:
        raise ValueError('Missing South City layer insertion point')
    page = page.replace('const cache=new Map();', south_js + '\nconst cache=new Map();', 1)

    # Append Illinois records to the existing data array before Leaflet initializes.
    # Avoid modifying the original 12,650 Missouri records.
    injection = '\n// Approved Illinois properties (independent vacancy evidence required).\n' \
                + 'data.push(...' + json.dumps(approved + historical, ensure_ascii=False).replace('</', '<\\/') + ');\n'
    page = page.replace('const map=L.map(', injection + 'const map=L.map(', 1)
    # Keep the same circle-marker style and filtering. New source uses the same palette.
    page = page.replace("lra:'#2564b3',illinois:'#278b56',il_historical:'#ef8b25'};", "lra:'#2564b3',illinois:'#ef8b25'};", 1)
    page = page.replace("lra:'LRA building candidate',illinois:'Illinois verified vacancy',il_historical:'Illinois historical demolition lead — status unverified'};",
                        "lra:'LRA building candidate',illinois:'Illinois verified vacancy'};", 1)
    # Add the Illinois source to the existing dropdown (no new UI layer).
    page = page.replace('<option value="lra">LRA only</option>',
                        '<option value="lra">LRA only</option><option value="illinois">Illinois verified</option><option value="il_historical">Illinois historical leads</option>', 1)
    # Existing popup uses a Missouri-specific address for Google Earth; fix for Illinois.
    page = page.replace("const street=encodeURIComponent(p.a+', St. Louis, MO');",
                        "const street=encodeURIComponent(p.a+', '+(p.s==='illinois'||p.s==='il_historical'?p.n:'St. Louis, MO'));", 1)
    # Display evidence links only on Illinois records, and escape attribute contents.
    page = page.replace("+'<br>Parcel: '+escapeHtml(p.id)+'<br><a target=",
                        "+'<br>Parcel: '+escapeHtml(p.id)+((p.s==='illinois'||p.s==='il_historical')&&p.evidence?'<br><a target=\"_blank\" rel=\"noopener noreferrer\" href=\"'+escapeHtml(p.evidence)+'\">Vacancy evidence</a>':'')+'<br><a target=", 1)
    page = page.replace("<span style=\"color:#2564b3\">●</span> LRA only';",
                        "<span style=\"color:#2564b3\">●</span> LRA only<br><span style=\"color:#ef8b25\">●</span> Illinois verified';", 1)
    # Load the evidence index before the marker factory. Popups remain lazy: do not
    # instantiate thousands of markers during page startup.
    payload = json.dumps(evidence_by_key, ensure_ascii=False).replace('</', '<\\/')
    evidence_js = r"""
const propertyEvidence = __PAYLOAD__;
function evidenceMarkup(p){
 const key=((p.s==='illinois'||p.s==='il_historical')?'IL:':'MO:')+String(p.id).replace(/^IL-/,'').toUpperCase();
 const items=propertyEvidence[key]||[];
 if(!items.length)return '<details><summary>Evidence (0)</summary>No reviewed evidence attached yet.</details>';
 const cards=items.map(e=>{
  const a='<a target="_blank" rel="noopener noreferrer" href="'+escapeHtml(e.url)+'">'+escapeHtml(e.title||e.source||'Source')+'</a>';
  const img=e.image_url?'<br><img loading="lazy" style="max-width:220px;max-height:150px" src="'+escapeHtml(e.image_url)+'" alt="Source image">':'';
  return '<div style="padding:8px 0;border-top:1px solid #ddd">'+a+'<br><small>'+escapeHtml(e.source)+' · '+escapeHtml(e.date)+' · '+escapeHtml(e.finding)+'</small><br>'+escapeHtml(e.notes)+img+'</div>';
 }).join('');
 return '<details><summary>Evidence ('+items.length+')</summary>'+cards+'</details>';
}
""".replace('__PAYLOAD__', payload)
    if 'const cache=new Map();' not in page or "m.bindPopup(()=>'<b>'+escapeHtml(p.a)" not in page:
        raise ValueError('Unexpected popup structure; refusing to publish evidence map')
    page = page.replace('const cache=new Map();', evidence_js + '\nconst cache=new Map();', 1)
    # Append to the existing popup markup, without changing its links or styling.
    page = page.replace("+'\x3c/a>');", "+'\x3c/a>'+evidenceMarkup(p));", 1) if False else page
    original = "</a>');\n cache.set(p,m);return m;"
    updated = "</a>'+evidenceMarkup(p));\n cache.set(p,m);return m;"
    if original not in page:
        raise ValueError('Expected marker popup terminator missing')
    page = page.replace(original, updated, 1)
    # Search the same fields as Missouri. City/state are stored in p.n.
    def card(item):
        title = html.escape(item.get('title') or item.get('location_reference') or 'Untitled')
        url = html.escape(item.get('url') or item.get('source_url') or '', quote=True)
        date = html.escape(item.get('published') or item.get('mentioned_on') or '')
        return f'<article class="research-card"><a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a><small>{date} · Unverified source lead</small></article>'

    cards = ''.join(card(x) for x in curated + list(leads.values()))
    panel = ('<style>#research-btn{position:fixed;right:12px;bottom:16px;z-index:99999;background:#17314b;color:white;border:0;border-radius:10px;padding:12px}'
             '#research-panel{display:none;position:fixed;z-index:100000;inset:5%;overflow:auto;background:white;padding:18px;border-radius:12px;box-shadow:0 0 0 100vmax #0009;font:14px system-ui}'
             '.research-card{border-top:1px solid #ddd;padding:10px 0}.research-card a{display:block}.research-card small{color:#555}</style>'
             '<button id="research-btn" onclick="document.getElementById(\'research-panel\').style.display=\'block\'">Urbex research MO + IL</button>'
             '<section id="research-panel"><button onclick="document.getElementById(\'research-panel\').style.display=\'none\'">Close</button>'
             '<h2>Missouri + Illinois research</h2><p>Illinois parcels awaiting verification: '
             + str(len(il)) + '. Approved Illinois entries: ' + str(len(approved))
             + '. Research leads do not prove vacancy or permission to enter.</p>'
             '<input placeholder="Search research" aria-label="Filter research" oninput="document.querySelectorAll(\'.research-card\').forEach(e=>e.style.display=e.textContent.toLowerCase().includes(this.value.toLowerCase())?\'\':\'none\')" style="width:90%;padding:9px"><div>'
             + cards + '</div></section>')
    page = page.replace('</body>', panel + '</body>', 1)
    (BASE / 'index.html').write_text(page, encoding='utf-8')
    print(f'MO baseline {len(mo)}; IL parcel review {len(il)}; IL approved mapped {len(approved)}; indexed leads {len(leads)}; errors {len(errors)}')


if __name__ == '__main__':
    main()
