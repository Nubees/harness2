# Research & Blueprint: Token-Powered Image-to-3D with Multi-Format Export

**Project:** `Project_no2_Image_to_3d_Model`  
**Date:** October 26, 2026  
**Document:** `research_repos.md`  
**Target Formats:** **GLB, OBJ, STL, FBX**  
**Token Engines:** **Ollama (Harness² Night Shift)** & **Antigravity (Day Shift)**

---

## 1. Executive Summary

Our goal is to build an autonomous system that takes any 2D reference image and uses **LLM / VLM token power** (Ollama or Antigravity) to produce a true 3D asset exportable into all four standard 3D formats:
- **`.glb` / `.gltf`:** Universal web and mobile 3D standard (embedded textures, PBR materials, animations).
- **`.obj`:** Universal Wavefront format for 3D modeling packages (Maya, ZBrush, Cinema4D, Blender).
- **`.stl`:** Standard stereolithography mesh for 3D printing and CAD slicers.
- **`.fbx`:** Industry standard for game engines (Unity, Unreal Engine) with full hierarchy, rigging, and animation support.

---

## 2. Deep-Dive on Target Open-Source Repositories

### A. `threedle/ll3m` (LL3M: Large Language 3D Modelers)
* **GitHub:** [github.com/threedle/ll3m](https://github.com/threedle/ll3m) (arXiv:2411.05436)
* **Core Paradigm:** Treats 3D asset creation as a **collaborative code-writing and debugging task** using Large Language Models to drive **Blender's Python API (`bpy`)**.
* **Key Innovations:**
  1. *Multi-Agent Division:* Planner Agent (deconstructs shape) $\rightarrow$ Coder Agent (writes BMesh and modifiers) $\rightarrow$ Critic Agent (visual/code audit) $\rightarrow$ Debugger Agent.
  2. *High-Level Parametric Primitives:* Instead of emitting millions of raw coordinates, it uses Blender's modifier stack (Subdivision Surface, Bevel, Boolean CSG, Solidify, Mirror) to keep geometry clean and lightweight.
  3. *Native Multi-Format Exporter:* Blender natively exports to `.glb`, `.obj`, `.stl`, and `.fbx` with single-line API calls.
* **Takeaway for our Project:** This is the gold standard for full FBX/GLB/OBJ/STL pipeline compatibility.

---

### B. `Chuny1/3DGPT` (3D-GPT: Procedural 3D Modeling with LLMs)
* **GitHub:** [github.com/Chuny1/3DGPT](https://github.com/Chuny1/3DGPT) (arXiv:2310.12945)
* **Core Paradigm:** Translates natural instructions into procedural 3D modeling scripts through a 3-agent pipeline:
  1. *Task Dispatch Agent:* Identifies domain, category, and target engine.
  2. *Conceptualization Agent:* Enriches sparse text/image concepts into spatial bounding relationships.
  3. *Modeling Agent:* Maps semantic parameters into Blender procedural node trees and Python scripts.
* **Takeaway for our Project:** We can adopt the Conceptualization $\rightarrow$ Spatial Decomposition stage so that vision models break down reference images into exact proportional measurements before writing code.

---

### C. `nv-tlabs/LLaMA-Mesh` (NVIDIA Toronto AI Lab)
* **GitHub:** [github.com/nv-tlabs/LLaMA-Mesh](https://github.com/nv-tlabs/LLaMA-Mesh) (arXiv:2411.09530)
* **Core Paradigm:** Adapts LLMs to generate 3D mesh vertices and faces directly as text tokens (similar to an ASCII OBJ file: `v x y z` and `f v1 v2 v3`).
* **Strengths:** 100% self-contained within the language model; requires zero external software runtime.
* **Limitations:** Limited to low-to-medium polygon density; text token generation is computationally slow for complex meshes (>2,000 vertices).
* **Takeaway for our Project:** Ideal for generating direct geometric base-hulls and simple props, but procedural code generation (LL3M) produces superior high-poly meshes with clean topology.

---

### D. `img2threejs` + Three.js Headless Exporters
* **GitHub:** [github.com/img2threejs/img2threejs](https://github.com/img2threejs/img2threejs)
* **Core Paradigm:** 7-stage quality-gated sculpting pipeline (Blockout $\rightarrow$ Structure $\rightarrow$ Form $\rightarrow$ Materials $\rightarrow$ Lighting).
* **Exporting Capabilities in Three.js:**
  - Three.js provides official exporters: `GLTFExporter`, `OBJExporter`, `STLExporter`.
  - Can run inside our existing browser viewer or headlessly in Node.js.
  - FBX export requires converting the resulting OBJ or GLB via Python `trimesh` or `assimp`.

---

## 3. Format Export Comparison Matrix

| Format | Primary Use Case | Materials / Textures | Rigging & Hierarchy | Native Python Tooling | Native Blender (`bpy`) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **`.glb`** | Web, AR, Mobile, 3D Viewers | Full PBR | Yes | `trimesh`, `pygltflib` | `bpy.ops.export_scene.gltf()` |
| **`.obj`** | Modeling, CAD, 3D printing | Basic MTL | Flat / Grouped | `trimesh`, `wavefront` | `bpy.ops.wm.obj_export()` |
| **`.stl`** | 3D Printing (Slicers, CNC) | Geometry only | No (Single shell) | `trimesh`, `numpy-stl` | `bpy.ops.wm.stl_export()` |
| **`.fbx`** | Game Engines (Unreal, Unity) | Embedded PBR / Phong | Full armature & bones | `pyassimp` / Blender | `bpy.ops.export_scene.fbx()` |

---

## 4. The Proposed Hybrid Architecture for `Project_no2_Image_to_3d_Model`

To create our own superior system, we combine the best features from each project into a unified **Omni-Format 3D Pipeline**:

```
                              [REFERENCE IMAGE]
                                      |
                                      v
  +-----------------------------------------------------------------------+
  |              STAGE 1: MULTI-MODAL VISION DECOMPOSITION                |
  |  - Powered by: Ollama GLM-5.3-flash:cloud OR Antigravity Day Shift    |
  |  - Inspiring Repo: 3D-GPT & img2threejs                               |
  |  - Extracts: Geometry hierarchy, bounding dimensions, symmetry,      |
  |              colors (#hex), PBR roughness/metallic, key silhouettes   |
  +-----------------------------------------------------------------------+
                                      |
                                      v
  +-----------------------------------------------------------------------+
  |             STAGE 2: PROCEDURAL SCRIPT SYNTHESIS & HARNESS            |
  |  - Powered by: Harness² Night Shift (Propose-Probe-Compose cycle)     |
  |  - Inspiring Repo: LL3M (threedle/ll3m)                               |
  |  - Engine Target Options:                                             |
  |      A) Pure Python (Trimesh / PyVista) -> Zero external install      |
  |      B) Headless Blender (bpy)          -> Full modifier/shader power |
  +-----------------------------------------------------------------------+
                                      |
                                      v
  +-----------------------------------------------------------------------+
  |                   STAGE 3: MULTI-FORMAT EXPORT HUB                    |
  |  - Executes script & exports simultaneously into 4 standard formats:  |
  |      1. output.glb   (Interactive web & mobile preview)               |
  |      2. output.obj   (Wavefront polygon mesh + MTL material)          |
  |      3. output.stl   (Watertight manifold for 3D printing)            |
  |      4. output.fbx   (Game-ready asset for Unity/Unreal Engine)       |
  +-----------------------------------------------------------------------+
                                      |
                                      v
  +-----------------------------------------------------------------------+
  |                    STAGE 4: LIVE DASHBOARD & PREVIEW                  |
  |  - Telemetry broadcast to Dual-Shift Console (localhost:8765)         |
  |  - Interactive 3D web viewer with 1-click download buttons for        |
  |    [Download GLB] [Download OBJ] [Download STL] [Download FBX]        |
  +-----------------------------------------------------------------------+
```

---

## 5. Brainstorming: 2 Implementation Routes for Our Core Engine

### Route 1: The Zero-Dependency Pure Python Engine (`trimesh` + Exporters)
- **How it works:** Uses Python's `trimesh` and computational geometry algorithms to create parametric shapes, CSG booleans, extrusions, and revolves, then calls `mesh.export('model.glb')`, `mesh.export('model.obj')`, `mesh.export('model.stl')`. For FBX, uses an automated conversion bridge.
- **Advantage:** Works immediately right now inside our existing Python `.venv` without downloading or configuring Blender.
- **Best for:** Geometric, mechanical, stylized low-to-medium poly assets, 3D printable parts.

### Route 2: The Blender Headless Scripting Engine (`bpy` / LL3M style) — [VERIFIED READY]
- **Local Environment Status:** `Blender 5.2.1 LTS` is **already installed** at `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`!
- **How it works:** Harness² writes high-level Blender Python scripts (`bpy`), using BMesh, Subdivision Surface modifiers, and Principled BSDF shaders. A background command `blender.exe -b -P script.py` executes headlessly and emits all 4 formats natively.
- **Advantage:** State-of-the-art visual quality, complex organic curves, native FBX rigging/armature, professional quad topology, and instant export into **GLB, OBJ, STL, and FBX**.
- **Requirement:** Fully satisfied on your machine.

### Route 3: The Dual-Target Studio (Recommended)
- Provide a unified runner: If Blender is detected, it runs the **LL3M (`bpy`)** engine; otherwise, it automatically falls back to the **Pure Python (`trimesh` + Three.js)** engine, ensuring that all 4 formats (GLB, OBJ, STL, FBX) are generated seamlessly under any environment.
