#!/usr/bin/env python3
"""Dependency-free, localized static site generator for GitHub Pages."""
import html
import json
import os
import re
import shutil
from datetime import datetime, date
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist'
BASE = '/' + os.environ.get('BASE_PATH', '').strip('/') if os.environ.get('BASE_PATH', '').strip('/') else ''
SITE = os.environ.get('SITE_URL', 'http://localhost:4173').rstrip('/')
TODAY = datetime.now(ZoneInfo('Europe/Lisbon')).date().isoformat()
LANGS = json.loads((ROOT / 'data/i18n.json').read_text())
INPUT = ROOT / os.environ.get('DATA_FILE', 'data/rooms.json')
DATA = json.loads(INPUT.read_text())

def esc(value):
    return html.escape(str(value), quote=True)

def localized(value, lang):
    return value.get(lang) or value.get('en', '') if isinstance(value, dict) else value or ''

def path(route='', lang='en'):
    return BASE + '/' + (lang + '/' if lang != 'en' else '') + route.strip('/') + ('/' if route.strip('/') else '')

def asset(name):
    return f'{BASE}/assets/{name}'

def valid_id(value):
    return bool(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', str(value or '')))

def public_room(room):
    return room.get('published') is True and room.get('status') != 'draft' and valid_id(room.get('id')) and room.get('title', {}).get('en') and isinstance(room.get('price'), (int, float)) and room['price'] > 0

APTS = {a['id']: a for a in DATA.get('apartments', []) if a.get('published') is True and valid_id(a.get('id'))}
ROOMS = [r for r in DATA.get('rooms', []) if public_room(r) and (not r.get('apartmentId') or r['apartmentId'] in APTS)]
if len({r['id'] for r in ROOMS}) != len(ROOMS):
    raise ValueError('Duplicate room IDs')

def available(room):
    return room.get('status') == 'available' or (room.get('status') == 'available_from' and valid_date(room.get('availableFrom')) and room['availableFrom'] <= TODAY)

def valid_date(value):
    try:
        return bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', value or '')) and date.fromisoformat(value) is not None
    except (ValueError, TypeError):
        return False

def upcoming(room):
    return room.get('status') == 'available_from' and valid_date(room.get('availableFrom')) and room['availableFrom'] > TODAY

def display_date(value, lang):
    try:
        d = datetime.strptime(value[:10], '%Y-%m-%d')
        return d.strftime('%d.%m.%Y') if lang == 'uk' else d.strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        return ''

def status(room, lang):
    t = LANGS[lang]
    if available(room):
        return t['available']
    if upcoming(room):
        return f"{t['availableFrom']} {display_date(room['availableFrom'], lang)}"
    return t['occupied']

def money(value):
    return f'€{value:,.0f}' if float(value).is_integer() else f'€{value:,.2f}'

def wa(lang, room=None, apartment=None):
    t = LANGS[lang]
    if room:
        text = t['roomMessage'].format(name=f"{t['roomLabel']} {room.get('name', room['id'])} — {localized(room['title'], lang)}", area=room.get('area', ''), price=f"{room['price']:g}")
    elif apartment:
        text = t['apartmentMessage'].format(name=apartment.get('name', apartment['id']), area=apartment.get('area', ''))
    else:
        text = t['genericMessage']
    return 'https://wa.me/380674575314?' + urlencode({'text': text})

def button(href, text, secondary=False):
    return f'<a class="button {"secondary" if secondary else ""}" href="{esc(href)}">{esc(text)} <span aria-hidden="true">↗</span></a>'

def photo_src(value):
    if value.startswith('/assets/'):
        return BASE + value
    return value if urlparse(value).scheme == 'https' else ''

def photo(room, lang, index=0, large=False):
    t = LANGS[lang]
    photos = room.get('photos') or []
    src = photo_src(photos[index]) if index < len(photos) else ''
    if src:
        return f'<img src="{esc(src)}" alt="{esc(localized(room.get("title", room.get("name", "")), lang))} — {index+1}" {"" if large else "loading=\"lazy\""} decoding="async">'
    note=f'<small>{esc(t["photoNote"])}</small>' if large else ''
    return f'<div class="placeholder variant-{int(room.get("price", 0)) % 3}"><span class="placeholder-art" aria-hidden="true">✳</span><span class="placeholder-label">{esc(t["photo"])}</span>{note}</div>'

def room_card(room, lang, apt_page=False):
    t = LANGS[lang]
    occupied = not available(room)
    title = localized(room['title'], lang)
    features = []
    if room.get('bed') in ('bunk','double','single'):
        features.append(t[room['bed']])
    if room.get('privateBathroom') is True:
        features.append(t['privateBathroom'])
    if room.get('maxGuests'):
        features.append(f"{t['maxGuests']}: {room['maxGuests']}")
    apt = APTS.get(room.get('apartmentId'), {})
    area = room.get('area') or apt.get('area')
    address = room.get('address') or apt.get('address')
    return f'''<article class="room-card {'occupied' if apt_page and occupied else ''}">
<a class="card-image" href="{path('rooms/'+room['id'], lang)}" aria-label="{esc(t['details']+': '+title)}">{photo(room, lang)}<span class="status {'muted' if occupied else ''}"><i></i>{esc(status(room, lang))}</span><span class="card-arrow" aria-hidden="true">↗</span></a>
<div class="card-meta"><span>{esc(area or '')}</span><span>{esc(room.get('name',''))}</span></div>
<h3><a href="{path('rooms/'+room['id'], lang)}">{esc(title)}</a></h3>
{f'<p class="address">{esc(address)}</p>' if address else ''}
<p class="card-features">{esc(' · '.join(features))}</p>
<div class="card-price"><strong>{money(room['price'])}</strong> <span>{esc(t['month'])}</span></div><p class="card-bills">{esc(t['bills'])}</p></article>'''

def terms(lang):
    t = LANGS[lang]
    items = ''.join(f'<li><span class="term-number">0{i+1}</span><div><h3>{esc(h)}</h3><p>{esc(b)}</p></div></li>' for i,(h,b) in enumerate(zip(t['termHead'], t['termBody'])))
    return f'<section class="terms section" id="terms"><div><p class="eyebrow">RUMBON</p><h2>{esc(t["terms"])}</h2><p class="muted-text">{esc(t["termsIntro"])}</p></div><ol>{items}</ol></section>'

def footer(lang):
    t=LANGS[lang]
    return f'''<section class="contact-banner" id="contact"><div><span class="eyebrow">{esc(t['contact'])}</span><h2>{esc(t['ask'])}</h2><p>{esc(t['askSub'])}</p></div>{button(wa(lang),t['chat'])}</section>
<footer><div class="footer-top"><div><a href="{path('',lang)}" class="wordmark">Rumbon<span>.</span></a><p>{esc(t['footer'])}</p></div><div class="contacts"><a href="https://wa.me/380674575314">WhatsApp · +380 67 457 53 14 ↗</a><a href="https://t.me/danechkabelyi">Telegram · @danechkabelyi ↗</a><a href="mailto:danechkabelyi@gmail.com">danechkabelyi@gmail.com ↗</a></div></div><div class="footer-bottom"><span>© {datetime.now().year} Rumbon</span><span>{esc(t['made'])} <span aria-hidden="true">☀</span></span><a href="{path('',lang)}#terms">{esc(t['terms'])}</a></div></footer>'''

def render(route, lang, title, description, content, map_payload=None, image=None, noindex=False):
    t=LANGS[lang]
    full_url=SITE+path(route,lang)[len(BASE):]
    links=''.join(f'<link rel="alternate" hreflang="{code}" href="{esc(SITE+path(route,code)[len(BASE):])}">' for code in LANGS)
    languages=''.join(f'<a lang="{code}" hreflang="{code}" href="{path(route,code)}" {"aria-current=\"page\"" if code==lang else ""}>{label}</a>' for code,label in [('en','EN'),('uk','УКР'),('pt','PT')])
    og_image=SITE+'/assets/share.png'
    if image and photo_src(image):
        og_image=photo_src(image)
        if og_image.startswith('/'):
            og_image=SITE+og_image[len(BASE):]
    page=f'''<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="theme-color" content="#225c50"><title>{esc(title)}</title><meta name="description" content="{esc(description)}"><link rel="canonical" href="{esc(full_url)}">{links}<link rel="alternate" hreflang="x-default" href="{esc(SITE+path(route)[len(BASE):])}"><meta property="og:type" content="website"><meta property="og:site_name" content="Rumbon"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{esc(full_url)}"><meta property="og:image" content="{esc(og_image)}"><meta property="og:locale" content="{dict(en='en_GB',uk='uk_UA',pt='pt_PT')[lang]}"><meta name="twitter:card" content="summary_large_image">{'<meta name="robots" content="noindex">' if noindex else ''}<link rel="icon" href="{asset('favicon.svg')}" type="image/svg+xml"><link rel="stylesheet" href="{asset('style.css')}">{f'<link rel="stylesheet" href="{asset("vendor/leaflet.css")}">' if map_payload is not None else ''}<script src="{asset('app.js')}" defer></script></head><body><a class="skip" href="#main">{esc(t['skip'])}</a><header class="header"><a class="wordmark" href="{path('',lang)}" aria-label="Rumbon">Rumbon<span>.</span></a><nav aria-label="{esc(t['rooms'])}"><a href="{path('',lang)}#rooms">{esc(t['rooms'])}</a><a href="{path('',lang)}#neighbourhood">{esc(t['map'])}</a><a href="{path('',lang)}#contact">{esc(t['contact'])} ↗</a></nav><div class="languages" aria-label="Language / Мова / Idioma">{languages}</div></header><main id="main">{content}</main>{footer(lang)}<dialog id="gallery-dialog"><form method="dialog"><button aria-label="{esc(t['close'])}" class="gallery-close">×</button></form><img id="gallery-image" alt=""><div class="gallery-controls"><button type="button" data-gallery-prev aria-label="{esc(t['previous'])}">←</button><span id="gallery-counter" aria-live="polite"></span><button type="button" data-gallery-next aria-label="{esc(t['next'])}">→</button></div></dialog>'''
    if map_payload is not None:
        payload=json.dumps({'groups':map_payload,'labels':t},ensure_ascii=False).replace('<','\\u003c')
        page+=f'<script id="map-data" type="application/json">{payload}</script><script src="{asset("vendor/leaflet.js")}" defer></script>'
    page+='</body></html>'
    directory=OUT / ((lang+'/' if lang!='en' else '') + route.strip('/'))
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'index.html').write_text(page)
    return full_url

def map_groups(lang):
    groups={}
    for room in ROOMS:
        if not (available(room) or upcoming(room)):
            continue
        apt=APTS.get(room.get('apartmentId'),{})
        lat=room.get('lat') if room.get('lat') is not None else apt.get('lat')
        lon=room.get('lng') if room.get('lng') is not None else apt.get('lng')
        if not (isinstance(lat,(int,float)) and isinstance(lon,(int,float)) and -90<=lat<=90 and -180<=lon<=180):
            continue
        key=room.get('apartmentId') or room['id']
        group=groups.setdefault(key,{'lat':lat,'lng':lon,'rooms':[]})
        siblings=sorted([r for r in ROOMS if r.get('apartmentId')==room.get('apartmentId')],key=lambda r:(r.get('order') or 0,r['id'])) if apt else [room]
        group['rooms'].append({'name':room.get('name',''),'title':localized(room['title'],lang),'price':money(room['price']),'status':status(room,lang),'photo':photo_src((room.get('photos') or [''])[0]),'url':path('rooms/'+room['id'],lang),'index':next((i+1 for i,r in enumerate(siblings) if r['id']==room['id']),1),'total':apt.get('totalRooms') or len(siblings)})
    return list(groups.values())

def home(lang):
    t=LANGS[lang]
    now=sorted([r for r in ROOMS if available(r)],key=lambda r:(r.get('order') or 0,r['id']))
    soon=sorted([r for r in ROOMS if upcoming(r)],key=lambda r:(r['availableFrom'],r.get('order') or 0,r['id']))
    minimum=min((r['price'] for r in now+soon),default=None)
    price=f'<span>{esc(t["from"])}</span> <strong>{money(minimum)}</strong> <span>{esc(t["month"])}</span>' if minimum else esc(t['direct'])
    help_card=f'<aside class="help-card"><span class="help-art" aria-hidden="true">↗</span><h3>{esc(t["more"])}</h3><p>{esc(t["moreSub"])}</p><a href="{esc(wa(lang))}">{esc(t["contact"])} ↗</a></aside>'
    content=f'''<section class="hero"><div class="hero-copy"><p class="eyebrow"><span class="tiny-sun" aria-hidden="true">☀</span> {esc(t['eyebrow'])}</p><h1>{esc(t['hero1'])}<br><em>{esc(t['hero2'])}</em></h1><p class="hero-intro">{esc(t['intro'])}</p>{button('#rooms',t['explore'])}<div class="hero-location"><span class="location-dot"></span> LISBON, PORTUGAL <span>38°43′N 9°08′W</span></div></div><div class="hero-art" aria-hidden="true"><div class="sun"></div><div class="tile-grid">{''.join('<i></i>' for _ in range(12))}</div><span class="art-word">olá,<br>Lisboa.</span><span class="art-caption">YOUR NEXT CHAPTER LIVES HERE.</span><div class="price-sticker">{price}</div></div></section>
<div class="benefits"><span>✳ {esc(t['bills'])}</span><span>◷ {esc(t['min'])}</span><span>↗ {esc(t['direct'])}</span></div>
<section class="section rooms-section" id="rooms"><div class="section-heading"><div><p class="eyebrow">{esc(t['rooms'])}</p><h2>{esc(t['now'])}</h2><p class="muted-text">{esc(t['nowSub'])}</p></div><span class="room-count">{len(now):02d} <span>{esc(t['rooms'].lower())}</span></span></div><div class="room-grid">{''.join(room_card(r,lang) for r in now) if now else f'<p class="empty-rooms">{esc(t["empty"])}</p>'}{help_card if now else ''}</div></section>'''
    if soon:
        content+=f'<section class="section"><h2>{esc(t["soon"])}</h2><p class="muted-text">{esc(t["soonSub"])}</p><div class="room-grid">'+''.join(room_card(r,lang) for r in soon)+'</div></section>'
    groups=map_groups(lang)
    note=f'<div class="map-note"><span aria-hidden="true">⌖</span><strong>{esc(t["mapEmpty"])}</strong><p>{esc(t["mapMissing"])}</p></div>' if not groups else ''
    content+=f'<section class="section map-section" id="neighbourhood"><div class="section-heading"><div><p class="eyebrow">LISBON, PORTUGAL</p><h2>{esc(t["mapTitle"])}</h2><p class="muted-text">{esc(t["mapIntro"])}</p></div></div><div class="map-wrap"><div id="room-map" role="region" aria-label="{esc(t["map"])}"></div>{note}</div><p class="map-status" id="map-status" role="status">{esc(t["mapPartial"]) if groups and sum(len(g["rooms"]) for g in groups)<len(now+soon) else ""}</p></section>'
    return render('',lang,f'Rumbon · {dict(en="Rooms in Lisbon",uk="Кімнати в Лісабоні",pt="Quartos em Lisboa")[lang]}',t['ogDescription'],content+terms(lang),groups)

def features(entity, lang, apartment=None):
    t=LANGS[lang]
    rows=[]
    boolean_keys=['privateBathroom','washer','wifi','tv','ac','heating','window','wardrobe','desk','miniFridge','furnished','elevator','balcony']
    for key in boolean_keys:
        v=entity.get(key)
        if v is None and apartment and key in ('washer','wifi','elevator','balcony'):
            v=apartment.get(key)
        if isinstance(v,bool):
            rows.append((t[key],t['yes'] if v else t['no']))
    if entity.get('bed') in ('bunk','double','single'):
        rows.insert(0,(t['bed'],t[entity['bed']]))
    for key in ('maxGuests','size','floor','buildingFloors','metro','address','totalRooms'):
        value=entity.get(key)
        if value is None and apartment and key in ('floor','buildingFloors','address'):
            value=apartment.get(key)
        if value is not None and value!='':
            rows.append((t[key],f'{value} m²' if key=='size' else str(value)))
    return '<dl class="feature-list">'+''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k,v in rows)+'</dl>' if rows else ''

def gallery(entity,lang):
    photos=[p for p in entity.get('photos',[]) if photo_src(p)]
    entity={**entity,'photos':photos}
    if not photos:
        return '<div class="gallery empty-gallery">'+photo(entity,lang,large=True)+'</div>'
    return '<div class="gallery">'+''.join(f'<button type="button" class="gallery-tile" data-gallery-index="{i}" aria-label="{esc(LANGS[lang]["gallery"])} {i+1}">{photo(entity,lang,i,large=i==0)}</button>' for i in range(min(5,len(photos))))+'</div><script id="gallery-data" type="application/json">'+json.dumps([photo_src(p) for p in photos],ensure_ascii=False).replace('<','\\u003c')+'</script>'

def room_page(room,lang):
    t=LANGS[lang]
    apt=APTS.get(room.get('apartmentId'),{})
    title=localized(room['title'],lang)
    description=localized(room.get('description',{}),lang)
    siblings=[r for r in ROOMS if apt and r.get('apartmentId')==apt['id'] and r['id']!=room['id'] and (available(r) or upcoming(r))]
    content=f'''<div class="detail-page"><a class="back-link" href="{path('',lang)}">← {esc(t['back'])}</a><div class="detail-heading"><div><p class="eyebrow">{esc(room.get('area') or apt.get('area',''))} · {esc(room.get('name',''))}</p><h1>{esc(title)}</h1></div><span class="status inline-status"><i></i>{esc(status(room,lang))}</span></div>{gallery(room,lang)}<div class="detail-columns"><div><section class="detail-section"><h2>{esc(t['aboutRoom'])}</h2><p class="description">{esc(description)}</p>{f'<p class="info-note">{esc(t["incomplete"])}</p>' if room.get('incomplete') else ''}</section><section class="detail-section"><h2>{esc(t['features'])}</h2>{features(room,lang,apt)}</section><section class="detail-section"><h2>{esc(t['aboutApartment'])}</h2>{button(path('apartments/'+apt['id'],lang),t['viewApartment'],True) if apt else '<p class="muted-text">'+esc(t['apartmentPending'])+'</p>'}</section></div><aside class="inquiry"><div class="inquiry-price">{money(room['price'])} <span>{esc(t['month'])}</span></div><p class="bills-label">✳ {esc(t['bills'])}</p><hr><dl><div><dt>{esc(t['availability'])}</dt><dd>{esc(status(room,lang))}</dd></div><div><dt>{esc(t['deposit'])}</dt><dd>{money(room['price']/2)}</dd></div><div><dt>{esc(t['firstPayment'])}</dt><dd>{money(room['price']*1.5)}</dd></div></dl>{button(wa(lang,room=room),t['request'])}<p class="inquiry-note">{esc(t['noPayment'])}</p><p class="inquiry-note">{esc(t['min'])}</p></aside></div>'''
    if siblings:
        content+=f'<section class="section"><h2>{esc(t["inApartment"])}</h2><div class="room-grid">'+''.join(room_card(r,lang) for r in siblings)+'</div></section>'
    content+='</div>'+terms(lang)
    return render('rooms/'+room['id'],lang,f'{title} · {money(room["price"])}/'+dict(en='month',uk='місяць',pt='mês')[lang]+' · Rumbon',description or t['ogDescription'],content,image=(room.get('photos') or [None])[0])

def apartment_page(apt,lang):
    t=LANGS[lang]
    rooms=sorted([r for r in ROOMS if r.get('apartmentId')==apt['id']],key=lambda r:(not available(r),r.get('order') or 0,r['id']))
    free=sum(available(r) for r in rooms)
    total=apt.get('totalRooms') or len(rooms)
    all_free=total>0 and free==total
    label=t['allFree'] if all_free else t['freeCount'].format(free=free,total=total)
    name=localized(apt.get('title',apt.get('name',apt['id'])),lang)
    content=f'<div class="detail-page"><a class="back-link" href="{path("",lang)}">← {esc(t["back"])}</a><div class="detail-heading"><div><p class="eyebrow">{esc(t["apartmentLabel"])} · {esc(apt.get("area",""))}</p><h1>{esc(name)}</h1></div><span class="status inline-status">{esc(label)}</span></div>{gallery(apt,lang)}<section class="detail-section"><h2>{esc(t["aboutApartment"])}</h2>{features(apt,lang)}</section>'
    if all_free:
        content+=f'<div class="whole-apartment"><h2>{esc(t["allFree"])}</h2>{button(wa(lang,apartment=apt),t["wholeApartment"])}</div>'
    for key in ('kitchen','bathroom','shared'):
        value=localized(apt.get(key,''),lang)
        photos=apt.get(key+'Photos',[])
        if value or photos:
            content+=f'<section class="detail-section"><h2>{esc(t["kitchen" if key=="kitchen" else "bathroom" if key=="bathroom" else "shared"])}</h2>{f"<p>{esc(value)}</p>" if value else ""}<div class="shared-photos">'+''.join(f'<a href="{esc(photo_src(p))}"><img loading="lazy" src="{esc(photo_src(p))}" alt="{esc(t[key])}"></a>' for p in photos if photo_src(p))+'</div></section>'
    content+=f'<section class="section"><h2>{esc(t["allRooms"])}</h2><p class="muted-text">{esc(label)}</p><div class="room-grid">'+''.join(room_card(r,lang,True) for r in rooms)+'</div></section></div>'+terms(lang)
    return render('apartments/'+apt['id'],lang,f'{name} · Rumbon',f'{name}. {label}. '+t['ogDescription'],content,image=(apt.get('photos') or [None])[0])

def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT/'assets',OUT/'assets')
    urls=[]
    for lang in LANGS:
        urls.append(home(lang))
        for room in ROOMS:
            urls.append(room_page(room,lang))
        for apt in APTS.values():
            urls.append(apartment_page(apt,lang))
    t=LANGS['en']
    render('404', 'en', 'Page not found · Rumbon', t['errorBody'],f'<section class="error-page"><p class="eyebrow">404</p><h1>{t["errorTitle"]}</h1><p>{t["errorBody"]}</p>{button(path(),t["back"])}</section>',noindex=True)
    shutil.copyfile(OUT/'404/index.html',OUT/'404.html')
    (OUT/'.nojekyll').touch()
    (OUT/'robots.txt').write_text(f'User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n')
    (OUT/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(f'<url><loc>{esc(url)}</loc></url>' for url in urls)+'</urlset>')
    print(f'Built {len(urls)} localized pages, {len(ROOMS)} rooms, {len(APTS)} apartments. Source: {DATA.get("source","unknown")}')

if __name__=='__main__':
    main()
