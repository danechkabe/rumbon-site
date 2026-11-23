import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

def load(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/file)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

b=load('build','scripts/build.py')
s=load('sync','scripts/sync_notion.py')

def room(id='test-room',**fields):
    return {'id':id,'name':id,'published':True,'title':{'en':'Test room'},'price':600,'status':'available',**fields}

class SiteRules(unittest.TestCase):
    def test_publication_requires_explicit_flag_and_price(self):
        self.assertTrue(b.public_room(room()))
        for fields in ({'published':False},{'status':'draft'},{'title':{}},{'price':None},{'price':0},{'id':'../../private'}):
            self.assertFalse(b.public_room(room(**fields)))

    def test_calendar_dates_and_today(self):
        self.assertTrue(b.available(room(status='available_from',availableFrom=b.TODAY)))
        self.assertTrue(b.upcoming(room(status='available_from',availableFrom='2099-12-01')))
        for value in ('2099-99-99','2026-02-30','',None):
            r=room(status='available_from',availableFrom=value)
            self.assertFalse(b.available(r))
            self.assertFalse(b.upcoming(r))

    def test_occupied_absent_from_home_and_map(self):
        r=room(status='occupied',lat=38.7,lng=-9.1)
        with patch.object(b,'ROOMS',[r]), patch.object(b,'APTS',{}):
            self.assertEqual(b.map_groups('en'),[])
            with tempfile.TemporaryDirectory() as folder,patch.object(b,'OUT',Path(folder)):
                b.home('en')
                page=(Path(folder)/'index.html').read_text()
                self.assertNotIn('rooms/test-room/',page)

    def test_apartment_grouping_requires_relation(self):
        rooms=[room('first',lat=38.7,lng=-9.1),room('second',lat=38.7,lng=-9.1)]
        with patch.object(b,'ROOMS',rooms),patch.object(b,'APTS',{}):
            self.assertEqual(len(b.map_groups('en')),2)
        apt={'id':'apt-one','totalRooms':3,'lat':38.7,'lng':-9.1}
        related=[room('first',apartmentId='apt-one'),room('second',apartmentId='apt-one')]
        with patch.object(b,'ROOMS',related),patch.object(b,'APTS',{'apt-one':apt}):
            groups=b.map_groups('en')
            self.assertEqual(len(groups),1)
            self.assertEqual(len(groups[0]['rooms']),2)
            self.assertEqual(groups[0]['rooms'][1]['index'],2)
            self.assertEqual(groups[0]['rooms'][1]['total'],3)

    def test_no_coordinate_fabrication(self):
        with patch.object(b,'ROOMS',[room()]),patch.object(b,'APTS',{}):
            self.assertEqual(b.map_groups('en'),[])

    def test_localization_and_escaping(self):
        self.assertEqual(b.localized({'en':'English','uk':''},'uk'),'English')
        self.assertEqual(b.localized({'en':'English'},'pt'),'English')
        self.assertIn('&lt;script&gt;',b.room_card(room(title={'en':'<script>alert(1)</script>'}),'en'))
        self.assertEqual(set(b.LANGS['en']),set(b.LANGS['uk']))
        self.assertEqual(set(b.LANGS['en']),set(b.LANGS['pt']))

    def test_rejected_photos_are_not_gallery_slides(self):
        markup=b.gallery({'photos':['http://example.com/x.jpg','javascript:alert(1)']},'en')
        self.assertIn('empty-gallery',markup)
        self.assertNotIn('data-gallery-index',markup)
        self.assertNotIn('gallery-data',markup)

    def test_apartment_counts_and_grayscale(self):
        apt={'id':'apt-one','name':'Apartment One','published':True,'totalRooms':3}
        rooms=[room('first',apartmentId='apt-one'),room('second',apartmentId='apt-one'),room('third',apartmentId='apt-one',status='occupied')]
        with tempfile.TemporaryDirectory() as folder,patch.object(b,'OUT',Path(folder)),patch.object(b,'ROOMS',rooms),patch.object(b,'APTS',{'apt-one':apt}):
            b.apartment_page(apt,'en')
            page=(Path(folder)/'apartments/apt-one/index.html').read_text()
            self.assertIn('2 of 3 rooms available',page)
            self.assertIn('room-card occupied',page)
            self.assertNotIn('Ask about the whole apartment',page)
            rooms[2]['status']='available'
            b.apartment_page(apt,'en')
            page=(Path(folder)/'apartments/apt-one/index.html').read_text()
            self.assertIn('All rooms are available',page)
            self.assertIn('Ask about the whole apartment',page)

    def test_unknown_fields_are_hidden_and_false_is_explicit(self):
        markup=b.features({'privateBathroom':False,'floor':0},'en')
        self.assertIn('Private bathroom',markup)
        self.assertIn('No',markup)
        self.assertIn('<dd>0</dd>',markup)
        self.assertNotIn('Washing machine',markup)

    def test_missing_token_cannot_restore_seed_after_activation(self):
        with patch.object(s,'TOKEN',''),patch.dict(s.os.environ,{'NOTION_SYNC_ENABLED':'true'}):
            with self.assertRaises(RuntimeError):
                s.sync()

    def test_notion_pagination_and_published_filter(self):
        responses=[{'results':[{'id':'one'}],'has_more':True,'next_cursor':'next'}, {'results':[{'id':'two'},{'id':'deleted','in_trash':True}],'has_more':False}]
        with patch.object(s,'request',side_effect=responses) as request:
            self.assertEqual([p['id'] for p in s.query('test')],['one','two'])
            self.assertEqual(request.call_args_list[1].args[1]['start_cursor'],'next')
            self.assertEqual(request.call_args_list[0].args[1]['filter']['checkbox']['equals'],True)

if __name__=='__main__':
    unittest.main()
