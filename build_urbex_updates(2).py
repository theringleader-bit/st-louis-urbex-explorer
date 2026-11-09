#!/usr/bin/env python3
"""Unified Missouri/Illinois map and indexed research updater.

Only explicitly approved Illinois entries with evidence are mapped.
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


def main():
    mo = csvrows(BASE / 'STL_Properties_v2.csv')
    if not mo:
        raise FileNotFoundError('STL_Properties_v2.csv missing or empty')
    il = csvrows(BASE / 'Illinois_Parcel_Review_Queue.csv')
    curated = csvrows(BASE / 'STL_Urbex_Research_Initial.csv')
    reviewed = csvrows(BASE / 'Illinois_Verified_Properties.csv')
    approved = approved_illinois(reviewed)
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

    # Append Illinois records to the existing data array before Leaflet initializes.
    # Avoid modifying the original 12,650 Missouri records.
    injection = '\n// Approved Illinois properties (independent vacancy evidence required).\n' \
                + 'data.push(...' + json.dumps(approved, ensure_ascii=False).replace('</', '<\\/') + ');\n'
    page = page.replace('const map=L.map(', injection + 'const map=L.map(', 1)
    # Keep the same circle-marker style and filtering. New source uses the same palette.
    page = page.replace("lra:'#2564b3'};", "lra:'#2564b3',illinois:'#ef8b25'};", 1)
    page = page.replace("lra:'LRA building candidate'};",
                        "lra:'LRA building candidate',illinois:'Illinois verified vacancy'};", 1)
    # Add the Illinois source to the existing dropdown (no new UI layer).
    page = page.replace('<option value="lra">LRA only</option>',
                        '<option value="lra">LRA only</option><option value="illinois">Illinois verified</option>', 1)
    # Existing popup uses a Missouri-specific address for Google Earth; fix for Illinois.
    page = page.replace("const street=encodeURIComponent(p.a+', St. Louis, MO');",
                        "const street=encodeURIComponent(p.a+', '+(p.s==='illinois'?p.n:'St. Louis, MO'));", 1)
    # Display evidence links only on Illinois records, and escape attribute contents.
    page = page.replace("+'<br>Parcel: '+escapeHtml(p.id)+'<br><a target=",
                        "+'<br>Parcel: '+escapeHtml(p.id)+(p.s==='illinois'&&p.evidence?'<br><a target=\"_blank\" rel=\"noopener noreferrer\" href=\"'+escapeHtml(p.evidence)+'\">Vacancy evidence</a>':'')+'<br><a target=", 1)
    page = page.replace("<span style=\"color:#2564b3\">●</span> LRA only';",
                        "<span style=\"color:#2564b3\">●</span> LRA only<br><span style=\"color:#ef8b25\">●</span> Illinois verified';", 1)
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
