import asyncio
import json
import os
import subprocess
import time
import urllib.request
import websockets
from pathlib import Path

async def capture_studio():
    temp_dir = os.path.join(os.environ.get('TEMP', 'C:\\temp'), 'chrome_studio_verify')
    Path(temp_dir).mkdir(parents=True, exist_ok=True)
    
    proc = subprocess.Popen([
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        '--headless=new',
        '--remote-debugging-port=9225',
        '--disable-gpu',
        '--window-size=1400,900',
        f'--user-data-dir={temp_dir}',
        r'http://localhost:8766/'
    ])
    
    time.sleep(2)
    try:
        with urllib.request.urlopen('http://127.0.0.1:9225/json') as resp:
            tabs = json.loads(resp.read().decode())
        
        page_tab = next(t for t in tabs if t.get('type') == 'page')
        ws_url = page_tab['webSocketDebuggerUrl']
        print('Connecting to CDP:', ws_url)
        
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({'id': 1, 'method': 'Runtime.enable'}))
            await ws.send(json.dumps({'id': 2, 'method': 'Page.enable'}))
            
            # Wait 3 seconds for initial load
            await asyncio.sleep(3.0)
            
            # Load the latest SOTA GLB model in Three.js
            load_script = """
            (function() {
                // Find the latest job GLB
                const glbUrl = '/files/jobs/job_20261026_224446/exports/fire_spirit.glb';
                if (window.loadGLB) {
                    window.loadGLB(glbUrl, 'SOTA Fire Spirit (Sculpted)', {
                        faces: '52,012',
                        objects: '7',
                        scale: '2.85m (Z)',
                        sculpt: 'OpenVDB SOTA'
                    });
                    return 'LOADED_VIA_WINDOW_FN';
                }
                return 'WINDOW_LOADGLB_NOT_FOUND';
            })()
            """
            await ws.send(json.dumps({
                'id': 10,
                'method': 'Runtime.evaluate',
                'params': {'expression': load_script}
            }))
            
            # Wait 3 seconds for GLTF loader and Three.js rendering
            await asyncio.sleep(3.5)
            
            # Capture screenshot
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
                    img_bytes = base64.b64decode(data['result']['data'])
                    out_path = Path('Project_no2_Image_to_3d_Model/exports/sota_studio_screenshot.png')
                    out_path.write_bytes(img_bytes)
                    print(f'Screenshot saved to {out_path} ({len(img_bytes):,} bytes)')
                    break
    finally:
        proc.terminate()

if __name__ == '__main__':
    asyncio.run(capture_studio())
