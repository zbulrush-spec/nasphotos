"""Local, incremental face indexing against the bundled InsightFace service."""
import json
import math
import threading
import urllib.request
import urllib.error
from io import BytesIO
from PIL import Image, ImageOps

class FaceLibrary:
    def __init__(self,db,data,lock,source,logger):
        self.db,self.data,self.lock,self.source,self.logger=db,data,lock,source,logger
        self.progress=dict(running=False,phase='idle',processed=0,total=0,errors=0,message='')

    def status(self):
        return dict(self.progress)

    def start(self):
        self.progress.update(running=True,phase='processing',processed=0,total=0,errors=0,message='')
        threading.Thread(target=self.run,daemon=True).start()

    def represent(self,row):
        with Image.open(self.source(row)) as image:
            image=ImageOps.exif_transpose(image).convert('RGB'); width=image.width
            image.thumbnail((2000,2000)); scale=width/image.width; output=BytesIO(); image.save(output,'JPEG',quality=92)
        boundary='nasphotos-face-upload'
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="photo.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode()+output.getvalue()+f'\r\n--{boundary}--\r\n'.encode())
        with self.db() as c: key_row=c.execute('SELECT value FROM settings WHERE key=?',('recognition_api_key',)).fetchone()
        if not key_row: raise RuntimeError('本地识别服务密钥尚未配置')
        request=urllib.request.Request('http://127.0.0.1:8066/represent',data=body,headers={'Content-Type':f'multipart/form-data; boundary={boundary}','api-key':key_row[0]})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=180) as response: result=json.load(response)
        if result.get('msg'): raise RuntimeError(result['msg'])
        for face in result['result']:
            face['box']=[float(face['facial_area'][k])*scale for k in ('x','y','w','h')]
        return result['result']

    def run(self):
        try:
            with self.db() as c:
                rows=c.execute('SELECT m.* FROM media m LEFT JOIN face_scans s ON s.media_id=m.id WHERE m.deleted IS NULL AND m.missing=0 AND m.kind=\'image\' AND (s.media_id IS NULL OR s.mtime!=m.mtime) ORDER BY m.id').fetchall()
                people=[(r['id'],json.loads(r['embedding'])) for r in c.execute('SELECT id,embedding FROM people')]
            self.progress['total']=len(rows)
            for row in rows:
                try:
                    faces=self.represent(row)
                    with self.db() as c:
                        c.execute('DELETE FROM faces WHERE media_id=?',(row['id'],))
                        for face in faces:
                            vector=face['embedding']; norm=math.sqrt(sum(v*v for v in vector))
                            if len(vector)!=512 or not norm or not all(math.isfinite(v) for v in vector): continue
                            vector=[v/norm for v in vector]
                            scores=[(sum(a*b for a,b in zip(vector,other)),pid) for pid,other in people]
                            score,pid=max(scores,default=(-1,None))
                            if score<.5:
                                pid=c.execute('INSERT INTO people(embedding) VALUES(?)',(json.dumps(vector),)).lastrowid
                                people.append((pid,vector))
                            c.execute('INSERT INTO faces(media_id,person_id,box) VALUES(?,?,?)',(row['id'],pid,json.dumps(face['box'])))
                        c.execute('INSERT OR REPLACE INTO face_scans VALUES(?,?)',(row['id'],row['mtime']))
                except Exception as error:
                    self.logger.exception('人脸识别失败：%s',row['path'])
                    self.progress.update(errors=self.progress['errors']+1,message=str(error))
                    # A missing service should fail visibly instead of timing out for every photo.
                    if isinstance(error,urllib.error.URLError): raise
                finally: self.progress['processed']+=1
            self.progress['phase']='complete'
        except Exception as error: self.progress.update(phase='failed',message=str(error))
        finally: self.progress['running']=False;self.lock.release()
