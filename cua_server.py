#!/usr/bin/env python3
import os
import subprocess
import base64
import shlex
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

os.environ['DISPLAY'] = ':98'
app = FastAPI(title='CUA Server')

class ClickRequest(BaseModel):
    x: int
    y: int

class MoveRequest(BaseModel):
    x: int
    y: int

class TypeRequest(BaseModel):
    text: str

class KeyPressRequest(BaseModel):
    keys: list

def run_cmd(cmd: str):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)

@app.get('/health')
async def health():
    ok, _ = run_cmd('xdpyinfo >/dev/null 2>&1')
    return {'status': 'healthy' if ok else 'degraded', 'display': os.environ.get('DISPLAY')}

@app.get('/screenshot')
async def screenshot():
    import time
    timestamp = int(time.time() * 1000)  # millisecond precision
    filename = f'/tmp/shot_{timestamp}.png'
    
    ok, _ = run_cmd(f'scrot {filename}')
    if ok:
        try:
            with open(filename, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode()
            # Clean up the file
            run_cmd(f'rm {filename}')
            return {'success': True, 'image': f'data:image/png;base64,{b64}'}
        except:
            pass
    return {'success': False}

@app.post('/move')
async def move(req: MoveRequest):
    ok, out = run_cmd(f'xdotool mousemove {req.x} {req.y}')
    return {'success': ok, 'message': out}

@app.post('/click')
async def click(req: ClickRequest):
    ok, out = run_cmd(f'xdotool mousemove {req.x} {req.y} click 1')
    return {'success': ok, 'message': out}

@app.post('/type')
async def type_text(req: TypeRequest):
    quoted = shlex.quote(req.text)
    cmd = f"xdotool type --clearmodifiers -- {quoted}"
    ok, out = run_cmd(cmd)
    return {'success': ok, 'message': out}

@app.post('/key_press')
async def key_press(req: KeyPressRequest):
    key_string = '+'.join(req.keys)
    cmd = f'xdotool key {key_string}'
    ok, out = run_cmd(cmd)
    return {'success': ok, 'message': out}

@app.get('/dimensions')
async def dimensions():
    return {'width': 1280, 'height': 720}

if __name__ == '__main__':
    print("Starting CUA server...")
    uvicorn.run(app, host='0.0.0.0', port=8001)
