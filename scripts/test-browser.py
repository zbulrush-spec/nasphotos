"""Exercise browser interactions without taking screenshots.

Optional test dependency: pip install playwright && playwright install chromium
Requires the application's Python dependencies and ffmpeg.
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from PIL import Image
from werkzeug.serving import make_server

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

async def exercise(base):
    from playwright.async_api import async_playwright,expect
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        page=await browser.new_page(viewport={'width':1100,'height':780})
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        await page.route('https://*.tile.openstreetmap.org/**',lambda route:route.abort())
        await page.goto(base)
        await page.locator('#password').fill('browser-test-password')
        await page.locator('#loginForm button').click()
        await expect(page.locator('.tile')).to_have_count(120)
        await page.evaluate('window.scrollTo(0,document.body.scrollHeight)')
        await expect(page.locator('.tile')).to_have_count(146)
        print('PASS automatic pagination',flush=True)
        await page.locator('#dismissScan').click();await page.wait_for_timeout(2300)
        await expect(page.locator('#progress')).to_be_hidden()
        print('PASS dismiss scan notification',flush=True)
        await page.locator('[data-view="all"]').click()
        gate=asyncio.Event()
        async def delayed_image(route):await gate.wait();await route.continue_()
        await page.route('**/api/media/*/preview',delayed_image)
        # Pick a photo rather than the newest fixture video.
        await page.locator('.tile').nth(1).click()
        await expect(page.locator('.preview-placeholder')).to_be_visible()
        assert await page.locator('.preview-placeholder').evaluate('(img)=>img.complete && img.naturalWidth>0')
        await expect(page.locator('.media-loading .spinner')).to_be_visible()
        gate.set();await expect(page.locator('.full-image')).to_be_visible()
        await expect(page.locator('.media-loading')).to_have_count(0)
        await page.locator('#closeViewer').click()
        await page.unroute('**/api/media/*/preview',delayed_image)
        print('PASS immediate existing thumbnail and decoded original replacement',flush=True)
        await page.locator('[data-view="video"]').click()
        await expect(page.locator('.tile')).to_have_count(1)
        gate=asyncio.Event()
        async def delayed_video(route):await gate.wait();await route.continue_()
        await page.route('**/api/media/*/original',delayed_video)
        await page.locator('.tile').click()
        await expect(page.locator('.media-loading progress')).to_be_visible()
        gate.set();await expect(page.locator('#mediaView video')).to_be_visible()
        await expect(page.locator('.media-loading')).to_be_hidden()
        assert await page.locator('.media-loading progress').evaluate('(bar)=>bar.value')>0
        await page.locator('#closeViewer').click()
        await expect(page.locator('#mediaView video')).to_have_count(0)
        print('PASS actual video buffering progress and cleanup',flush=True)
        await page.locator('[data-view="settings"]').click()
        await expect(page.locator('#config')).to_be_visible()
        assert await page.locator('#config').evaluate('(node)=>node.tagName')=='SECTION'
        await expect(page.locator('#scan')).to_be_visible()
        await expect(page.locator('dialog[open]')).to_have_count(0)
        await page.locator('#saveFolder').click()
        print('PASS settings page and saved library directories',flush=True)
        await page.locator('[data-view="all"]').click()
        await page.locator('.tile').nth(1).click()
        page.once('dialog',lambda dialog:dialog.accept())
        await page.locator('#delete').click()
        await expect(page.locator('#viewer')).to_be_hidden()
        await page.locator('[data-view="trash"]').click()
        await expect(page.locator('.tile')).to_have_count(1)
        await page.locator('.tile').click()
        await expect(page.locator('.full-image')).to_be_visible()
        await expect(page.locator('#restore')).to_be_visible()
        await expect(page.locator('#share')).to_be_hidden()
        await page.locator('#restore').click()
        await expect(page.locator('.tile')).to_have_count(0)
        print('PASS trash preview and restore',flush=True)
        await page.locator('[data-view="places"]').click()
        await expect(page.locator('.photo-marker').first).to_be_visible()
        zooms=[]
        for _ in range(10):
            previous=await page.evaluate('map.getZoom()');zooms.append(previous)
            await page.locator('.photo-marker').first.click(force=True)
            await page.wait_for_timeout(600)
            if await page.locator('#clearRegion').is_visible():break
            assert await page.evaluate('map.getZoom()')>previous
        else:raise AssertionError('Map did not reach a leaf region')
        assert await page.locator('.tile').count()>0
        await page.locator('#clearRegion').click();await expect(page.locator('.tile')).to_have_count(0)
        print('PASS hierarchical map clusters and regional gallery',zooms,flush=True)
        await page.locator('[data-view="people"]').click()
        await expect(page.locator('.person-card')).to_have_count(1)
        await page.locator('.person-card').click()
        await expect(page.locator('.tile')).to_have_count(1)
        page.once('dialog',lambda dialog:dialog.accept('家人'))
        await page.locator('#renamePerson').click()
        await expect(page.locator('#title')).to_have_text('家人')
        print('PASS person album and renaming',flush=True)
        assert not errors,errors
        await browser.close()

def main():
    with tempfile.TemporaryDirectory(prefix='nasphotos-browser-') as temp:
        base=Path(temp);photos=base/'photos';photos.mkdir()
        os.environ['MEDIA_ROOT']=str(photos);os.environ['DATA_DIR']=str(base/'data')
        spec=importlib.util.spec_from_file_location('browser_fixture_app',ROOT/'app.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for i in range(145):
            Image.new('RGB',(960,600),'#4488cc').save(photos/f'photo-{i}.jpg')
            with module.db() as c:
                mid=c.execute('INSERT INTO media(path,kind,date,size,mtime,width,height,lat,lon) VALUES(?,?,?,?,?,?,?,?,?)',(f'photo-{i}.jpg','image','2026-11-13',1000,1,960,600,31.23+i*.00001,121.47+i*.00001)).lastrowid
            Image.new('RGB',(120,75),'#4488cc').save(module.DATA/'thumbs'/f'{mid}.jpg')
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','color=c=blue:s=320x240:d=3','-c:v','libx264','-pix_fmt','yuv420p','-threads','1',str(photos/'test.mp4')],check=True)
        with module.db() as c:
            c.execute("INSERT INTO media(path,kind,date,size,mtime,width,height) VALUES('test.mp4','video','2026-11-14',1000,1,320,240)")
            c.execute('INSERT INTO settings VALUES(?,?)',('folders',json.dumps([str(photos)])))
            pid=c.execute('INSERT INTO people(embedding) VALUES(?)',(json.dumps([1.0]+[0.0]*511),)).lastrowid
            c.execute('INSERT INTO faces(media_id,person_id,box) VALUES(?,?,?)',(1,pid,'[10,10,100,100]'))
        module.progress.update(phase='complete',task_id='fixture',discovered=146,processed=146)
        server=make_server('127.0.0.1',0,module.app,threaded=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:asyncio.run(exercise(f'http://127.0.0.1:{server.server_port}'))
        finally:server.shutdown();thread.join();server.server_close()

if __name__=='__main__':main()
