"""Verify that the installation Compose creates and reuses config automatically."""
import http.cookiejar
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.error
import urllib.request


def main():
    image=os.environ.get('TEST_IMAGE','nasphotos:0.2.0')
    with tempfile.TemporaryDirectory(prefix='nasphotos-compose-',dir='/private/tmp' if Path('/private/tmp').exists() else None) as temp:
        root=Path(temp)
        (root/'photos').mkdir()
        content=(Path(__file__).resolve().parents[1]/'compose.yaml').read_text()
        content=content.replace('crpi-44sb4bvpcm655d55.cn-beijing.personal.cr.aliyuncs.com/zbulrush/nasphotos:latest',image).replace('"8080:8080"','"127.0.0.1::8080"')
        file=root/'compose.yaml';file.write_text(content)
        command=['docker','compose','-p','nasphotos-config-'+root.name.split('-')[-1],'-f',str(file)]
        assert not (root/'config').exists()
        client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        base=''
        def call(path,body=None):
            request=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
            with client.open(request,timeout=5) as response:return json.load(response)
        def ready():
            for _ in range(60):
                try:return call('/api/status')
                except (OSError,urllib.error.URLError):time.sleep(1)
            raise AssertionError('Container did not start')
        try:
            subprocess.run(command+['up','-d','--pull','never'],check=True)
            base='http://'+subprocess.check_output(command+['port','nasphotos','8080'],text=True).strip().splitlines()[0]
            assert ready()['setup'] is False
            config=root/'config'
            assert (config/'library.sqlite').is_file()
            assert (config/'thumbs').is_dir() and (config/'previews').is_dir()
            assert (config/'secret').is_file()
            call('/api/login',{'password':'compose-fixture-password'})
            subprocess.run(command+['up','-d','--force-recreate','--pull','never'],check=True)
            base='http://'+subprocess.check_output(command+['port','nasphotos','8080'],text=True).strip().splitlines()[0]
            status=ready()
            assert status['setup'] and status['authenticated'],status
            # A still-authenticated cookie proves the signing key survived.
            print('PASS: Compose creates config, initializes SQLite/cache, and preserves login after container recreation')
        finally:
            subprocess.run(command+['down','--volumes'],check=False)
            # Only this script's generated temporary project is mounted here.
            subprocess.run(['docker','run','--rm','--network','none','--read-only','--user','0','--entrypoint','chown','-v',f'{root}:/test-data',image,'-R',f'{os.getuid()}:{os.getgid()}','/test-data'],check=True)

if __name__=='__main__':main()
