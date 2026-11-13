"""Run both local services; stop the container if either process exits."""
import os
import signal
import subprocess
import sys
import time

processes=[]
stopping=False

def stop(signum=None,frame=None):
    global stopping
    stopping=True
    for process in processes:
        if process.poll() is None: process.terminate()

signal.signal(signal.SIGTERM,stop)
signal.signal(signal.SIGINT,stop)
env=dict(os.environ,RECOGNITION_MODEL='buffalo_l',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',NO_ALBUMENTATIONS_UPDATE='1')
try:
    processes.append(subprocess.Popen([sys.executable,'vendor/mt-photos-insightface/server.py'],env=env))
    processes.append(subprocess.Popen(['gunicorn','--bind','0.0.0.0:8080','--workers','1','--threads','4','--timeout','120','app:app'],env=env))
    while not stopping and all(p.poll() is None for p in processes): time.sleep(.25)
    code=0 if stopping else next((p.returncode or 1 for p in processes if p.poll() is not None),1)
finally:
    stop()
    deadline=time.monotonic()+15
    for process in processes:
        try:process.wait(timeout=max(.1,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:process.kill();process.wait()
sys.exit(code)
