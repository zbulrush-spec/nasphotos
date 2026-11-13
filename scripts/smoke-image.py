"""Run real HTTP/file lifecycle tests against a built Docker image (stdlib only)."""
import argparse
import os
import http.cookiejar
import json
import pathlib
import subprocess
import tempfile
import time
import urllib.error
import urllib.request


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config-target',choices=['/config','/data'],default='/config')
    args=parser.parse_args()
    test_image=os.environ.get('TEST_IMAGE','nasphotos:0.1.2')
    with tempfile.TemporaryDirectory(prefix='nasphotos-smoke-',dir='/private/tmp' if pathlib.Path('/private/tmp').is_dir() else None) as directory:
        root=pathlib.Path(directory)
        (root/'data').mkdir(); (root/'photos').mkdir(); (root/'extra').mkdir()
        (root/'photos'/'family').mkdir(); (root/'photos'/'travel').mkdir()
        # A tiny valid PNG without needing Pillow on the test host.
        import base64
        (root/'photos'/'sample.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aC1sAAAAASUVORK5CYII='))
        (root/'extra'/'extra.png').write_bytes((root/'photos'/'sample.png').read_bytes())
        name='nasphotos-smoke-'+root.name.split('-')[-1]
        command=['docker','run','-d','--name',name,'--memory','1536m','--cpus','1.5','-p','127.0.0.1::8080','-v',f'{root}/data:{args.config_target}','-v',f'{root}/photos:/media','-v',f'{root}/extra:/family_photos',test_image]
        subprocess.run(command,check=True)
        try:
            mapping=subprocess.check_output(['docker','port',name,'8080/tcp'],text=True).strip().splitlines()[0]
            base='http://'+mapping
            client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            def call(path,body=None,method=None):
                request=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers={'Content-Type':'application/json'})
                with client.open(request,timeout=15) as response:
                    data=response.read()
                    return json.loads(data) if 'application/json' in response.headers.get('Content-Type','') else data
            for _ in range(60):
                try: call('/api/status');break
                except (OSError,urllib.error.URLError):time.sleep(1)
            subprocess.run(['docker','exec',name,'ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=blue:s=160x120:d=1','-c:v','libx264','-pix_fmt','yuv420p','-threads','1','/media/sample.mp4'],check=True)
            assert (root/'data'/'library.sqlite').is_file()
            assert (root/'data'/'secret').is_file()
            assert (root/'data'/'thumbs').is_dir()
            assert (root/'data'/'previews').is_dir()
            assert call('/api/status')['setup'] is False
            call('/api/login',{'password':'smoke-test-password'})
            available=call('/api/roots')['roots']
            assert any(r['path']=='/family_photos' and r['mounted'] for r in available),available
            assert not any(r['path'] in ('/data','/config') for r in available),available
            call('/api/library',{'path':''})
            call('/api/scan',{},'POST')
            for _ in range(60):
                progress=call('/api/scan')
                if not progress['running']:break
                time.sleep(1)
            assert progress['phase']=='complete',progress
            assert progress['errors']==0,progress
            media=call('/api/media');assert media['total']==2,media
            mid=next(r['id'] for r in media['items'] if r['kind']=='image')
            video=next(r for r in media['items'] if r['kind']=='video')
            assert video['width']==160 and video['height']==120,video
            assert call(f"/api/media/{video['id']}/thumb")[:2]==b'\xff\xd8'
            request=urllib.request.Request(base+f"/api/media/{video['id']}/original",headers={'Range':'bytes=0-15'})
            with client.open(request) as response:
                assert response.status==206
                assert len(response.read())==16
            assert call(f'/api/media/{mid}/thumb')[:2]==b'\xff\xd8'
            link=call('/api/shares',{'id':mid,'days':1,'download':True})['url']
            with urllib.request.urlopen(base+link+'/file') as response:assert response.status==200
            call(f'/api/media/{mid}/trash',{})
            assert not (root/'photos'/'sample.png').exists()
            try:urllib.request.urlopen(base+link+'/file');raise AssertionError('Deleted share still accessible')
            except urllib.error.HTTPError as error:assert error.code==404
            call(f'/api/media/{mid}/restore',{})
            assert (root/'photos'/'sample.png').exists()
            call('/api/shares/'+link.split('/')[-1],method='DELETE')
            (root/'photos'/'sample.png').rename(root/'photos'/'family'/'sample.png')
            (root/'photos'/'sample.mp4').rename(root/'photos'/'travel'/'sample.mp4')
            subprocess.run(['docker','exec',name,'python','-c',"from PIL import Image; import pillow_heif; pillow_heif.register_heif_opener(); Image.new('RGB',(96,64),'green').save('/media/family/phone.heic',format='HEIF')"],check=True)
            paths=['/media/family','/media/travel','/family_photos']
            result=call('/api/library',{'paths':paths,'scan':True})
            assert result['paths']==paths,result
            for _ in range(60):
                progress=call('/api/scan')
                if not progress['running']:break
                time.sleep(1)
            assert progress['phase']=='complete' and progress['errors']==0,progress
            media=call('/api/media');assert media['total']==4,media
            heic=next(r for r in media['items'] if r['path'].endswith('.heic'))
            assert call(f"/api/media/{heic['id']}/preview")[:2]==b'\xff\xd8'
            original=call(f"/api/media/{heic['id']}/download")
            assert b'ftyp' in original[:16] and not original.startswith(b'\xff\xd8')
            link=call('/api/shares',{'id':heic['id'],'download':True})['url']
            with urllib.request.urlopen(base+link+'/file') as response:
                assert response.headers['Content-Type'].startswith('image/jpeg')
                assert response.read()[:2]==b'\xff\xd8'
            extra=next(r for r in media['items'] if r['path'].startswith('/family_photos/'))
            call(f"/api/media/{extra['id']}/trash",{})
            assert not (root/'extra'/'extra.png').exists()
            call(f"/api/media/{extra['id']}/restore",{})
            assert (root/'extra'/'extra.png').exists()
            subprocess.run(['docker','restart',name],check=True,stdout=subprocess.DEVNULL)
            mapping=subprocess.check_output(['docker','port',name,'8080/tcp'],text=True).strip().splitlines()[0]
            base='http://'+mapping
            for _ in range(60):
                try:
                    assert call('/api/status')['setup'] is True
                    assert call('/api/library')['paths']==paths
                    assert call('/api/media')['total']==4
                    break
                except (OSError,urllib.error.URLError):time.sleep(1)
            else:raise AssertionError('Restart persistence test timed out')
            print('PASS: Docker HTTP login, scan, thumbnail, FFmpeg video cover, video range streaming, share, trash, restore multi-directory/mount binding, HEIC JPEG preview/original download, and restart persistence')
        finally:
            subprocess.run(['docker','logs','--tail','15',name],check=False)
            subprocess.run(['docker','rm','-f',name],check=False,stdout=subprocess.DEVNULL)

if __name__=='__main__':main()
