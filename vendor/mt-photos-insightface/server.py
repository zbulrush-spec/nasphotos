"""NAS Photos adapter for the vendored MT Photos InsightFace API.

Keep the upstream /check and /represent protocol, bind only to loopback, limit
CPU threads, and unload the model after five idle minutes without restarting.
"""
import asyncio
import importlib.util
import os
import threading
from pathlib import Path

spec=importlib.util.spec_from_file_location('mt_insightface_upstream',Path(__file__).with_name('upstream_server.py'))
upstream=importlib.util.module_from_spec(spec)
spec.loader.exec_module(upstream)
app=upstream.app
upstream.model_folder_path=os.environ.get('INSIGHTFACE_ROOT','/opt/insightface')
model_lock=threading.Lock()

def load_face_model():
    with model_lock:
        if upstream.face_model is None:
            import onnxruntime
            onnxruntime.disable_telemetry_events()
            options=onnxruntime.SessionOptions()
            options.intra_op_num_threads=1
            options.inter_op_num_threads=1
            root=Path(upstream.model_folder_path)
            for name in ('det_10g.onnx','w600k_r50.onnx'):
                if not (root/'models'/'buffalo_l'/name).is_file():
                    raise RuntimeError('Bundled buffalo_l model is missing; rebuild the image')
            model=upstream.FaceAnalysis(name='buffalo_l',root=str(root),providers=['CPUExecutionProvider'],allowed_modules=['detection','recognition'],sess_options=options)
            model.prepare(ctx_id=-1,det_thresh=upstream.detection_thresh,det_size=(640,640))
            upstream.face_model=model

async def release_idle_model():
    await asyncio.sleep(300)
    with model_lock:
        upstream.face_model=None
    import gc
    gc.collect()

async def predict(predict_func,inputs,model):
    loop=asyncio.get_running_loop()
    def run():
        with model_lock: return predict_func(inputs,model)
    return await loop.run_in_executor(None,run)

upstream.load_face_model=load_face_model
upstream.check_inactive=release_idle_model
upstream.predict=predict
# The upstream restart endpoint is unused and not exposed by the photo server.
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8066,access_log=False)
