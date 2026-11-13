"""Verify bundled models and real recognition in a network-isolated Docker.

Usage: python scripts/test-recognition.py --sample /path/to/a/face-photo.jpg
Use a local sample with at least one clearly visible face. No screenshots.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

CHECK=r'''
import json,os,subprocess,time,urllib.request
from pathlib import Path
os.environ['API_AUTH_KEY']='nasphotos-internal'
service=subprocess.Popen(['python','vendor/mt-photos-insightface/server.py'])
try:
    for _ in range(60):
        try:
            request=urllib.request.Request('http://127.0.0.1:8066/check',data=b'',headers={'api-key':'nasphotos-internal'})
            with urllib.request.urlopen(request,timeout=2) as response:assert json.load(response)['result']=='pass'
            break
        except OSError:time.sleep(1)
    else:raise AssertionError('Recognition service did not start')
    required={'1k3d68.onnx','2d106det.onnx','det_10g.onnx','genderage.onnx','w600k_r50.onnx'}
    assert required.issubset({p.name for p in Path('/opt/insightface/models/buffalo_l').iterdir()})
    import app
    client=app.app.test_client()
    with client.session_transaction() as session:session['admin']=True
    assert client.post('/api/library',json={'paths':['/media'],'scan':True}).status_code==200
    for _ in range(60):
        state=client.get('/api/scan').json
        if not state['running']:break
        time.sleep(1)
    assert state['phase']=='complete' and state['errors']==0,state
    assert client.post('/api/recognition').status_code==200
    for _ in range(180):
        state=client.get('/api/recognition').json
        if not state['running']:break
        time.sleep(1)
    assert state['phase']=='complete' and state['errors']==0,state
    people=client.get('/api/people').json
    assert people,'No face found in the sample'
    assert all(p['count']==2 for p in people),people
    pid=people[0]['id'];assert client.get('/api/media?person='+str(pid)).json['total']==2
    assert client.patch('/api/people/'+str(pid),json={'name':'Sample person'}).status_code==200
    with client.get('/api/faces/'+str(people[0]['cover'])+'/thumb') as response:assert response.status_code==200
    with app.db() as c:
        for row in c.execute('SELECT embedding FROM people'):assert len(json.loads(row[0]))==512
    assert client.post('/api/recognition').status_code==200
    for _ in range(10):
        state=client.get('/api/recognition').json
        if not state['running']:break
        time.sleep(.1)
    assert state['processed']==0 and state['phase']=='complete',state
    print('PASS real offline buffalo_l detection, 512D embeddings, duplicate-photo grouping, person album, crop, rename and incremental skip:',len(people),'people',flush=True)
finally:
    service.terminate();service.wait(timeout=15)
'''

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--image',default='nasphotos:0.2.0');parser.add_argument('--sample',required=True);args=parser.parse_args()
    sample=Path(args.sample).resolve()
    with tempfile.TemporaryDirectory(prefix='nasphotos-face-test-',dir='/private/tmp' if Path('/private/tmp').is_dir() else None) as temp:
        root=Path(temp);(root/'photos').mkdir()
        for name in ['first','second']:shutil.copyfile(sample,root/'photos'/(name+sample.suffix))
        subprocess.run(['docker','run','--rm','--network','none','--memory','2560m','--cpus','1.5','-e','NO_ALBUMENTATIONS_UPDATE=1','-v',f'{root}/photos:/media:ro','--tmpfs','/config','--entrypoint','python',args.image,'-c',CHECK],check=True)

if __name__=='__main__':main()
