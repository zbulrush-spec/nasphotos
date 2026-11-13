import os,tempfile,unittest,time,importlib.util
from pathlib import Path
from PIL import Image
sandbox=tempfile.TemporaryDirectory(); base=Path(sandbox.name)
os.environ['DATA_DIR']=str(base/'data'); os.environ['MEDIA_ROOT']=str(base/'photos')
(base/'photos').mkdir(); Image.new('RGB',(100,80),'red').save(base/'photos'/'test.jpg')
spec=importlib.util.spec_from_file_location('nasphotos_app',Path(__file__).parents[1]/'app.py'); app=importlib.util.module_from_spec(spec); spec.loader.exec_module(app)
class Flow(unittest.TestCase):
 def test_library_lifecycle(self):
  c=app.app.test_client()
  self.assertEqual(c.get('/api/media').status_code,401)
  self.assertEqual(c.post('/api/login',json={'password':'short'}).status_code,400)
  self.assertEqual(c.post('/api/login',json={'password':'family-test-password'}).status_code,200)
  self.assertEqual(c.get('/api/folders?path=../').status_code,403)
  self.assertEqual(c.post('/api/library',json={'path':''}).status_code,200)
  self.assertEqual(c.post('/api/scan').status_code,200)
  for _ in range(100):
   if not c.get('/api/scan').json['running']: break
   time.sleep(.03)
  self.assertEqual(c.get('/api/scan').json['phase'],'complete')
  media=c.get('/api/media').json; self.assertEqual(media['total'],1); mid=media['items'][0]['id']
  response=c.get(f'/api/media/{mid}/thumb'); self.assertEqual(response.status_code,200); response.close()
  link=c.post('/api/shares',json={'id':mid,'password':'share','download':False}).json['url']
  visitor=app.app.test_client()
  self.assertEqual(visitor.get(link+'/file').status_code,403)
  visitor.post(link,data={'password':'share'})
  response=visitor.get(link+'/file'); self.assertEqual(response.status_code,200); response.close()
  self.assertEqual(visitor.get(link+'/file?download=1').status_code,403)
  self.assertEqual(c.post(f'/api/media/{mid}/trash').status_code,200)
  self.assertFalse((base/'photos'/'test.jpg').exists())
  self.assertEqual(visitor.get(link+'/file').status_code,404)
  self.assertEqual(c.get('/api/media?trash=1').json['total'],1)
  self.assertEqual(c.post(f'/api/media/{mid}/restore').status_code,200)
  self.assertTrue((base/'photos'/'test.jpg').exists())
  token=link.split('/')[-1];c.delete('/api/shares/'+token)
  self.assertEqual(visitor.get(link).status_code,404)
  self.assertEqual(c.post('/api/scan',headers={'Origin':'https://evil.example'}).status_code,403)
  self.assertEqual(c.post('/api/logout',headers={'Origin':'https://localhost'}).status_code,200)
if __name__=='__main__': unittest.main()
