import importlib.util
import os
import tempfile
import time
import unittest
from pathlib import Path
from PIL import Image

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name).resolve()
        self.photos=self.root/'photos'; self.photos.mkdir()
        os.environ['DATA_DIR']=str(self.root/'data'); os.environ['MEDIA_ROOT']=str(self.photos)
        spec=importlib.util.spec_from_file_location('library_under_test',Path(__file__).parents[1]/'app.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.client=self.module.app.test_client()
        with self.client.session_transaction() as session:session['admin']=True
    def tearDown(self):self.temp.cleanup()
    def wait_scan(self):
        for _ in range(200):
            status=self.client.get('/api/scan').json
            if not status['running']:return status
            time.sleep(.01)
        self.fail('Scan did not finish')
    def test_empty_directory_and_clear_errors(self):
        result=self.client.get('/api/folders').json
        self.assertEqual(result['path'],str(self.photos));self.assertIsNone(result['parent'])
        self.assertEqual(result['folders'],[]);self.assertEqual(result['media_count'],0)
        result=self.client.post('/api/library',json={'paths':[],'scan':True})
        self.assertEqual(result.status_code,400);self.assertIn('至少选择',result.json['error'])
        result=self.client.post('/api/library',json={'paths':['/etc']})
        self.assertEqual(result.status_code,403);self.assertIn('挂载',result.json['error'])
        result=self.client.post('/api/library',json={'paths':[str(self.photos)],'scan':True})
        self.assertEqual(result.status_code,200)
        self.assertIn('未发现',self.wait_scan()['message'])
    def test_multi_directory_selection_and_overlap(self):
        for name in ['family','travel','family/nested','excluded']:(self.photos/name).mkdir(parents=True,exist_ok=True)
        for name in ['family/nested/a.jpg','travel/b.jpg','excluded/c.jpg']:Image.new('RGB',(12,12),'red').save(self.photos/name)
        self.assertEqual(self.client.post('/api/library',json={'paths':['family','family/nested','travel','travel'],'scan':True}).status_code,200)
        self.assertEqual(self.wait_scan()['phase'],'complete')
        paths=self.client.get('/api/library').json['paths'];self.assertEqual(len(paths),2)
        self.assertEqual(self.client.get('/api/media').json['total'],2)
        self.client.post('/api/library',json={'paths':['travel'],'scan':True});self.wait_scan()
        self.assertEqual(self.client.get('/api/media').json['total'],1)
        self.module.lock.acquire()
        try:self.assertEqual(self.client.post('/api/library',json={'paths':['family']}).status_code,409)
        finally:self.module.lock.release()
        self.assertEqual(self.client.get('/api/library').json['paths'],[str(self.photos/'travel')])
    def test_old_single_directory_migration(self):
        with self.module.db() as connection:connection.execute("INSERT INTO settings VALUES('folder','.')")
        self.assertEqual(self.client.get('/api/library').json['paths'],[str(self.photos)])
    def test_actual_heic_preview_original_and_share(self):
        import pillow_heif
        pillow_heif.register_heif_opener()
        source=self.photos/'phone.heic'
        Image.new('RGB',(96,64),'red').save(source,format='HEIF')
        original=source.read_bytes()
        self.client.post('/api/library',json={'paths':[str(self.photos)],'scan':True})
        self.assertEqual(self.wait_scan()['errors'],0)
        mid=self.client.get('/api/media').json['items'][0]['id']
        preview=self.client.get(f'/api/media/{mid}/preview')
        self.assertEqual(preview.status_code,200);self.assertEqual(preview.mimetype,'image/jpeg')
        self.assertTrue(preview.data.startswith(b'\xff\xd8'));preview.close()
        download=self.client.get(f'/api/media/{mid}/download')
        self.assertEqual(download.data,original);download.close()
        link=self.client.post('/api/shares',json={'id':mid,'download':True}).json['url']
        visitor=self.module.app.test_client();shared=visitor.get(link+'/file')
        self.assertEqual(shared.mimetype,'image/jpeg');shared.close()
        shared=visitor.get(link+'/file?download=1');self.assertEqual(shared.data,original);shared.close()
        self.assertEqual(source.read_bytes(),original)
        old=(self.root/'data'/'previews'/f'{mid}.jpg').read_bytes()
        time.sleep(.02);Image.new('RGB',(96,64),'blue').save(source,format='HEIF')
        preview=self.client.get(f'/api/media/{mid}/preview')
        self.assertNotEqual(preview.data,old);preview.close()

if __name__=='__main__':unittest.main()
