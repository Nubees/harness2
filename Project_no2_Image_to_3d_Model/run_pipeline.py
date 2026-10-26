"""Omni-3D Pipeline Runner for Project #2 (SpaceMan).

Integrates Harness² with Ollama GLM-5.3 to synthesize a Blender Python (bpy)
modeling script following the LL3M methodology, executes it headlessly via
Blender 5.2 LTS, and exports into GLB, OBJ, STL, and FBX with an interactive viewer.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT_DIR = ROOT / "Project_no2_Image_to_3d_Model"
IMAGE_PATH = PROJECT_DIR / "spaceman.png"
SCRIPT_PATH = PROJECT_DIR / "generate_spaceman.py"
EXPORTS_DIR = PROJECT_DIR / "exports"
VIEWER_PATH = PROJECT_DIR / "index.html"
BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


TASK_PROMPT = """You are an elite 3D technical artist, Blender Python (bpy) specialist, and spatial engineer following the LL3M (Large Language 3D Modelers) methodology.

TASK:
Analyze the reference image (spaceman.png) — an iconic retro sci-fi cartoon alien astronaut wearing an orange spacesuit with a cyan helmet and glass visor showing a green alien head inside — and write a complete, standalone, production-ready Blender Python script (generate_spaceman.py) that procedurally builds this 3D model and exports it into ALL FOUR target formats: GLB, OBJ, STL, and FBX.

CHARACTER ANATOMY & GEOMETRIC DECOMPOSITION:
1. HEAD & HELMET:
   - Outer Helmet: Spherical metallic teal/cyan helmet (approx radius 0.65m), open circular front face with collar ring.
   - Glass Visor: Clear, glossy translucent dome (approx radius 0.60m) covering the front opening.
   - Antenna: Mounted vertically on top of helmet (cylinder stalk) with a spherical red/orange beacon tip.
   - Ear Pods: Cylindrical communication ports on the left and right sides of the helmet with bevels.
   - Alien Head (Inside Visor): Classic green extraterrestrial head (approx radius 0.40m, elongated skull) with two large black almond-shaped glossy eyes, subtle brow ridges, and frowning mouth.

2. TORSO & LIFE SUPPORT:
   - Spacesuit Body: Padded, segmented retro orange jumpsuit (torso height ~0.85m, width ~0.70m, depth ~0.50m) with smooth beveled edges.
   - Chest Control Pack: Rectangular console mounted on chest with status screen, dials, and indicator buttons.
   - Breathing Hoses: Two corrugated curved tubes routing from the chest unit around the sides to the backpack.
   - Backpack Life-Support: Rectangular canister unit on the astronaut's back with vents.
   - Harness & Utility Belt: Cyan straps running over shoulders and a thick cyan waist belt with a rectangular center buckle.

3. ARMS, GLOVES, LEGS & BOOTS:
   - Arms: Segmented cylindrical orange sleeves angled naturally at the sides, cyan shoulder pads.
   - Gloves: Chunky cyan astronaut mittens/gloves with distinct thumbs.
   - Legs & Kneepads: Sturdy cylindrical orange legs with cyan protective knee patches.
   - Boots: Heavy cyan astronaut space boots with pronounced soles and toe caps.

4. MATERIALS (Principled BSDF):
   - Orange Suit: Base Color #E85D26, Roughness 0.55
   - Cyan Trim / Helmet / Boots: Base Color #38A3C2, Metallic 0.35, Roughness 0.30
   - Green Alien Skin: Base Color #7CB534, Roughness 0.45, Subsurface 0.15
   - Glossy Black Eyes: Base Color #0D0D0D, Roughness 0.08
   - Translucent Visor: Base Color #88C8D8, Alpha 0.35 (or Transmission 0.85), Roughness 0.1
   - Console & Details: Dark slate #243342, Red #E03B24, Yellow #F5C518

5. MULTI-FORMAT EXPORTING REQUIREMENTS (Blender 5.2):
   At the end of the script, resolve the exports folder relative to the script and export all 4 formats:
   ```python
   from pathlib import Path
   exports_dir = Path(__file__).resolve().parent / "exports"
   exports_dir.mkdir(parents=True, exist_ok=True)

   # 1. GLB
   bpy.ops.export_scene.gltf(filepath=str(exports_dir / "spaceman.glb"), export_format="GLB")
   # 2. OBJ
   bpy.ops.wm.obj_export(filepath=str(exports_dir / "spaceman.obj"))
   # 3. STL
   bpy.ops.wm.stl_export(filepath=str(exports_dir / "spaceman.stl"))
   # 4. FBX
   bpy.ops.export_scene.fbx(filepath=str(exports_dir / "spaceman.fbx"))
   ```

Write the complete, self-contained Python script inside a single ```python ... ``` code block. Include clean Blender scene setup (clear default objects), create smooth geometry with bevel modifiers, apply materials, and execute the 4 exports."""


def generate_viewer_html(exports_dir: Path, out_html: Path):
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Omni-3D Studio: SpaceMan Alien Astronaut</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script type="importmap">
  {
    "imports": {
      "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
      "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
    }
  }
  </script>
  <style>
    body { margin: 0; overflow: hidden; background: radial-gradient(circle at 50% 40%, #1e293b 0%, #0f172a 60%, #020617 100%); color: #f8fafc; font-family: system-ui, sans-serif; }
    canvas { display: block; width: 100vw; height: 100vh; position: fixed; inset: 0; z-index: 0; }
  </style>
</head>
<body class="relative min-h-screen">
  <canvas id="c"></canvas>

  <!-- Top Bar -->
  <div class="fixed top-5 left-6 right-6 flex items-center justify-between z-10 pointer-events-none">
    <div>
      <div class="flex items-center gap-2">
        <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse"></span>
        <h1 class="text-lg font-bold tracking-wider text-cyan-300">SPACEMAN · ALIEN ASTRONAUT</h1>
      </div>
      <p class="text-xs text-slate-400 mt-0.5">Procedural 3D Asset Synthesized via LL3M & Blender 5.2</p>
    </div>
    <div class="pointer-events-auto flex items-center gap-2">
      <span class="text-xs px-3 py-1 rounded-full bg-slate-800/80 border border-slate-700 text-slate-300 font-mono">
        Formats: GLB · OBJ · STL · FBX
      </span>
    </div>
  </div>

  <!-- Bottom Format Download Bar -->
  <div class="fixed bottom-6 left-1/2 -translate-x-1/2 z-10 bg-slate-900/90 border border-slate-700/80 backdrop-blur-md rounded-2xl p-3.5 shadow-2xl flex flex-wrap items-center gap-3">
    <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider pl-2 pr-1 hidden sm:block">
      Export Deliverables:
    </div>
    <a href="exports/spaceman.glb" download="spaceman.glb" class="px-3.5 py-2 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-400/40 text-cyan-300 font-mono text-xs font-semibold transition-all flex items-center gap-1.5 shadow-lg shadow-cyan-500/10">
      <span>📦</span> Download .GLB
    </a>
    <a href="exports/spaceman.obj" download="spaceman.obj" class="px-3.5 py-2 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 border border-amber-400/40 text-amber-300 font-mono text-xs font-semibold transition-all flex items-center gap-1.5 shadow-lg shadow-amber-500/10">
      <span>📐</span> Download .OBJ
    </a>
    <a href="exports/spaceman.stl" download="spaceman.stl" class="px-3.5 py-2 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-400/40 text-emerald-300 font-mono text-xs font-semibold transition-all flex items-center gap-1.5 shadow-lg shadow-emerald-500/10">
      <span>🖨️</span> Download .STL
    </a>
    <a href="exports/spaceman.fbx" download="spaceman.fbx" class="px-3.5 py-2 rounded-xl bg-purple-500/20 hover:bg-purple-500/30 border border-purple-400/40 text-purple-300 font-mono text-xs font-semibold transition-all flex items-center gap-1.5 shadow-lg shadow-purple-500/10">
      <span>🎮</span> Download .FBX
    </a>
  </div>

  <!-- Orbit Hint -->
  <div class="fixed bottom-24 left-1/2 -translate-x-1/2 text-[11px] uppercase tracking-widest text-slate-500 pointer-events-none font-mono">
    Drag to Orbit · Scroll to Zoom
  </div>

  <script type="module">
    import * as THREE from 'three';
    import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
    import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

    const canvas = document.getElementById('c');
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, window.innerWidth / window.innerHeight, 0.1, 50);
    camera.position.set(0, 1.2, 4.2);

    const controls = new OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.target.set(0, 0.8, 0);
    controls.autoRotate = true;
    controls.autoRotateSpeed = 1.2;

    // Studio Lighting
    const amb = new THREE.AmbientLight(0xffffff, 0.8);
    scene.add(amb);
    const key = new THREE.DirectionalLight(0xfff5ea, 1.8);
    key.position.set(3, 5, 4);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0x7dd3fc, 1.2);
    fill.position.set(-4, 2, -2);
    scene.add(fill);
    const rim = new THREE.DirectionalLight(0xfb923c, 1.0);
    rim.position.set(0, 4, -4);
    scene.add(rim);

    // Floor contact shadow grid
    const grid = new THREE.GridHelper(6, 20, 0x38bdf8, 0x1e293b);
    grid.position.y = -0.01;
    scene.add(grid);

    // Load Model
    let modelRoot = null;
    const loader = new GLTFLoader();
    loader.load('exports/spaceman.glb', (gltf) => {
      modelRoot = gltf.scene;
      
      // Compute bounding box and center
      const box = new THREE.Box3().setFromObject(modelRoot);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z);
      const scale = 2.0 / (maxDim || 1);
      modelRoot.scale.setScalar(scale);
      modelRoot.position.set(-center.x * scale, -box.min.y * scale, -center.z * scale);
      
      scene.add(modelRoot);
      controls.target.set(0, 1.0, 0);
    }, undefined, (err) => {
      console.warn('Could not load exports/spaceman.glb directly, waiting for build:', err);
    });

    window.addEventListener('resize', () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    });

    function animate() {
      requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    }
    animate();
  </script>
</body>
</html>
"""
    out_html.write_text(html_content, encoding="utf-8")
    print(f"  -> Generated Web Studio Viewer: {out_html}")


def run_pipeline(model: str = "glm-5.3-flash:cloud"):
    print("\n" + "=" * 65)
    print(f"  [PROJECT #2: OMNI-3D SPACEMAN PIPELINE]")
    print(f"  Image:      {IMAGE_PATH}")
    print(f"  Model:      {model}")
    print(f"  Exports:    GLB, OBJ, STL, FBX")
    print(f"  Blender:    {BLENDER_EXE}")
    print("=" * 65 + "\n")

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Dispatch through Harness2 directly via in-process call (avoids Windows CLI arg truncation)
    print("[1/3] Dispatching LL3M modeling task to Harness²...")
    sys.path.insert(0, str(ROOT))
    from scripts.dispatch_task import dispatch_custom_task

    dispatch_result = dispatch_custom_task(
        task_description=TASK_PROMPT,
        image_path=IMAGE_PATH,
        output_file=SCRIPT_PATH,
        model=model,
        k=1,
    )

    if not SCRIPT_PATH.is_file():
        raise RuntimeError(f"Expected generated script at {SCRIPT_PATH}, but file was not created.")

    print(f"  -> Successfully generated Blender modeling script: {SCRIPT_PATH}")

    # 2. Run Blender Headless
    print("\n[2/3] Running Headless Blender 5.2 LTS...")
    blender_cmd = [
        str(BLENDER_EXE),
        "-b",
        "-P", str(SCRIPT_PATH),
    ]
    b_res = subprocess.run(blender_cmd)
    if b_res.returncode != 0:
        print("  [WARNING] Blender exited with code", b_res.returncode)

    # 3. Verify deliverables
    print("\n[3/3] Auditing Export Deliverables in exports/...")
    expected_files = ["spaceman.glb", "spaceman.obj", "spaceman.stl", "spaceman.fbx"]
    for f in expected_files:
        p = EXPORTS_DIR / f
        if p.is_file():
            print(f"  ✓ {f:<15} ({p.stat().st_size:,} bytes)")
        else:
            print(f"  ✗ {f:<15} [MISSING]")

    # Generate Studio Viewer
    generate_viewer_html(EXPORTS_DIR, VIEWER_PATH)
    print(f"\n  Pipeline Complete! Open {VIEWER_PATH} to inspect.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="glm-5.3-flash:cloud")
    args = parser.parse_args()
    run_pipeline(args.model)
