const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Project_NO1_Image-to-3d/viewer.html', 'utf8');

console.log('=== 1. HTML & SCRIPTS EXTRACTION ===');

// Check DOCTYPE, html, head, body
const hasDoctype = /<!DOCTYPE html>/i.test(html);
const hasTitle = /<title>(.*?)<\/title>/i.test(html);
const hasCanvas = /<canvas/i.test(html) || /document\.body\.appendChild\(renderer\.domElement\)/.test(html);
console.log('DOCTYPE present:', hasDoctype);
console.log('Title present:', hasTitle, html.match(/<title>(.*?)<\/title>/i)?.[1]);

// 1. Check Importmap JSON
const importMapMatch = html.match(/<script type="importmap">([\s\S]*?)<\/script>/);
let importMapOk = false;
if (importMapMatch) {
  try {
    const im = JSON.parse(importMapMatch[1]);
    console.log('IMPORTMAP JSON valid:', true);
    console.log('  three:', im.imports?.three);
    console.log('  three/addons/:', im.imports?.['three/addons/']);
    if (im.imports?.three === 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js' &&
        im.imports?.['three/addons/'] === 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/') {
      importMapOk = true;
    }
  } catch (e) {
    console.error('IMPORTMAP JSON ERROR:', e.message);
  }
} else {
  console.error('No importmap found!');
}
console.log('Importmap Check PASS:', importMapOk);

// 2. Syntax check for scripts
const scriptRegex = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
let match;
let scriptIdx = 0;
while ((match = scriptRegex.exec(html)) !== null) {
  scriptIdx++;
  const attrs = match[1];
  const content = match[2].trim();
  const typeMatch = attrs.match(/type=["']([^"']+)["']/i);
  const srcMatch = attrs.match(/src=["']([^"']+)["']/i);
  const type = typeMatch ? typeMatch[1] : 'text/javascript';
  const src = srcMatch ? srcMatch[1] : null;

  console.log(`\nScript #${scriptIdx}: type="${type}", src="${src || 'inline'}", size=${content.length} chars`);

  if (src) {
    console.log(`  External dependency checked: ${src}`);
    continue;
  }
  if (type === 'importmap') {
    continue;
  }

  if (type === 'module') {
    fs.writeFileSync('scripts/temp_module.mjs', content);
    console.log('  Module script written to scripts/temp_module.mjs for node --check');
  } else {
    try {
      new vm.Script(content, { displayErrors: true });
      console.log('  Classic script parsed: Syntax 100% VALID!');
    } catch (e) {
      console.error('  Classic script SYNTAX ERROR:', e.message);
    }
  }
}

console.log('\n=== 2. SHADER EXTRACT & STATIC GLSL ANALYSIS ===');

// Extract all shaders defined as template strings or constants
const shaders = {};
const shaderRegex = /const\s+([A-Z0-9_]+)\s*=\s*`([\s\S]*?)`;/g;
while ((match = shaderRegex.exec(html)) !== null) {
  shaders[match[1]] = match[2];
}

// Also check inline shaders in bgQuad and pool
const bgVertMatch = html.match(/vertexShader:\s*`([\s\S]*?)`/);
const bgFragMatch = html.match(/fragmentShader:\s*`([\s\S]*?)`/);

console.log('Extracted Shaders:', Object.keys(shaders));

function analyzeGLSL(name, code, isFrag) {
  console.log(`\nAnalyzing Shader [${name}] (${isFrag ? 'FRAGMENT' : 'VERTEX'}):`);
  const uniforms = [...code.matchAll(/uniform\s+(\w+)\s+(\w+)/g)].map(m => ({ type: m[1], name: m[2] }));
  const attributes = [...code.matchAll(/attribute\s+(\w+)\s+(\w+)/g)].map(m => ({ type: m[1], name: m[2] }));
  const varyings = [...code.matchAll(/varying\s+(\w+)\s+(\w+)/g)].map(m => ({ type: m[1], name: m[2] }));
  console.log('  Uniforms:', uniforms);
  console.log('  Attributes:', attributes);
  console.log('  Varyings:', varyings);
  return { uniforms, attributes, varyings, code };
}

for (const [k, v] of Object.entries(shaders)) {
  const isFrag = k.includes('FRAG');
  analyzeGLSL(k, v, isFrag);
}

console.log('\n=== 3. MATERIAL UNIFORMS & ATTRIBUTES CROSS-CHECK ===');

// Check VERT_STD vs BODY_FRAG
// Check CAP_VERT vs CAP_FRAG
// Check FLAME_VERT vs FLAME_FRAG
// Check EMBER_VERT vs EMBER_FRAG
// Check GLOW_VERT vs GLOW_FRAG

function compareVaryings(vertName, fragName) {
  const vert = shaders[vertName];
  const frag = shaders[fragName];
  const vertVaryings = [...vert.matchAll(/varying\s+(\w+)\s+(\w+);/g)].map(m => `${m[1]} ${m[2]}`);
  const fragVaryings = [...frag.matchAll(/varying\s+(\w+)\s+(\w+);/g)].map(m => `${m[1]} ${m[2]}`);
  const match = JSON.stringify(vertVaryings.sort()) === JSON.stringify(fragVaryings.sort());
  console.log(`Varyings match between ${vertName} and ${fragName}: ${match ? 'PASS' : 'FAIL'}`);
  if (!match) {
    console.log(`  Vert: ${vertVaryings.join(', ')}`);
    console.log(`  Frag: ${fragVaryings.join(', ')}`);
  }
}

compareVaryings('VERT_STD', 'BODY_FRAG');
compareVaryings('CAP_VERT', 'CAP_FRAG');
compareVaryings('FLAME_VERT', 'FLAME_FRAG');
compareVaryings('EMBER_VERT', 'EMBER_FRAG');
compareVaryings('GLOW_VERT', 'GLOW_FRAG');

console.log('\n=== 4. AUDIT ALL SHADERMATERIAL INSTANCES ===');
const smMatches = [...html.matchAll(/new THREE\.ShaderMaterial\(\{([\s\S]*?)\n\s*\}\)/g)];
console.log('ShaderMaterial count:', smMatches.length);
smMatches.forEach((m, i) => {
  console.log(`\n--- Material #${i+1} ---`);
  const vert = m[1].match(/vertexShader:\s*([A-Za-z0-9_]+)/)?.[1];
  const frag = m[1].match(/fragmentShader:\s*([A-Za-z0-9_]+)/)?.[1];
  const uniformsMatch = m[1].match(/uniforms:\s*([A-Za-z0-9_]+|\{[\s\S]*?\})/);
  console.log('vertexShader:', vert || 'inline');
  console.log('fragmentShader:', frag || 'inline');
  console.log('uniforms:', uniformsMatch ? uniformsMatch[0].replace(/\s+/g, ' ') : 'NONE');
});


