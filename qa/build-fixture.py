"""Isolated QA fixtures. Never included in public dist or initial data."""
import importlib.util
import shutil
from copy import deepcopy
from pathlib import Path

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fixture_build',root/'scripts/build.py')
b=importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
b.OUT=root/'qa/fixture-dist'
b.SITE='http://127.0.0.1:4174'
b.BASE=''
if b.OUT.exists():
    shutil.rmtree(b.OUT)
b.OUT.mkdir()
shutil.copytree(root/'assets',b.OUT/'assets')
b.ROOMS=deepcopy(b.ROOMS)
for index,room in enumerate(b.ROOMS):
    room['apartmentId']='qa-apartment'
    room['title']={lang:f'TEST ONLY — Room {index+1}' for lang in b.LANGS}
    room['photos']=['/assets/share.png','/assets/share.png']
    room['incomplete']=False
b.ROOMS[2]['status']='occupied'
b.APTS={'qa-apartment':{'id':'qa-apartment','name':'TEST ONLY — Apartment','published':True,'area':'TEST FIXTURE','address':'TEST ONLY — not a listing','totalRooms':3,'lat':0,'lng':0,'photos':['/assets/share.png']}}
for lang in b.LANGS:
    b.home(lang)
    b.apartment_page(b.APTS['qa-apartment'],lang)
    for room in b.ROOMS:
        b.room_page(room,lang)
print('Created isolated QA fixture in qa/fixture-dist; no production data changed.')
