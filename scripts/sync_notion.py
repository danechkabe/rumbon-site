#!/usr/bin/env python3
"""Build-time Notion API sync. No secrets or expiring image URLs go to the browser."""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT/'data/notion-config.json').read_text())
TOKEN = os.environ.get('NOTION_TOKEN','')
MEDIA = ROOT/'assets/media'

def request(endpoint, body=None):
    req=Request('https://api.notion.com/v1/'+endpoint,
                data=json.dumps(body).encode() if body is not None else None,
                headers={'Authorization':'Bearer '+TOKEN,'Notion-Version':'2025-09-03','Content-Type':'application/json'})
    for attempt in range(4):
        try:
            with urlopen(req,timeout=40) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code in (429,500,502,503) and attempt<3:
                time.sleep(min(int(error.headers.get('Retry-After','2')),15))
                continue
            # Never log requests, response bodies or signed URLs.
            raise RuntimeError(f'Notion API returned HTTP {error.code}; check integration access and data source IDs.') from None

def query(source_id):
    pages=[]
    cursor=None
    while True:
        body={'page_size':100,'filter':{'property':'Опубліковано','checkbox':{'equals':True}}}
        if cursor:
            body['start_cursor']=cursor
        result=request(f'data_sources/{source_id}/query',body)
        pages.extend(p for p in result['results'] if not p.get('archived') and not p.get('in_trash'))
        if not result.get('has_more'):
            return pages
        cursor=result['next_cursor']

def prop(page,name):
    value=page['properties'].get(name,{})
    kind=value.get('type')
    data=value.get(kind)
    if kind in ('title','rich_text'):
        return ''.join(t.get('plain_text',t.get('text',{}).get('content','')) for t in data or [])
    if kind in ('select','status'):
        return (data or {}).get('name')
    if kind=='date':
        return (data or {}).get('start')
    if kind=='relation':
        return [p['id'] for p in data or []]
    if kind=='files':
        return [f.get('file',f.get('external',{})).get('url') for f in data or []]
    return data

def boolean(page,name):
    value=prop(page,name)
    return True if value=='Так' else False if value=='Ні' else None

def stable_id(page):
    value=prop(page,'ID') or prop(page,'userDefined:ID') or page['id']
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',value):
        raise ValueError('ID must contain lowercase Latin letters, numbers and hyphens. See Notion instructions.')
    return value

def copy_photos(page,name):
    result=[]
    for index,url in enumerate(prop(page,name) or []):
        if not url or urlparse(url).scheme!='https':
            raise ValueError('Photo must have a valid HTTPS URL.')
        try:
            with urlopen(Request(url,headers={'User-Agent':'Rumbon-static-build/1.0'}),timeout=45) as response:
                mime=response.headers.get_content_type()
                extension={'image/jpeg':'jpg','image/png':'png','image/webp':'webp','image/avif':'avif'}.get(mime)
                if not extension:
                    raise ValueError('Photos must be JPEG, PNG, WebP or AVIF.')
                content=response.read(20*1024*1024+1)
                if len(content)>20*1024*1024:
                    raise ValueError('Photo exceeds the 20 MB limit.')
        except (HTTPError,OSError):
            raise RuntimeError('Photo download failed; previous deployment is preserved. Retry sync after checking photos in Notion.') from None
        filename=hashlib.sha256(content).hexdigest()[:24]+'.'+extension
        MEDIA.mkdir(parents=True,exist_ok=True)
        (MEDIA/filename).write_bytes(content)
        result.append('/assets/media/'+filename)
    return result

def common(page):
    return {'id':stable_id(page),'name':prop(page,'Назва'),'area':prop(page,'Район'),'address':prop(page,'Адреса'),
            'lat':prop(page,'Широта'),'lng':prop(page,'Довгота'),'floor':prop(page,'Поверх'),
            'washer':boolean(page,'Пральна машина'),'wifi':boolean(page,'Wi-Fi'),'published':True}

def sync():
    if not TOKEN:
        if os.environ.get('NOTION_SYNC_ENABLED')=='true':
            raise RuntimeError('NOTION_SYNC_ENABLED is true but NOTION_TOKEN is missing. Refusing to restore seed listings.')
        print('NOTION_TOKEN is absent: keeping initial local data. Notion sync was not performed.')
        return False
    apt_id=os.environ.get('NOTION_APARTMENTS_DATA_SOURCE_ID') or CONFIG['apartmentsDataSourceId']
    room_id=os.environ.get('NOTION_ROOMS_DATA_SOURCE_ID') or CONFIG['roomsDataSourceId']
    apt_pages=query(apt_id)
    room_pages=query(room_id)
    apartments=[]
    apt_ids={}
    for page in apt_pages:
        a=common(page)
        if not a['name'] or not a['address'] or not a['area'] or not prop(page,'Кількість кімнат'):
            print(f'Skipping incomplete apartment {page["id"]}: name, address, area and total room count required.')
            continue
        a.update({'totalRooms':prop(page,'Кількість кімнат'),'buildingFloors':prop(page,'Поверхів у будинку'),
                  'elevator':boolean(page,'Ліфт'),'balcony':boolean(page,'Балкон'),'photos':copy_photos(page,'Фото')})
        for key,field,photos in [('kitchen','Кухня','Фото кухні'),('bathroom','Ванна кімната','Фото ванної'),('shared','Спільні приміщення','Фото спільних приміщень')]:
            a[key]=prop(page,field)
            a[key+'Photos']=copy_photos(page,photos)
        if prop(page,'Інші зручності'):
            a['shared']=(a.get('shared') or '')+'\n'+prop(page,'Інші зручності')
        apartments.append(a)
        apt_ids[page['id']]=a['id']
    rooms=[]
    statuses={'Вільна зараз':'available','Вільна з дати':'available_from','Зайнята без дати':'occupied','Чернетка':'draft'}
    for page in room_pages:
        room=common(page)
        room['status']=statuses.get(prop(page,'Статус'),'draft')
        if room['status']=='draft':
            continue
        rel=prop(page,'Квартира') or []
        if len(rel)!=1 or rel[0] not in apt_ids:
            print(f'Skipping room {page["id"]}: exactly one published, complete apartment is required.')
            continue
        room['apartmentId']=apt_ids[rel[0]]
        room['title']={code:prop(page,'Заголовок '+label) for code,label in [('en','EN'),('uk','UK'),('pt','PT')]}
        room['description']={code:prop(page,'Опис '+label) for code,label in [('en','EN'),('uk','UK'),('pt','PT')]}
        room['price']=prop(page,'Ціна EUR')
        room['availableFrom']=(prop(page,'Доступна з') or '')[:10]
        if not room['title']['en'] or not room['description']['en'] or not isinstance(room['price'],(int,float)) or room['price']<=0 or not prop(page,'Фото'):
            print(f'Skipping incomplete room {page["id"]}: English title/description, price and real photos required.')
            continue
        if room['status']=='available_from':
            try:
                from datetime import date
                date.fromisoformat(room['availableFrom'])
            except ValueError:
                print(f'Skipping room {page["id"]}: availability date is required for dated status.')
                continue
        room['photos']=copy_photos(page,'Фото')
        for key,field in [('privateBathroom','Власна ванна'),('tv','Телевізор'),('ac','Кондиціонер'),('heating','Опалення'),('window','Вікно'),('wardrobe','Шафа'),('desk','Письмовий стіл'),('miniFridge','Мініхолодильник'),('furnished','Мебльована')]:
            room[key]=boolean(page,field)
        room.update({'metro':prop(page,'Метро'),'size':prop(page,'Площа'),'maxGuests':prop(page,'Максимум мешканців'),
                     'order':prop(page,'Порядок'),'bed':{'Двоярусне':'bunk','Двоспальне':'double','Односпальне':'single'}.get(prop(page,'Тип ліжка'))})
        rooms.append(room)
    output={'source':'notion','apartments':apartments,'rooms':rooms}
    target=ROOT/'data/notion.json'
    temp=target.with_suffix('.tmp')
    temp.write_text(json.dumps(output,ensure_ascii=False,indent=2))
    temp.replace(target)
    print(f'Notion synced: {len(apartments)} published apartments, {len(rooms)} complete published rooms. Drafts are excluded.')
    return True

if __name__=='__main__':
    try:
        sync()
    except Exception as error:
        print(f'Sync failed: {type(error).__name__}: {error}',file=sys.stderr)
        sys.exit(1)
