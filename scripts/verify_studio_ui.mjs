import { spawn } from 'child_process';
import http from 'http';

function getWsUrl(port) {
  return new Promise((resolve, reject) => {
    const req = http.get(`http://127.0.0.1:${port}/json/list`, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const list = JSON.parse(data);
          const page = list.find(t => t.type === 'page') || list[0];
          resolve(page?.webSocketDebuggerUrl);
        } catch (e) { reject(e); }
      });
    });
    req.on('error', reject);
  });
}

async function run() {
  const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  const port = 9334;
  const chrome = spawn(chromePath, [
    `--remote-debugging-port=${port}`,
    '--headless=new',
    '--no-sandbox',
    '--disable-gpu',
    '--remote-allow-origins=*'
  ]);

  let wsUrl = null;
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 200));
    try {
      wsUrl = await getWsUrl(port);
      if (wsUrl) break;
    } catch {}
  }

  if (!wsUrl) {
    console.error("Failed to connect to headless Chrome");
    chrome.kill();
    process.exit(1);
  }

  const ws = new WebSocket(wsUrl);
  let id = 1;
  const callbacks = new Map();

  function send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const msgId = id++;
      callbacks.set(msgId, (err, res) => {
        if (err) reject(err); else resolve(res);
      });
      ws.send(JSON.stringify({ id: msgId, method, params }));
    });
  }

  await new Promise(r => ws.onopen = r);

  const consoleErrors = [];
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.method === 'Runtime.consoleAPICalled') {
      if (msg.params.type === 'error') {
        consoleErrors.push(msg.params.args.map(a => a.value || a.description).join(' '));
      }
    }
    if (msg.method === 'Runtime.exceptionThrown') {
      consoleErrors.push(msg.params.exceptionDetails.text + ' ' + (msg.params.exceptionDetails.exception?.description || ''));
    }
    if (msg.id && callbacks.has(msg.id)) {
      const cb = callbacks.get(msg.id);
      callbacks.delete(msg.id);
      if (msg.error) cb(msg.error); else cb(null, msg.result);
    }
  };

  await send('Page.enable');
  await send('Runtime.enable');

  console.log("Navigating to http://localhost:8766/...");
  await send('Page.navigate', { url: 'http://localhost:8766/' });
  await new Promise(r => setTimeout(r, 2500));

  async function evaluate(expr) {
    const res = await send('Runtime.evaluate', { expression: expr, returnByValue: true });
    return res.result?.value;
  }

  console.log("\n--- Checking Initial UI State ---");
  const initialState = await evaluate(`(() => {
    const dropzone = document.getElementById('dropzone');
    const previewCard = document.getElementById('image-preview-card');
    const previewImg = document.getElementById('image-preview');
    const assetName = document.getElementById('asset-name')?.textContent;
    const metricFaces = document.getElementById('metric-faces')?.textContent;
    const pip = document.getElementById('viewport-ref-pip');

    return {
      dropzoneHidden: dropzone?.classList.contains('hidden'),
      cardHidden: previewCard?.classList.contains('hidden'),
      assetName,
      metricFaces,
      pipHidden: pip?.classList.contains('hidden')
    };
  })()`);
  console.log("Initial state:", JSON.stringify(initialState, null, 2));

  console.log("\n--- Testing SpaceMan Sample Button Click ---");
  await evaluate(`document.getElementById('load-spaceman-btn').click()`);
  await new Promise(r => setTimeout(r, 1000));

  const afterSampleState = await evaluate(`(() => {
    const card = document.getElementById('image-preview-card');
    const img = document.getElementById('image-preview');
    const filename = document.getElementById('preview-filename')?.textContent;
    const pip = document.getElementById('viewport-ref-pip');
    const pipImg = document.getElementById('viewport-ref-img');
    const assetName = document.getElementById('asset-name')?.textContent;

    const imgRect = img?.getBoundingClientRect();
    const cardRect = card?.getBoundingClientRect();

    return {
      cardHidden: card?.classList.contains('hidden'),
      filename,
      imgSrc: img?.src,
      imgWidth: imgRect?.width,
      imgHeight: imgRect?.height,
      cardWidth: cardRect?.width,
      cardHeight: cardRect?.height,
      pipHidden: pip?.classList.contains('hidden'),
      pipImgSrc: pipImg?.src,
      assetName
    };
  })()`);
  console.log("After Sample Click:", JSON.stringify(afterSampleState, null, 2));

  console.log("\n--- Testing 'New Model' Button Click ---");
  await evaluate(`document.getElementById('btn-new-model').click()`);
  await new Promise(r => setTimeout(r, 500));

  const afterNewModelState = await evaluate(`(() => {
    const dropzone = document.getElementById('dropzone');
    const card = document.getElementById('image-preview-card');
    const img = document.getElementById('image-preview');
    const pip = document.getElementById('viewport-ref-pip');
    const assetName = document.getElementById('asset-name')?.textContent;
    const promptVal = document.getElementById('prompt-input')?.value;

    return {
      dropzoneHidden: dropzone?.classList.contains('hidden'),
      cardHidden: card?.classList.contains('hidden'),
      imgSrc: img?.src,
      pipHidden: pip?.classList.contains('hidden'),
      assetName,
      promptVal
    };
  })()`);
  console.log("After New Model Click:", JSON.stringify(afterNewModelState, null, 2));

  console.log("\n--- Testing Custom File Upload (Mock Data URL via displayLoadedImage) ---");
  const testDataUrl = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
  await evaluate(`displayLoadedImage("${testDataUrl}", "my_alien.png")`);
  await new Promise(r => setTimeout(r, 500));

  const afterCustomState = await evaluate(`(() => {
    const card = document.getElementById('image-preview-card');
    const img = document.getElementById('image-preview');
    const filename = document.getElementById('preview-filename')?.textContent;
    const pip = document.getElementById('viewport-ref-pip');
    const pipImg = document.getElementById('viewport-ref-img');

    const imgRect = img?.getBoundingClientRect();
    const cardRect = card?.getBoundingClientRect();

    return {
      cardHidden: card?.classList.contains('hidden'),
      filename,
      imgSrcLength: img?.src?.length,
      imgWidth: imgRect?.width,
      imgHeight: imgRect?.height,
      cardWidth: cardRect?.width,
      cardHeight: cardRect?.height,
      pipHidden: pip?.classList.contains('hidden'),
      pipImgSrcLength: pipImg?.src?.length
    };
  })()`);
  console.log("After Custom Image Display:", JSON.stringify(afterCustomState, null, 2));

  console.log("\n--- Testing Real File Dispatch via handleSelectedFile ---");
  await evaluate(`(async () => {
    // 1x1 base64 transparent PNG
    const b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
    const byteChars = atob(b64);
    const byteNums = new Array(byteChars.length);
    for (let i = 0; i < byteChars.length; i++) byteNums[i] = byteChars.charCodeAt(i);
    const byteArray = new Uint8Array(byteNums);
    const file = new File([byteArray], "real_drop_alien.png", { type: "image/png" });
    window.handleSelectedFile(file);
  })()`);
  await new Promise(r => setTimeout(r, 1200));

  const afterRealFileState = await evaluate(`(() => {
    const card = document.getElementById('image-preview-card');
    const img = document.getElementById('image-preview');
    const filename = document.getElementById('preview-filename')?.textContent;
    const pip = document.getElementById('viewport-ref-pip');
    const dropzone = document.getElementById('dropzone');
    const imgRect = img?.getBoundingClientRect();

    return {
      dropzoneHidden: dropzone?.classList.contains('hidden'),
      cardHidden: card?.classList.contains('hidden'),
      filename,
      imgWidth: imgRect?.width,
      imgHeight: imgRect?.height,
      pipHidden: pip?.classList.contains('hidden')
    };
  })()`);
  console.log("After Real File Dispatch:", JSON.stringify(afterRealFileState, null, 2));

  console.log("\n--- Console Errors Encountered ---");
  console.log(consoleErrors.length === 0 ? "No JS errors!" : consoleErrors);

  ws.close();
  chrome.kill();

  if (consoleErrors.length > 0) {
    process.exit(1);
  }
}

run().catch(err => {
  console.error("Test failed:", err);
  process.exit(1);
});
