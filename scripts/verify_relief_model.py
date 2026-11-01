import asyncio
import json
import os
import subprocess
import time
import urllib.request
import websockets
from pathlib import Path

async def capture_model():
    temp_dir = os.path.join(os.environ.get('TEMP', 'C:\\temp'), 'chrome_studio_verify_relief')
    Path(temp_dir).mkdir(parents=True, exist_ok=True)
    
    proc = subprocess.Popen([
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        '--headless=new',
        '--remote-debugging-port=9227',
        '--disable-gpu',
        '--window-size=1400,900',
        f'--user-data-dir={temp_dir}',
        r'http://localhost:8766/'
    ])
    
    time.sleep(2)
    try:
        with urllib.request.urlopen('http://127.0.0.1:9227/json') as resp:
            tabs = json.loads(resp.read().decode())
        
        page_tab = next(t for t in tabs if t.get('type') == 'page')
        ws_url = page_tab['webSocketDebuggerUrl']
        print('Connecting to CDP:', ws_url)
        
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({'id': 1, 'method': 'Runtime.enable'}))
            await ws.send(json.dumps({'id': 2, 'method': 'Page.enable'}))
            
            await asyncio.sleep(2.0)
            
            load_script = """
            (function() {
                const glbUrl = '/files/exports/spaceman_relief.glb';
                if (window.loadGLB) {
                    window.loadGLB(glbUrl, '2.5D Bas-Relief Plaque (Spaceman)', {
                        faces: '22,410',
                        objects: '1',
                        scale: 'Displaced PBR',
                        sculpt: 'Contour Relief + Metallic PBR'
                    });
                    return 'LOADED_OK';
                }
                return 'LOAD_FAILED';
            })()
            """
            await ws.send(json.dumps({
                'id': 10,
                'method': 'Runtime.evaluate',
                'params': {'expression': load_script}
            }))
            
            await asyncio.sleep(3.5)
            
            await ws.send(json.dumps({
                'id': 20,
                'method': 'Page.captureScreenshot',
                'params': {'format': 'png'}
            }))
            
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                if data.get('id') == 20:
                    import base64
                    img_data = base64.b64decode(data['result']['data'])
                    out_path = Path('Project_no2_Image_to_3d_Model/exports/spaceman_relief_screenshot.png')
                    out_path.write_bytes(img_data)
                    print(f'Saved screenshot: {out_path} ({len(img_data):,} bytes)')
                    break
    finally:
        proc.terminate()
        proc.wait(timeout=5)

if __name__ == '__main__':
    asyncio.run(capture_model())
