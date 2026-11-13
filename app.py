import os, sqlite3, secrets, threading, time, json, subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlsplit
from storage import data_directory
from flask import Flask, request, jsonify, session, render_template, send_file, abort
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image, ImageOps, ExifTags
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

DATA=data_directory()
ROOT=Path(os.environ.get('MEDIA_ROOT','./media')).resolve()
DATA.mkdir(parents=True,exist_ok=True)
(DATA/'thumbs').mkdir(exist_ok=True)
(DATA/'previews').mkdir(exist_ok=True)
preview_lock=threading.Lock()
secret=DATA/'secret'
if not secret.exists(): secret.write_text(secrets.token_hex(32)); secret.chmod(0o600)
app=Flask(__name__)
app.secret_key=secret.read_text()
app.config.update(MAX_CONTENT_LENGTH=1024*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax')
lock=threading.Lock()
progress={'running':False,'phase':'idle','discovered':0,'processed':0,'errors':0}
IMAGE={'.jpg','.jpeg','.png','.webp','.gif','.heic','.heif','.tif','.tiff','.bmp'}
VIDEO={'.mp4','.mov','.m4v','.webm','.mkv','.avi'}
def db():
    c=sqlite3.connect(DATA/'library.sqlite',timeout=30); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
with db() as c:
    c.executescript('''PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
    CREATE TABLE IF NOT EXISTS media(id INTEGER PRIMARY KEY,path TEXT UNIQUE,kind TEXT,date TEXT,size INTEGER,mtime REAL,width INTEGER,height INTEGER,lat REAL,lon REAL,deleted REAL,trash TEXT,missing INTEGER DEFAULT 0);
    CREATE INDEX IF NOT EXISTS media_date ON media(deleted,missing,date);
    CREATE TABLE IF NOT EXISTS shares(token TEXT PRIMARY KEY,media_id INTEGER REFERENCES media(id) ON DELETE CASCADE,expires REAL,password TEXT,download INTEGER DEFAULT 0);
    ''')
def setting(key):
    with db() as c:
        row=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone(); return row[0] if row else None

def auth(fn):
    @wraps(fn)
    def wrapped(*a,**kw):
        if not session.get('admin'): return jsonify(error='请先登录'),401
        return fn(*a,**kw)
    return wrapped

def media_roots():
    roots=[ROOT]
    # Docker may mount user media at /photos or /family_photos instead of /media.
    protected={'config','data','app','etc','dev','proc','sys','run','tmp','var','usr','bin','sbin','lib','lib64','home','root','opt','boot','mnt'}
    mounts=Path('/proc/self/mountinfo')
    if mounts.exists():
        for line in mounts.read_text().splitlines():
            fields=line.split()
            if len(fields)<6: continue
            name=fields[4].replace('\\040',' ').replace('\\011','\t').replace('\\134','\\')
            path=Path(name)
            if len(path.parts)==2 and path.name not in protected and not path.name.startswith('.') and path.is_dir() and not path.is_symlink():
                resolved=path.resolve()
                if resolved!=DATA and resolved not in roots: roots.append(resolved)
    return roots

def safe(rel,trash=False):
    p=(ROOT/rel).resolve()
    if not any(p.is_relative_to(root) for root in media_roots()): abort(403,description='目录不在已挂载的照片范围内')
    if not trash and '.nasphotos-trash' in p.parts: abort(403)
    return p

def storage_path(p):
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)

def library_paths():
    saved=setting('folders')
    if saved is not None: return json.loads(saved)
    old=setting('folder')
    return [str((ROOT/old).resolve())] if old is not None else []

def validate_paths(values):
    if not isinstance(values,list) or not values or len(values)>100: abort(400,description='请至少选择一个照片目录（最多100个）')
    paths=[]
    for value in values:
        if not isinstance(value,str): abort(400,description='目录格式不正确')
        path=safe(value)
        if not path.is_dir(): abort(400,description=f'目录不存在或未挂载：{path}')
        try: next(path.iterdir(),None)
        except PermissionError: abort(403,description=f'没有目录读取权限：{path}')
        if path not in paths: paths.append(path)
    # A parent already recursively includes its selected descendants.
    return [p for p in paths if not any(p!=q and p.is_relative_to(q) for q in paths)]

def start_scan_locked():
    progress.update(running=True,phase='discovering',processed=0,discovered=0,errors=0,message='')
    threading.Thread(target=scan,daemon=True).start()

def rowmedia(mid):
    with db() as c: row=c.execute('SELECT * FROM media WHERE id=?',(mid,)).fetchone()
    if not row: abort(404)
    return row

def gps_value(v): return float(v[0])+float(v[1])/60+float(v[2])/3600

def scan():
    try:
        progress.update(phase='discovering',processed=0,discovered=0,errors=0)
        folders=validate_paths(library_paths())
        files=[]; discovered=set()
        def walk_error(error): raise error
        for folder in folders:
            for base,dirs,names in os.walk(folder,followlinks=False,onerror=walk_error):
                dirs[:]=[d for d in dirs if not d.startswith('.') and not (Path(base)/d).is_symlink()]
                for name in names:
                    p=Path(base)/name
                    if p.suffix.lower() in IMAGE|VIDEO and not p.is_symlink() and p not in discovered:
                        discovered.add(p); files.append(p); progress['discovered']+=1
        progress['phase']='processing'
        seen=set()
        for p in files:
            try:
                rel=storage_path(p); seen.add(rel); stat=p.stat()
                with db() as c: old=c.execute('SELECT * FROM media WHERE path=?',(rel,)).fetchone()
                if old and old['deleted']: continue
                if old and old['mtime']==stat.st_mtime and old['size']==stat.st_size and (DATA/'thumbs'/f"{old['id']}.jpg").exists():
                    with db() as c: c.execute('UPDATE media SET missing=0 WHERE id=?',(old['id'],))
                    continue
                kind='video' if p.suffix.lower() in VIDEO else 'image'
                date=datetime.fromtimestamp(stat.st_mtime).isoformat(); w=h=0; lat=lon=None; thumb=None
                if kind=='image':
                    with Image.open(p) as im:
                        ex=im.getexif(); dt=ex.get(36867) or ex.get_ifd(34665).get(36867) if ex else None
                        if dt:
                            try: date=datetime.strptime(str(dt),'%Y:%m:%d %H:%M:%S').isoformat()
                            except ValueError: pass
                        try:
                            gps=ex.get_ifd(34853)
                            if gps:
                                lat=gps_value(gps[2])*(-1 if gps[1]=='S' else 1); lon=gps_value(gps[4])*(-1 if gps[3]=='W' else 1)
                        except (KeyError,TypeError,ValueError,ZeroDivisionError): pass
                        thumb=ImageOps.exif_transpose(im); w,h=thumb.size; thumb.thumbnail((640,640)); thumb=thumb.convert('RGB')
                else:
                    try:
                        result=subprocess.run(['ffprobe','-v','quiet','-show_format','-show_streams','-of','json',str(p)],capture_output=True,timeout=30)
                        meta=json.loads(result.stdout); stream=next((s for s in meta.get('streams',[]) if s.get('codec_type')=='video'),{})
                        w=stream.get('width',0); h=stream.get('height',0)
                        dt=meta.get('format',{}).get('tags',{}).get('creation_time')
                        if dt: date=datetime.fromisoformat(dt.replace('Z','+00:00')).replace(tzinfo=None).isoformat()
                    except (OSError,ValueError,subprocess.TimeoutExpired): pass
                with db() as c:
                    c.execute('''INSERT INTO media(path,kind,date,size,mtime,width,height,lat,lon) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET kind=excluded.kind,date=excluded.date,size=excluded.size,mtime=excluded.mtime,width=excluded.width,height=excluded.height,lat=excluded.lat,lon=excluded.lon,missing=0''',(rel,kind,date,stat.st_size,stat.st_mtime,w,h,lat,lon))
                    mid=c.execute('SELECT id FROM media WHERE path=?',(rel,)).fetchone()[0]
                dest=DATA/'thumbs'/f'{mid}.jpg'
                if thumb: thumb.save(dest,'JPEG',quality=82)
                else:
                    try: subprocess.run(['ffmpeg','-nostdin','-v','error','-threads','1','-y','-i',str(p),'-frames:v','1','-vf','scale=640:640:force_original_aspect_ratio=decrease',str(dest)],capture_output=True,timeout=60)
                    except (OSError,subprocess.TimeoutExpired): pass
            except Exception: progress['errors']+=1
            finally: progress['processed']+=1
        with db() as c:
            for row in c.execute('SELECT id,path FROM media WHERE deleted IS NULL').fetchall():
                if row['path'] not in seen: c.execute('UPDATE media SET missing=1 WHERE id=?',(row['id'],))
        progress.update(phase='complete',message='未发现图片或视频，请检查选择的目录以及 Docker 文件夹映射。' if not files else '')
    except Exception as e: progress.update(phase='failed',message=str(e)); app.logger.exception('扫描失败')
    finally: progress['running']=False; lock.release()

@app.get('/')
def index(): return render_template('index.html')
@app.get('/api/status')
def status(): return jsonify(setup=bool(setting('password')),authenticated=bool(session.get('admin')))
@app.post('/api/login')
def login():
    body=request.get_json() or {}; password=body.get('password','')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute("SELECT value FROM settings WHERE key='password'").fetchone()
        if not row:
            if len(password)<12: return jsonify(error='首次设置密码至少需要12位'),400
            c.execute("INSERT INTO settings VALUES('password',?)",(generate_password_hash(password),))
        elif not check_password_hash(row[0],password):
            time.sleep(1); return jsonify(error='密码错误'),401
    session.clear(); session['admin']=True; return jsonify(ok=True)
@app.post('/api/logout')
@auth
def logout(): session.clear(); return jsonify(ok=True)
@app.get('/api/roots')
@auth
def roots():
    mountfile=Path('/proc/self/mountinfo')
    mounted={line.split()[4].replace('\\040',' ').replace('\\134','\\') for line in mountfile.read_text().splitlines() if len(line.split())>5} if mountfile.exists() else set()
    return jsonify(roots=[{'path':str(p),'exists':p.is_dir(),'mounted':str(p) in mounted} for p in media_roots()])

@app.get('/api/folders')
@auth
def folders():
    p=safe(request.args.get('path',''))
    if not p.is_dir(): abort(400,description=f'目录不存在，请检查 Docker 文件夹映射：{p}')
    try:
        children=sorted((x for x in p.iterdir() if x.is_dir() and not x.name.startswith('.') and not x.is_symlink()),key=lambda x:x.name)
        media_count=sum(1 for x in p.iterdir() if x.is_file() and x.suffix.lower() in IMAGE|VIDEO)
    except PermissionError: abort(403,description=f'没有目录读取权限：{p}')
    parent=str(p.parent) if p not in media_roots() else None
    return jsonify(path=str(p),parent=parent,folders=[{'name':x.name,'path':str(x)} for x in children],media_count=media_count)

@app.route('/api/library',methods=['GET','POST'])
@auth
def library():
    if request.method=='POST':
        body=request.get_json() or {}
        values=body.get('paths') if 'paths' in body else [body.get('path','')]
        paths=validate_paths(values)
        if not lock.acquire(False): abort(409,description='扫描或文件操作正在进行，请稍后再试')
        started=False
        try:
            with db() as c:
                c.execute("INSERT OR REPLACE INTO settings VALUES('folders',?)",(json.dumps([str(p) for p in paths]),))
                c.execute("INSERT OR REPLACE INTO settings VALUES('folder',?)",(storage_path(paths[0]),))
            if body.get('scan'):
                start_scan_locked(); started=True
        finally:
            if not started: lock.release()
    return jsonify(paths=library_paths(),path=setting('folder'),root=str(ROOT),scan=progress)

@app.route('/api/scan',methods=['GET','POST'])
@auth
def scanning():
    if request.method=='POST':
        validate_paths(library_paths())
        if not lock.acquire(False): abort(409,description='扫描或文件操作正在进行，请稍后再试')
        start_scan_locked()
    return jsonify(progress)

@app.get('/api/media')
@auth
def listing():
    trash=request.args.get('trash')=='1'; offset=max(0,int(request.args.get('offset',0))); limit=min(200,max(1,int(request.args.get('limit',120))))
    where='deleted IS NOT NULL' if trash else 'deleted IS NULL AND missing=0'
    with db() as c:
        total=c.execute('SELECT count(*) FROM media WHERE '+where).fetchone()[0]
        rows=c.execute('SELECT * FROM media WHERE '+where+' ORDER BY date DESC,id DESC LIMIT ? OFFSET ?',(limit,offset)).fetchall()
    return jsonify(total=total,items=[dict(r) for r in rows])
def browser_preview(r):
    source=safe(r['path'])
    if source.suffix.lower() not in {'.heic','.heif','.tif','.tiff','.bmp'}: return source
    dest=DATA/'previews'/f"{r['id']}.jpg"
    def current(): return dest.exists() and dest.stat().st_mtime>=source.stat().st_mtime
    if current(): return dest
    if not preview_lock.acquire(timeout=15): abort(503,description='正在生成其他照片预览，请稍后重试')
    try:
        if not current():
            try:
                with Image.open(source) as image:
                    image=ImageOps.exif_transpose(image)
                    image.thumbnail((2560,2560))
                    temp=dest.with_suffix('.tmp')
                    image.convert('RGB').save(temp,'JPEG',quality=90)
                    temp.replace(dest)
            except (OSError,ValueError) as error:
                app.logger.exception('图片解码失败')
                abort(422,description='无法解码此图片，请下载原文件查看或检查文件是否损坏')
    finally: preview_lock.release()
    return dest

@app.get('/api/media/<int:mid>/<variant>')
@auth
def content(mid,variant):
    r=rowmedia(mid)
    if r['deleted'] or r['missing']: abort(404)
    if variant=='thumb':
        p=DATA/'thumbs'/f'{mid}.jpg'
        if not p.exists(): return send_file('static/video.svg',mimetype='image/svg+xml')
    elif variant=='preview': p=browser_preview(r)
    elif variant in ('original','download'): p=safe(r['path'])
    else: abort(404)
    return send_file(p,as_attachment=variant=='download',download_name=Path(r['path']).name if variant=='download' else None,conditional=True)
@app.post('/api/media/<int:mid>/trash')
@auth
def trash(mid):
    with lock:
        r=rowmedia(mid)
        if r['deleted']: return jsonify(ok=True)
        p=safe(r['path']); dest=p.parent/'.nasphotos-trash'/f'{mid}-{secrets.token_hex(8)}{p.suffix}'
        dest.parent.mkdir(exist_ok=True)
        if dest.parent.is_symlink() or not any(dest.resolve().is_relative_to(root) for root in media_roots()): abort(403)
        p.rename(dest)
        try:
            with db() as c: c.execute('UPDATE media SET deleted=?,trash=? WHERE id=?',(time.time(),storage_path(dest),mid))
        except Exception: dest.rename(p); raise
    return jsonify(ok=True)
@app.post('/api/media/<int:mid>/restore')
@auth
def restore(mid):
    with lock:
        r=rowmedia(mid)
        if not r['deleted']: abort(409)
        p=safe(r['path']); src=safe(r['trash'],trash=True)
        if p.exists(): return jsonify(error='原路径已有同名文件，无法恢复'),409
        p.parent.mkdir(parents=True,exist_ok=True); src.rename(p)
        with db() as c: c.execute('UPDATE media SET deleted=NULL,trash=NULL WHERE id=?',(mid,))
    return jsonify(ok=True)
@app.route('/api/shares',methods=['GET','POST'])
@auth
def shares():
    if request.method=='GET':
        with db() as c: return jsonify([dict(r) for r in c.execute('SELECT token,media_id,expires,download FROM shares ORDER BY expires DESC')])
    b=request.get_json() or {}; r=rowmedia(int(b['id']))
    if r['deleted'] or r['missing']: abort(404)
    token=secrets.token_urlsafe(32); days=min(365,max(1,int(b.get('days',7)))); pwd=b.get('password','')
    with db() as c: c.execute('INSERT INTO shares VALUES(?,?,?,?,?)',(token,r['id'],time.time()+days*86400,generate_password_hash(pwd) if pwd else None,int(bool(b.get('download')))))
    return jsonify(url='/s/'+token)
@app.delete('/api/shares/<token>')
@auth
def revoke(token):
    with db() as c: c.execute('DELETE FROM shares WHERE token=?',(token,))
    return jsonify(ok=True)
def shared(token):
    with db() as c: r=c.execute('SELECT s.*,m.id,m.path,m.kind,m.deleted,m.missing FROM shares s JOIN media m ON s.media_id=m.id WHERE token=?',(token,)).fetchone()
    if not r or r['expires']<time.time() or r['deleted'] or r['missing']: abort(404)
    return r
@app.route('/s/<token>',methods=['GET','POST'])
def share_page(token):
    r=shared(token)
    if request.method=='POST':
        if not r['password'] or check_password_hash(r['password'],request.form.get('password','')): session['share_'+token]=True
        else: time.sleep(1)
    allowed=not r['password'] or session.get('share_'+token)
    return render_template('share.html',token=token,allowed=allowed,kind=r['kind'],download=r['download'])
@app.get('/s/<token>/file')
def share_file(token):
    r=shared(token)
    if r['password'] and not session.get('share_'+token): abort(403)
    download=request.args.get('download')=='1'
    if download and not r['download']: abort(403)
    return send_file(safe(r['path']) if download or r['kind']=='video' else browser_preview(r),as_attachment=download,download_name=Path(r['path']).name if download else None,conditional=True)
def maintenance():
    while True:
        try:
            with lock:
                with db() as c:
                    rows=c.execute('SELECT * FROM media WHERE deleted<?',(time.time()-30*86400,)).fetchall()
                    for r in rows:
                        p=(ROOT/r['trash']).resolve()
                        if not any(p.is_relative_to(root) for root in media_roots()) or '.nasphotos-trash' not in p.parts: continue
                        p.unlink(missing_ok=True); (DATA/'thumbs'/f"{r['id']}.jpg").unlink(missing_ok=True); (DATA/'previews'/f"{r['id']}.jpg").unlink(missing_ok=True)
                        c.execute('DELETE FROM media WHERE id=?',(r['id'],))
        except Exception: app.logger.exception('回收站清理失败')
        time.sleep(3600)
threading.Thread(target=maintenance,daemon=True).start()
@app.before_request
def protect_origin():
    if request.method in ('POST','DELETE','PUT','PATCH'):
        origin=request.headers.get('Origin')
        if origin:
            parsed=urlsplit(origin)
            # HTTPS may terminate at the NAS reverse proxy; require its original Host.
            if parsed.scheme not in ('http','https') or parsed.netloc.lower() != request.host.lower(): abort(403,description='请求来源与访问地址不一致；若使用反向代理，请保留原始 Host 请求头')
@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(409)
@app.errorhandler(422)
@app.errorhandler(503)
def api_error(error):
    if request.path.startswith('/api/'):
        return jsonify(error=error.description),error.code
    return error

@app.errorhandler(PermissionError)
def permission_error(error):
    return jsonify(error='文件或目录权限不足，请检查 Docker 文件夹映射的读写权限'),403

@app.after_request
def headers(response):
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Cache-Control']='private, no-store'
    return response
if __name__=='__main__': app.run(host='0.0.0.0',port=8080,threaded=True)
