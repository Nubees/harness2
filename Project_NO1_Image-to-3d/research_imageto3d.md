# Comprehensive Research: Image-to-3D Reconstruction & Procedural Generation

**Project:** `Project_NO1_Image-to-3d`  
**Date:** October 26, 2026  
**Document:** `research_imageto3d.md`  
**Architecture:** Dual-Shift (Antigravity Day Shift + Harness² Ollama Night Shift + RTX 3090 Local Compute)

---

## 1. Executive Summary

Transforming a 2D image into an interactive, high-fidelity 3D asset represents one of the most dynamic frontiers in AI. Today, the field splits into two distinct, powerful paradigms:

1. **Neural 3D Reconstruction & Diffusion:** Heavyweight neural networks that synthesize dense geometry (`.glb`, `.obj`), 3D Gaussians (3DGS), or Radiance Fields (NeRF) directly from image pixels via learned 3D priors. These run on dedicated GPUs (like our 24GB RTX 3090).
2. **Procedural & Code-Native 3D Synthesis:** Large Language Model (LLM) token-driven reasoning where AI vision models inspect the reference image and programmatically author modular, rigged, and lightweight 3D models (e.g. Three.js / TypeScript / OpenSCAD / Blender Python). This leverages the **Ollama + Harness²** recursive engine.

By uniting both paradigms under our **Dual-Shift architecture**, we can achieve both photorealistic dense mesh generation and fully procedural, inspectable code assets.

---

## 2. Deep-Dive: Target Repositories

### A. Microsoft TRELLIS & TRELLIS.2 (`microsoft/TRELLIS` & `microsoft/TRELLIS.2`)
* **Repository:** [github.com/microsoft/TRELLIS](https://github.com/microsoft/TRELLIS) / [github.com/microsoft/TRELLIS.2](https://github.com/microsoft/TRELLIS.2)
* **Core Tech:** Structured 3D Latents (SLAT) and "field-free" sparse voxel structures (`O-Voxel`) powered by 2B to 4B parameter flow-matching transformers.
* **Outputs:** 
  - Textured Polygon Meshes (`.glb`, `.obj`)
  - 3D Gaussian Splats (`.ply`)
  - Neural Radiance Fields (NeRF)
  - Full PBR materials (Albedo, Roughness, Metallic, Normal maps)
* **Strengths:** 
  - Undisputed state-of-the-art for complex topologies, sharp details, thin structures (clothing, leaves, antennae), and articulated objects.
  - Generates multiple representations simultaneously from one forward pass.
* **Hardware Profile:**
  - VRAM: 16 GB – 24 GB VRAM.
  - Inference Time: 20 – 45 seconds on modern CUDA GPUs.
  - **Match for us:** Fits natively inside our secondary **RTX 3090 (24GB VRAM)**.

---

### B. img2threejs (`img2threejs/img2threejs`)
* **Repository:** [github.com/img2threejs/img2threejs](https://github.com/img2threejs/img2threejs)
* **Core Tech:** Staged, quality-gated AI coding skill that generates **pure TypeScript / Three.js code** (`THREE.Group` factories) rather than opaque binary mesh files.
* **Pipeline Phases:**
  1. *Blockout:* Rough geometric bounding boxes and primitive composition.
  2. *Structural:* Hierarchy assembly, joint anchors, pivots, and parent-child trees.
  3. *Form & Sculpting:* Extrusions, lathed shapes, bezier curves, and boolean CSG operations.
  4. *Materials:* Shader setup, procedural canvas textures, roughness, and metalness.
  5. *Lighting & Surface:* Normal mapping, soft shadows, ambient occlusion.
  6. *Interaction & Animation:* Bone rigs, morph targets, rotation logic.
  7. *Optimization:* Buffer geometry merging and draw-call reduction.
* **Token Power Synergy:**
  - Uses zero local GPU VRAM for neural inference.
  - 100% token-driven: ideal for **Harness²** running recursive Propose–Probe–Compose loops with Ollama vision-code models (e.g. `glm-5.3-flash:cloud`, `deepseek-v4.1-flash:cloud`, `kimi-k2.7-code:cloud`).

---

### C. Modly (`lightningpixel/modly`)
* **Repository:** [github.com/lightningpixel/modly](https://github.com/lightningpixel/modly)
* **Core Tech:** Local desktop studio and modular backend engine combining an Electron/TypeScript frontend with a Python FastAPI server.
* **Architecture:**
  - Modular extension system loading plug-and-play image-to-3D pipelines (Trellis, Hunyuan3D, TripoSR).
  - Built-in VRAM/RAM telemetry, queue management, and batch processing.
  - Includes a standalone Python CLI that allows external agents (like Antigravity or Harness²) to trigger local 3D jobs headlessly over localhost HTTP or CLI commands.
* **Utility for us:** Can serve as the turnkey local API service deployed on the RTX 3090 machine.

---

## 3. Alternative & Complementary SOTA Models

To ensure we select the best tools, we evaluated the wider open-source landscape:

| Model | Creator / Org | Core Tech | VRAM Required | Speed | Primary Output | Best Use Case |
|---|---|---|---|---|---|---|
| **TRELLIS.2** | Microsoft | Sparse O-Voxel DiT | ~16–24 GB | 25–40s | Mesh (GLB) + 3DGS + NeRF | Maximum visual fidelity, PBR texturing |
| **Hunyuan3D 2.0 / 2.1** | Tencent | DiT Shape + Diffusion Paint | ~12–18 GB | 30–60s | Textured GLB / OBJ | High-resolution production meshes with rich UV maps |
| **Stable Fast 3D (SF3D)** | Stability AI | Feed-Forward LRM + UV Baker | ~6–8 GB | **0.5 – 2s** | GLB (Illumination-unwrapped) | Real-time prototyping, instant previews, game assets |
| **TripoSR** | Stability AI / VAST | Large Reconstruction Transformer | ~6 GB | **1 – 3s** | Textured Mesh (OBJ) | Fast, lightweight baselines, low-end GPU execution |
| **img2threejs** | Open Source | Multi-stage LLM Sculptor | **0 GB (Tokens)** | Agent-paced | TypeScript Three.js code | Procedural, interactive, editable, web-native 3D apps |

### Key Findings on Alternatives:
- **Tencent Hunyuan3D-2.1:** Exceptional texture fidelity with explicit UV unwrapping. Tencent also provides portable Windows releases (`Hunyuan3D-2-WinPortable`), making deployment on our RTX 3090 PC painless.
- **Stable Fast 3D (SF3D):** The undisputed speed champion. Completes mesh generation and texture baking in ~0.5 seconds with built-in de-lighting (removing pre-existing shadows from the photo so the 3D model looks clean under any new light).

---

## 4. Hardware & Resource Allocation Plan

We have three distinct computing tiers available:

```
+---------------------------------------------------------------------------------------+
|                                TIER 1: DAY SHIFT (This Session)                      |
|  - Platform: Google Antigravity                                                       |
|  - Role: Conversational Architect, Multi-Modal Vision Analysis, UI Previews          |
|  - Tools: Three.js interactive canvas widgets, Git manager, Task delegator           |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
|                          TIER 2: NIGHT SHIFT (Harness² Engine)                         |
|  - Platform: Ollama Local/Cloud Endpoints (Zero Cloud Billing)                         |
|  - Models: glm-5.3-flash:cloud, deepseek-v4.1-flash:cloud, kimi-k2.7-code:cloud       |
|  - Role: Token-Powered Procedural Sculpting (img2threejs pipeline)                    |
|  - Tasks: Autonomous Propose-Probe-Compose cycles for Three.js / OpenSCAD code       |
|  - Post-Processing: Mesh cleaning, decimation scripts, shader writing, lesson sync   |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
|                       TIER 3: LOCAL NEURAL COMPUTE NODE (Dedicated PC)                |
|  - Hardware: NVIDIA GeForce RTX 3090 (24GB VRAM)                                      |
|  - Engine Options: TRELLIS / Hunyuan3D-2.1 / SF3D / Modly FastAPI Server              |
|  - Role: Heavyweight Neural Mesh & Gaussian Splat Inference                           |
|  - Interface: Headless FastAPI REST endpoint on local LAN (http://192.168.x.x:8000)   |
+---------------------------------------------------------------------------------------+
```

---

## 5. Token Power Synergy (How Harness² Empowers Image-to-3D)

Neural models generate "frozen" polygon meshes. LLM token power (Harness² + Ollama) brings dynamic intelligence to the pipeline in three critical ways:

### 1. The Autonomous img2threejs Procedural Sculptor
Instead of downloading 100MB binary files, Harness² can take any reference image and autonomously code an editable Three.js scene:
- **Propose:** The LLM generates the initial Three.js TypeScript module (blockout + hierarchy).
- **Probe:** A headless rendering script (Puppeteer + Three.js) captures front, top, and perspective viewpoints.
- **Compose:** Harness² compares the rendered views against the target image, identifies proportion errors or missing details, and refines the code recursively until the asset is faithful.

### 2. Intelligent Mesh Refinement & Post-Processing
Dense neural meshes from TRELLIS or Hunyuan3D often contain 500k+ polygons, inverted normals, or noisy vertices:
- Harness² writes Python scripts using `trimesh`, `pymeshlab`, and `open3d` to automatically:
  - Decimate meshes down to target polycounts (e.g., 5,000 polys for web/mobile).
  - Repair non-manifold edges and close watertight holes.
  - Generate LOD (Level-of-Detail) ladders.

### 3. Prompt & Semantic Pre-Processing
Neural models perform significantly better when the input image has:
- A clean, transparent alpha channel (background removed via `rembg`).
- Explicit semantic prompting (e.g., specifying material properties, canonical orientation).
- Harness² autonomously preprocesses the image and synthesizes the optimal conditioning parameters before passing it to the 3090 GPU.

---

## 6. Recommended Architectural Options for Our Project

### Option A: The Neural-First Heavyweight Pipeline (High-Fidelity)
* **Workflow:** User feeds image -> Background removed -> Sent to RTX 3090 node running **TRELLIS.2** or **Hunyuan3D-2.1** -> Returns high-resolution `.glb` with PBR textures.
* **Best for:** Photorealistic objects, organic creatures, complex industrial models, 3D printing STL exports.
* **Setup required:** Clone TRELLIS or Hunyuan3D on the RTX 3090 PC with a simple FastAPI wrapper.

### Option B: The Pure Agentic Token Pipeline (Code-Native & Instant)
* **Workflow:** User feeds image -> Antigravity/Harness² executes the **img2threejs** pipeline -> Emits an interactive, procedural `.ts`/Three.js component.
* **Best for:** Lightweight web apps, UI widgets, animated mechanical items, procedural game objects.
* **Setup required:** Zero external GPU setup required; runs right now using our existing Ollama models and Antigravity.

### Option C: The Hybrid Dual-Engine Studio (The Ultimate Solution)
* **Workflow:**
  1. Fast Path: Instant preview via **Stable Fast 3D** (~1 second) or **img2threejs** (procedural code).
  2. Heavy Path: Production bake via **TRELLIS.2** on the RTX 3090.
  3. Optimization: Harness² runs post-processing to clean the topology and generate an interactive viewer.

---

## 7. Immediate Next Steps & Discussion Points

1. **Which path do we want to build first inside `Project_NO1_Image-to-3d`?**
   - **Path 1 (Immediate / Local):** Build the **Procedural Token Sculptor** (`img2threejs` pipeline inside Harness²) that works immediately on this machine using Ollama without waiting for network/GPU setup.
   - **Path 2 (Remote Neural Node):** Configure the REST bridge to connect this project to the **RTX 3090 PC** running TRELLIS / Hunyuan3D / Modly.
   - **Path 3 (Full Stack):** Set up both so the system can choose between code generation (Three.js) or neural mesh generation (.glb).
