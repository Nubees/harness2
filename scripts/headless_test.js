const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const server = http.createServer((req, res) => {
  let reqPath = req.url.split('?')[0];
  if (reqPath === '/') reqPath = '/Project_NO1_Image-to-3d/viewer.html';
  const filePath = path.join(process.cwd(), reqPath.replace(/^\//, ''));
  if (fs.existsSync(filePath)) {
    const ext = path.extname(filePath);
    const contentTypes = {
      '.html': 'text/html',
      '.js': 'application/javascript',
      '.css': 'text/css',
      '.png': 'image/png',
      '.json': 'application/json'
    };
    res.writeHead(200, { 'Content-Type': contentTypes[ext] || 'text/plain' });
    fs.createReadStream(filePath).pipe(res);
  } else {
    console.log('404 on:', reqPath);
    res.writeHead(404);
    res.end('Not found');
  }
});

server.listen(8999, async () => {
  console.log('HTTP server listening on 8999');

  const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  const args = [
    '--headless=new',
    '--remote-debugging-port=9223',
    '--user-data-dir=C:\\Users\\User101\\AppData\\Local\\Temp\\chrome_test_profile',
    '--disable-extensions',
    '--enable-unsafe-swiftshader',
    '--use-gl=angle',
    '--use-angle=swiftshader',
    '--no-sandbox',
    '--disable-gpu-sandbox',
    'http://localhost:8999/Project_NO1_Image-to-3d/viewer.html'
  ];

  console.log('Spawning Chrome...');
  const chrome = spawn(chromePath, args);

  // Wait for CDP to be available
  let cdpUrl = null;
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 500));
    try {
      const resp = await fetch('http://localhost:9223/json/list');
      const list = await resp.json();
      const pageTarget = list.find(t => t.type === 'page' && t.url.includes('viewer.html'));
      if (pageTarget) {
        cdpUrl = pageTarget.webSocketDebuggerUrl;
        console.log('CDP target found:', pageTarget.title, pageTarget.url);
        break;
      }
    } catch (e) {}
  }

  if (!cdpUrl) {
    console.error('Failed to connect to Chrome CDP endpoint');
    chrome.kill();
    server.close();
    process.exit(1);
  }

  const ws = new WebSocket(cdpUrl);
  const consoleMessages = [];
  const errors = [];

  ws.onopen = () => {
    console.log('Connected to CDP WebSocket');
    ws.send(JSON.stringify({ id: 1, method: 'Runtime.enable' }));
    ws.send(JSON.stringify({ id: 2, method: 'Log.enable' }));
    ws.send(JSON.stringify({ id: 3, method: 'Page.enable' }));
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.method === 'Runtime.consoleAPICalled') {
      const argsText = msg.params.args.map(a => a.value || a.description || JSON.stringify(a)).join(' ');
      console.log(`[Browser Console ${msg.params.type}]:`, argsText);
      consoleMessages.push({ type: msg.params.type, text: argsText });
    }
    if (msg.method === 'Runtime.exceptionThrown') {
      console.error('[Browser Exception]:', msg.params.exceptionDetails);
      errors.push(msg.params.exceptionDetails);
    }
    if (msg.method === 'Log.entryAdded') {
      if (msg.params.entry.level === 'error') {
        console.log('[Browser Log Error]:', msg.params.entry.text);
      }
    }
  };

  // Give the page 6 seconds to run several animation frames
  setTimeout(async () => {
    // Check window.__BLAZE_BOOTED
    ws.send(JSON.stringify({
      id: 10,
      method: 'Runtime.evaluate',
      params: { expression: '({ booted: window.__BLAZE_BOOTED, failed: window.__BLAZE_FAILED, canvasCount: document.querySelectorAll("canvas").length, title: document.title })', returnByValue: true }
    }));
  }, 4000);

  // Read response
  const originalOnMessage = ws.onmessage;
  ws.onmessage = (event) => {
    originalOnMessage(event);
    const msg = JSON.parse(event.data);
    if (msg.id === 10) {
      console.log('\n--- BLAZE BROWSER EVAL RESULT ---');
      console.log(msg.result.result.value);
      console.log('Total Console Messages:', consoleMessages.length);
      console.log('Total Exceptions:', errors.length);

      // Capture screenshot
      ws.send(JSON.stringify({ id: 11, method: 'Page.captureScreenshot' }));
    }
    if (msg.id === 11) {
      if (msg.result && msg.result.data) {
        fs.writeFileSync('Project_NO1_Image-to-3d/render_screenshot.png', Buffer.from(msg.result.data, 'base64'));
        console.log('Screenshot saved to Project_NO1_Image-to-3d/render_screenshot.png');
      }
      ws.close();
      chrome.kill();
      server.close();
      process.exit(errors.length === 0 ? 0 : 1);
    }
  };
});
