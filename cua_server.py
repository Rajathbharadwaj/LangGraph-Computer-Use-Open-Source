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

class ScrollRequest(BaseModel):
    x: int
    y: int
    scroll_x: int = 0
    scroll_y: int = 3

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

@app.post('/scroll')
async def scroll(req: ScrollRequest):
    # Move mouse to target location first
    move_ok, _ = run_cmd(f'xdotool mousemove {req.x} {req.y}')
    if not move_ok:
        return {'success': False, 'message': 'Failed to move mouse'}
    
    # Use xdotool mouse wheel events for scrolling
    scroll_commands = []
    
    # Handle vertical scrolling (most common for feeds)
    if req.scroll_y > 0:  # Scroll down
        for _ in range(abs(req.scroll_y)):
            scroll_commands.append('xdotool click 5')  # Mouse wheel down
    elif req.scroll_y < 0:  # Scroll up
        for _ in range(abs(req.scroll_y)):
            scroll_commands.append('xdotool click 4')  # Mouse wheel up
    
    # Handle horizontal scrolling if needed
    if req.scroll_x > 0:  # Scroll right
        for _ in range(abs(req.scroll_x)):
            scroll_commands.append('xdotool click 7')  # Mouse wheel right
    elif req.scroll_x < 0:  # Scroll left
        for _ in range(abs(req.scroll_x)):
            scroll_commands.append('xdotool click 6')  # Mouse wheel left
    
    # Execute scroll commands with small delays
    for cmd in scroll_commands:
        ok, out = run_cmd(cmd)
        if not ok:
            return {'success': False, 'message': f'Scroll command failed: {out}'}
        # Small delay between scroll events for better compatibility
        run_cmd('sleep 0.1')
    
    return {'success': True, 'message': f'Scrolled at ({req.x}, {req.y}): x={req.scroll_x}, y={req.scroll_y}'}

@app.get('/dimensions')
async def dimensions():
    return {'width': 1280, 'height': 720}

if __name__ == '__main__':
    print("Starting CUA server...")
    uvicorn.run(app, host='0.0.0.0', port=8001)
