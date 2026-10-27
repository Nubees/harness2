import asyncio
import json
import os
import subprocess
import time
import urllib.request
import websockets
from pathlib import Path

async def capture_model():
    temp_dir = os.path.join(os.environ.get('TEMP', 'C:\\temp'), 'chrome_studio_verify_inflated')
    Path(temp_dir).mkdir(parents=True, exist_ok=True)
    
    proc = subprocess.Popen([
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        '--headless=new',
        '--remote-debugging-port=9226',
        '--disable-gpu',
        '--window-size=1400,900',
        f'--user-data-dir={temp_dir}',
        r'http://localhost:8766/'
    ])
    
    time.sleep(2)
    try:
        with urllib.request.urlopen('http://127.0.0.1:9226/json') as resp:
            tabs = json.loads(resp.read().decode())
        
        page_tab = next(t for t in tabs if t.get('type') == 'page')
        ws_url = page_tab['webSocketDebuggerUrl']
        print('Connecting to CDP:', ws_url)
        
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({'id': 1, 'method': 'Runtime.enable'}))
            await ws.send(json.dumps({'id': 2, 'method': 'Page.enable'}))
            await ws.send(json.dumps({'id': 3, 'method': 'Log.enable'}))
            
            await asyncio.sleep(2.0)
            
            # Load inflated model & display reference
            load_script = """
            (async function() {
                const glbUrl = '/files/exports/clean_spaceman.glb';
                console.log('Testing fetch of:', glbUrl);
                for (let i = 0; i < 50; i++) {
                    if (window.loadGLB && window.displayLoadedImage) break;
                    await new Promise(r => setTimeout(r, 200));
                }
                if (!window.loadGLB) return 'NO_LOADGLB_TIMEOUT';
                
                window.displayLoadedImage('/files/spaceman.png', 'spaceman.png');
                window.loadGLB(glbUrl, 'Teddy Silhouette Inflated (Retro Spaceman)', {
                    faces: '5,539',
                    objects: '1',
                    scale: '100% Watertight',
                    sculpt: 'Teddy/EDT + Exact Image UV'
                });
                
                const sel = document.getElementById('preset-select');
                if (sel) {
                    sel.value = 'silhouette_inflation';
                    sel.dispatchEvent(new Event('change'));
                }
                return 'LOAD_CALLED_SUCCESS';
            })()
            """
            await ws.send(json.dumps({
                'id': 10,
                'method': 'Runtime.evaluate',
                'params': {'expression': load_script, 'awaitPromise': True}
            }))
            
            # Wait 3 seconds for Three.js to render
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
                    img_data = base64.b64decode(data['result']['data'])
                    out_path = Path('Project_no2_Image_to_3d_Model/exports/studio_final_showcase.png')
                    out_path.write_bytes(img_data)
                    print(f'Saved screenshot: {out_path} ({len(img_data):,} bytes)')
                    break
    finally:
        proc.terminate()
        proc.wait(timeout=5)

if __name__ == '__main__':
    asyncio.run(capture_model())
