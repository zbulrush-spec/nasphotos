import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PIL import Image

class BrowsingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        photos=self.root/'photos';photos.mkdir()
        os.environ['MEDIA_ROOT']=str(photos);os.environ['DATA_DIR']=str(self.root/'data')
        spec=importlib.util.spec_from_file_location('browsing_app',Path(__file__).parents[1]/'app.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.client=self.module.app.test_client()
        with self.client.session_transaction() as session:session['admin']=True
        for i,(lat,lon) in enumerate([(31.2304,121.4737),(31.2305,121.4738),(39.9042,116.4074),(None,None)]):
            Image.new('RGB',(80,60),'red').save(photos/f'{i}.jpg')
            with self.module.db() as c:
                c.execute('INSERT INTO media(path,kind,date,size,mtime,width,height,lat,lon) VALUES(?,?,?,?,?,?,?,?,?)',(f'{i}.jpg','image',f'2026-01-0{i+1}',100,1,80,60,lat,lon))
            Image.new('RGB',(40,30),'red').save(self.module.DATA/'thumbs'/f'{i+1}.jpg')
    def tearDown(self):self.temp.cleanup()
    def test_server_side_filters_and_pagination(self):
        self.assertEqual(self.client.get('/api/media?limit=2').json['total'],4)
        self.assertEqual(len(self.client.get('/api/media?limit=2&offset=2').json['items']),2)
        self.assertEqual(self.client.get('/api/media?kind=video').json['total'],0)
        self.assertEqual(self.client.get('/api/media?bounds=31,121,32,122').json['total'],2)
        for query in ['bounds=nan,1,2,3','bounds=0,0,1','bounds=5,1,2,3','offset=bad']:
            self.assertEqual(self.client.get('/api/media?'+query).status_code,400)
    def test_map_clusters_split_and_leaf_filters_match(self):
        broad=self.client.get('/api/places?zoom=0').json
        self.assertEqual(broad['total'],3);self.assertEqual(len(broad['clusters']),1)
        detailed=self.client.get('/api/places?zoom=18').json
        self.assertGreater(len(detailed['clusters']),1)
        self.assertEqual(sum(g['count'] for g in detailed['clusters']),3)
        for group in detailed['clusters']:
            self.assertTrue(group['leaf'])
            bounds=','.join(str(v) for v in group['bounds'])
            self.assertEqual(self.client.get('/api/media?bounds='+bounds).json['total'],group['count'])
        visible=self.client.get('/api/places?zoom=18&bounds=31,121,32,122').json
        self.assertEqual(visible['total'],3);self.assertEqual(sum(g['count'] for g in visible['clusters']),2)
        self.client.post('/api/media/1/trash')
        self.assertEqual(self.client.get('/api/places').json['total'],2)
    def test_trash_preview_download_range_and_deletion_sort(self):
        self.client.post('/api/media/4/trash');time.sleep(.01);self.client.post('/api/media/1/trash')
        items=self.client.get('/api/media?trash=1').json['items']
        self.assertEqual([r['id'] for r in items],[1,4])
        for variant in ['thumb','preview','original','download']:
            with self.client.get('/api/media/1/'+variant) as response:self.assertEqual(response.status_code,200)
        with self.client.get('/api/media/1/original',headers={'Range':'bytes=0-15'}) as response:
            self.assertEqual(response.status_code,206);self.assertEqual(len(response.data),16)
        self.assertEqual(self.client.post('/api/shares',json={'id':1}).status_code,404)
        self.assertEqual(self.module.app.test_client().get('/api/media/1/preview').status_code,401)
        self.assertEqual(self.client.post('/api/media/1/restore').status_code,200)
        with self.client.get('/api/media/1/preview') as response:self.assertEqual(response.status_code,200)
    def test_recognition_groups_people_incrementally_and_hides_deleted(self):
        vector=[1.0]+[0.0]*511
        def represent(row):return [{'embedding':vector,'box':[10,10,20,20]}]
        library=self.module.face_library
        with patch.object(library,'represent',side_effect=represent) as infer:
            self.module.lock.acquire();library.run()
            self.assertEqual(library.status()['errors'],0);self.assertEqual(infer.call_count,4)
            self.module.lock.acquire();library.run();self.assertEqual(infer.call_count,4)
        people=self.client.get('/api/people').json;self.assertEqual(len(people),1);self.assertEqual(people[0]['count'],4)
        pid=people[0]['id']
        self.assertEqual(self.client.patch(f'/api/people/{pid}',json={'name':'家人'}).status_code,200)
        self.assertEqual(self.client.get('/api/people').json[0]['name'],'家人')
        self.assertEqual(self.client.get(f'/api/media?person={pid}').json['total'],4)
        with self.client.get(f"/api/faces/{people[0]['cover']}/thumb") as response:self.assertEqual(response.status_code,200)
        self.client.post('/api/media/1/trash')
        self.assertEqual(self.client.get(f'/api/media?person={pid}').json['total'],3)
        self.assertEqual(self.client.get(f"/api/faces/{people[0]['cover']}/thumb").status_code,404)
        self.module.lock.acquire()
        try:self.assertEqual(self.client.post('/api/recognition').status_code,409)
        finally:self.module.lock.release()

if __name__=='__main__':unittest.main()
