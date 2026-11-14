#!/usr/bin/env python3
"""South St. Louis footprint candidate inventory, for imagery-assisted review.
Source: City of St. Louis Assessor Public Parcels, Buildings layer 9.
Does NOT assert vacancy, access, or nonresidential use.
"""
import csv, json, math, time, urllib.parse, urllib.request
from collections import defaultdict
from pathlib import Path
BASE=Path(__file__).resolve().parent
API='https://maps8.stlouis-mo.gov/arcgis/rest/services/ASSESSOR/Assessor_Public_Parcels/MapServer/9/query'
# Approximate South City coverage; adjust bounds for later citywide runs.
WEST,EAST,SOUTH,NORTH=-90.315,-90.175,38.525,38.618
STEP=.009
MIN_AREA_M2=280

def request(params, retries=3):
    data=urllib.parse.urlencode(params).encode()
    for attempt in range(retries):
        try:
            req=urllib.request.Request(API,data=data,headers={'User-Agent':'STL-Building-Research/1.0'})
            with urllib.request.urlopen(req,timeout=50) as response:
                obj=json.load(response)
            if 'error' in obj: raise RuntimeError(str(obj['error']))
            return obj
        except Exception:
            if attempt==retries-1:raise
            time.sleep(2**attempt)

def ring_area(ring):
    # local equirectangular approximation; suitable for screening, not cadastral measurement
    if len(ring)<3:return 0
    lat=sum(p[1] for p in ring)/len(ring)
    factor_x=111320*math.cos(math.radians(lat));factor_y=111132
    return abs(sum((ring[i][0]*factor_x)*(ring[(i+1)%len(ring)][1]*factor_y)-(ring[(i+1)%len(ring)][0]*factor_x)*(ring[i][1]*factor_y) for i in range(len(ring)))/2)

def geometry_stats(geom):
    rings=geom.get('rings',[])
    if not rings:return None
    # Outer-ring subtraction not required for initial candidate screening; use largest ring.
    outer=max(rings,key=ring_area)
    area=ring_area(outer)
    pts=outer[:-1] if len(outer)>1 and outer[0]==outer[-1] else outer
    if not pts:return None
    return sum(p[1] for p in pts)/len(pts),sum(p[0] for p in pts)/len(pts),round(area)

def prior_reviews(path):
    """Retain human review decisions across automated refreshes."""
    if not path.exists():
        return {}
    with path.open(newline='', encoding='utf-8-sig') as f:
        return {r['building_id']: r for r in csv.DictReader(f) if r.get('building_id')}


def registry_classification(value):
    value = str(value or '').strip().lower()
    if value in ('commercial', 'industrial', 'mixed-use', 'institutional'):
        return 'SOURCE_CLASSIFIED_NONRESIDENTIAL'
    if value in ('residential', 'single family', 'single-family', 'multifamily', 'multi-family'):
        return 'SOURCE_CLASSIFIED_RESIDENTIAL'
    return 'UNVERIFIED'


def candidate_priority(area, classification, registry_distance):
    """Review priority only; never a probability of vacancy."""
    if classification == 'SOURCE_CLASSIFIED_NONRESIDENTIAL':
        return 'HIGH'
    if classification == 'SOURCE_CLASSIFIED_RESIDENTIAL':
        return 'LOW'
    return 'MEDIUM' if area >= 1000 else 'LOW'


def main():
    seen={}; errors=[]; cells=0
    y=SOUTH
    while y<NORTH:
        x=WEST
        while x<EAST:
            x2=min(x+STEP,EAST);y2=min(y+STEP,NORTH);cells+=1
            params={'f':'json','where':'1=1','geometry':json.dumps({'xmin':x,'ymin':y,'xmax':x2,'ymax':y2,'spatialReference':{'wkid':4326}}),
                    'geometryType':'esriGeometryEnvelope','inSR':4326,'spatialRel':'esriSpatialRelIntersects',
                    'outFields':'*','outSR':4326,'returnGeometry':'true','resultRecordCount':2000}
            try:
                obj=request(params)
                if obj.get('exceededTransferLimit'):
                    errors.append(f'Too many features in cell {x:.4f},{y:.4f}; reduce STEP')
                    x=x2;continue
                for feature in obj.get('features',[]):
                    attr=feature.get('attributes',{}); geom=feature.get('geometry',{})
                    oid=attr.get('OBJECTID') or attr.get('ObjectID') or attr.get('FID')
                    stats=geometry_stats(geom)
                    if stats is None:continue
                    lat,lon,area=stats
                    if not (SOUTH<=lat<=NORTH and WEST<=lon<=EAST):continue
                    key=str(oid) if oid is not None else f'{lat:.6f},{lon:.6f}'
                    if key not in seen:seen[key]=(lat,lon,area)
            except Exception as exc:errors.append(f'{x:.4f},{y:.4f}: {exc}')
            x=x2
        y=y2
    if errors:
        (BASE/'South_City_Scan_Errors.json').write_text(json.dumps({'cells':cells,'errors':errors},indent=2))
        raise RuntimeError(f'{len(errors)} GIS grid cells failed; refusing incomplete output. See South_City_Scan_Errors.json')
    registry=[]
    with (BASE/'STL_Properties_v2.csv').open(newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            try:registry.append((float(r['lat']),float(r['lng']),r))
            except (ValueError,KeyError):pass
    old_reviews = prior_reviews(BASE/'South_City_Building_Imagery_Review.csv')
    # Spatial buckets reduce the cost of matching thousands of footprints.
    bucket_size = .001
    buckets = defaultdict(list)
    for rlat, rlon, r in registry:
        buckets[(math.floor(rlat/bucket_size), math.floor(rlon/bucket_size))].append((rlat, rlon, r))
    rows=[]
    for oid,(lat,lon,area) in seen.items():
        if area<MIN_AREA_M2:continue
        nearby=[]
        iy, ix = math.floor(lat/bucket_size), math.floor(lon/bucket_size)
        for by in range(iy-1,iy+2):
            for bx in range(ix-1,ix+2):
                for rlat,rlon,r in buckets.get((by,bx),[]):
                    dy=(lat-rlat)*111132;dx=(lon-rlon)*111320*math.cos(math.radians(lat))
                    d=math.hypot(dx,dy)
                    if d<45:nearby.append((d,r))
        nearby.sort(key=lambda z:z[0])
        nearest=nearby[0][1] if nearby else {}
        distance=round(nearby[0][0],1) if nearby else ''
        classification=registry_classification(nearest.get('t',''))
        priority=candidate_priority(area, classification, distance)
        previous=old_reviews.get('STL-BLDG-'+oid,{})
        # Google Maps satellite view is a review link, NOT evidence of review.
        imagery=f'https://www.google.com/maps/@{lat:.7f},{lon:.7f},19z/data=!3m1!1e3'
        rows.append({'building_id':'STL-BLDG-'+oid,'latitude':f'{lat:.7f}','longitude':f'{lon:.7f}',
                     'footprint_area_m2_approx':area,'footprint_area_sqft_approx':round(area*10.7639),
                     'near_registry_address':nearest.get('a',''),'near_registry_id':nearest.get('id',''),
                     'near_registry_type':nearest.get('t',''),
                     'near_registry_distance_m_approx':distance,
                     'candidate_reason':('Nearby registry class: '+str(nearest.get('t','')) if classification=='SOURCE_CLASSIFIED_NONRESIDENTIAL' else 'Large building footprint; use and vacancy unverified'),
                     'review_priority':priority,
                     'nonresidential_status':previous.get('nonresidential_status') or classification,
                     'vacancy_status':previous.get('vacancy_status') or 'UNKNOWN',
                     'imagery_review_url':imagery,'gis_source':API.rsplit('/query',1)[0],
                     'review_notes':previous.get('review_notes',''),
                     'review_evidence_url':previous.get('review_evidence_url',''),
                     'review_date':previous.get('review_date','')})
    rows.sort(key=lambda r:({'HIGH':0,'MEDIUM':1,'LOW':2}[r['review_priority']],-r['footprint_area_m2_approx']))
    fields=['building_id','latitude','longitude','footprint_area_m2_approx','footprint_area_sqft_approx',
            'near_registry_address','near_registry_id','near_registry_type','near_registry_distance_m_approx','candidate_reason','review_priority',
            'nonresidential_status','vacancy_status','imagery_review_url','gis_source','review_notes','review_evidence_url','review_date']
    with (BASE/'South_City_Building_Imagery_Review.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    report={'footprints_retrieved':len(seen),'large_footprints_for_review':len(rows),'grid_cells':cells,
            'minimum_area_m2':MIN_AREA_M2,'classification':'unverified: visual review required',
            'source':API.rsplit('/query',1)[0],
            'review_priority_counts':{level:sum(r['review_priority']==level for r in rows) for level in ('HIGH','MEDIUM','LOW')},
            'note':'Priority is not evidence of vacancy. Registry matches within 45m may refer to neighboring buildings.'}
    (BASE/'South_City_Scan_Report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
