#!/usr/bin/env python3
"""Add separate provisional footprint candidates to existing generated index.html."""
import csv,json
from pathlib import Path
P=Path(__file__).resolve().parent
csv_path=P/'South_City_Building_Imagery_Review.csv'
html_path=P/'index.html'
if not csv_path.exists() or not html_path.exists():raise FileNotFoundError('Run footprint scanner and map builder first')
with csv_path.open(newline='',encoding='utf-8') as f:
    rows=list(csv.DictReader(f))
features=[]
for r in rows:
    try:lat,lon=float(r['latitude']),float(r['longitude'])
    except (ValueError,KeyError):continue
    features.append({'lat':lat,'lon':lon,'area':r['footprint_area_sqft_approx'],
                     'id':r['building_id'],'addr':r['near_registry_address'],
                     'url':r['imagery_review_url']})
page=html_path.read_text(encoding='utf-8')
if 'const map=L.map(' not in page:raise ValueError('Map initialization not found')
# Load AFTER map and all existing JavaScript are initialized, before closing body.
js='''
<style>#south-review-control{position:fixed;left:12px;bottom:14px;z-index:1001;background:white;padding:9px 12px;border:1px solid #bbb;border-radius:8px;font:13px system-ui;max-width:260px}#south-review-control label{cursor:pointer}</style>
<div id="south-review-control"><label><input type="checkbox" id="south-review-toggle"> South City large-building review (<span id="south-review-count"></span>)</label><br><small>Unverified building type and vacancy. Imagery review needed.</small></div>
<script>
(function(){
const candidates=__DATA__;
const count=document.getElementById('south-review-count');count.textContent=candidates.length.toLocaleString();
const layer=L.layerGroup();
function escapeReview(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
let loaded=false;
document.getElementById('south-review-toggle').addEventListener('change',function(){
 if(this.checked){
  if(!loaded){for(const p of candidates){
    const m=L.circleMarker([p.lat,p.lon],{radius:5,color:'#713e9c',weight:1,fillColor:'#a77bc6',fillOpacity:.65});
    m.bindPopup('<b>Building footprint: visual review required</b><br>'+escapeReview(p.addr||'No matched registry address')+'<br>Approx. footprint: '+escapeReview(p.area)+' sq ft<br>Building use: unverified<br>Vacancy: unknown<br><a target="_blank" rel="noopener noreferrer" href="'+escapeReview(p.url)+'">Review satellite imagery</a>');
    layer.addLayer(m);
   }loaded=true;}
   layer.addTo(map);
 }else map.removeLayer(layer);
});
})();
</script>
'''.replace('__DATA__',json.dumps(features).replace('</','<\\/'))
if 'id="south-review-toggle"' in page:raise ValueError('Layer already inserted')
page=page.replace('</body>',js+'</body>',1)
html_path.write_text(page,encoding='utf-8')
print('Added',len(features),'provisional building footprint markers (off by default)')
