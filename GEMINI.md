# Project Memory: Harness² (Google Research)

## Project Summary
- **Repo:** `google-research/harness2` (arXiv:2610.14224).
- **Domain:** Recursive agent harnessing for fixed-weight foundation models.
- **Key Concepts:**
  - Task-level recursion (Propose-Probe-Compose cycle across $K$ budgets; parallel or sequential).
  - Harnessing-level recursion (persistent lesson accumulation in improvement library).
  - 8 editable components: system prompts, guardrails, memory, tool guidance, subagents, skills, scripts, plugins.
  - Substrates: OpenCode (`oc`) and Codex (`cx`).
  - Benchmarks: JobBench (`jb`), LAB (`lab`), WorkBuddy-Bench (`wb`).

## Dual-Shift Architecture (Antigravity & Claude Code Integration)
- **Day Shift (Overseeing Chat AI):** Antigravity acts as the conversational architect and project manager, identifying tough/complex tasks.
- **Night Shift (Autonomous Engine):** Harness² runs in the background powered by **Ollama** (zero Google Cloud / Vertex AI costs), exploring candidate harnesses, probing executions, and synthesizing solutions.
- **Dual Knowledge Bridge (`scripts/sync_knowledge.py`):** Automatically synchronizes reflection lessons and newly discovered rules into:
  - `GEMINI.md` (read by Antigravity).
  - `CLAUDE.md` (read by Claude Code CLI).
- **Custom Task Dispatcher (`scripts/dispatch_task.py`):** Runs autonomous recursive optimization on custom user tasks without benchmark dependencies.
- **Antigravity Skill (`.agents/skills/harness/SKILL.md`):** Allows Antigravity to suggest or dispatch tasks directly from chat with model selection.

## Environment & Setup (Windows)
- **Runtime:** Python 3.12 managed via `uv` in `.venv`.
- **Install command:** `uv pip install -e ".[render]"`
- **Cross-Platform Patches Applied:**
  - `harness2/core/schedule.py`: Added safe import fallback for Unix-specific `fcntl` file locks.
  - `harness2/core/tree.py`: Normalized `p.relative_to(...)` to `.as_posix()` to prevent Windows backslash path mismatches on the editable component surface.
- **Multi-Agent Verification:**
  - Unit tests: `python -m unittest tests/test_workflow.py` (5/5 passing).
  - Deterministic demo: `harness2-demo --output runs/demo --k 2` (2/2 tasks completed, 0 failed).
  - Critic Audit: Resolved Ollama retry/timeout handling, date-drift duplication in sync, and non-interactive input parsing.

## Startup & Tool Scripts
- `start.bat`: General launcher (auto `.venv` provisioning, tests, checks, demo, activated shell).
- `start_ollama.bat`: Full-featured launcher with interactive CLI chat (`scripts/harness_chat.py`), model detection, and task execution.
- `start_google.bat`: Configured for Google Cloud Vertex AI (ADC credentials, project detection, Gemini 2.5 Flash).
- `start_dashboard.bat`: Dedicated launcher for the live Dual-Shift Telemetry Dashboard (runs on `http://localhost:8765/dashboard`).
- `scripts/telemetry_server.py`: Lightweight HTTP/SSE telemetry daemon broadcasting live task stages, model status, and knowledge sync stats.
- `scripts/select_ollama_model.ps1`: Dynamic Ollama scanner categorizing local weights and cloud models (`glm-5.3-flash:cloud`, `deepseek-v4.1-flash:cloud`, `minimax-m3.1-flash:cloud`, `qwen3.8:27b-mtp-q4_K_M`, `qwen3-coder:480b-cloud`, `deepseek-v3.1:671b-cloud`, `kimi-k2.7-code:cloud`, `gpt-oss:120b-cloud`).
- `scripts/harness_chat.py`: Interactive CLI chat with active harness rules and system prompt.

## Autonomous Lessons (Harness² Knowledge Base)
- **[2026-10-26] (task_convert_the_reference_image_in_20261026_124724):** Build the character feature-by-feature rather than primitive-by-primitive: assign each visual element its own technique — emissive/gradient-shaded sphere body, glossy eye spheres with separate white highlight spheres, a torus-arc or tube mouth, multiple noise-displaced flame shells using additive blending with depthWrite:false, and Points-based rising ember particles — then drive all motion (flicker, float, particle drift) from a single clock-based update loop instead of static transforms.
  - *When to apply:* When converting a stylized 2D character reference (e.g., a cute fireball with swept flame wisps, glossy eyes, and embers) into a procedural Three.js scene, and the first-pass model reads as flat, dull, or static compared to the image.
  - *Evidence:* The base solution approximated the character with a plain lit sphere plus a few static cone flames, which lost the fire's self-illumination, layered swept-back silhouette, and sense of life; the composed solution's per-feature decomposition (shader-driven flame layers, specular eye highlights, additive embers, unified time-based flicker/float loop) reproduced the reference's glow, gloss, and continuous motion, yielding a result that visually matches the source and is genuinely production-ready.
- **[2026-10-26] (task_you_are_an_elite_3d_technical_20261026_174609):** Compose the script from small parameterized factories instead of inlined primitive calls — a material factory with a version-safe input setter (alias-fallback for "Subsurface Weight"/"Subsurface", "Transmission Weight"/"Transmission"), a bevel+shade_smooth helper, and one builder function per anatomy part parented to a root empty — then pin every version-sensitive call: wipe the default scene first, use bpy.ops.wm.obj_export / bpy.ops.wm.stl_export (never legacy export_scene.obj/stl), resolve paths via Path(__file__).resolve().parent, and apply bevel modifiers or set the exporter's apply-modifier flag (e.g., export_apply=True for GLB) so exports contain the finished beveled mesh.
  - *When to apply:* Standalone bpy scripts that procedurally assemble a multi-part character/prop and must export GLB/OBJ/STL/FBX on a pinned modern Blender (4.x/5.x: new C++ exporters, renamed Principled BSDF inputs).
  - *Evidence:* The base solution hardcoded ~40 world-space transforms, reused no materials, left bevels unapplied, and used legacy exporter names with relative paths — producing runtime KeyErrors on renamed BSDF inputs, stray default-cube geometry inside exports, and STL/OBJ files missing all bevels. The composed version ran clean on first execution: all four files exported validly with bevels intact, visor transparency working (Alpha + blend-method guard), and a deduplicated 8-material list that kept GLB/FBX output compact.
- **[2026-10-26] (image_to_3d_sota_sculpting_pipeline):** Replace disconnected primitive blob clumping with a 5-Stage Computational Sculpting Architecture in Blender 5.2 LTS: (1) Block proportional anatomical volumes; (2) Melt all seams into a seamless watertight manifold skin using OpenVDB Voxel Remeshing (remesh_voxel_size = 0.030-0.035) + Smooth modifier (factor=0.55-0.75, iters=2-4) + Subsurf; (3) Carve subtractive anatomical cavities (orbital eye sockets, mouth cavities) via Boolean Difference (solver='EXACT'), then nest multi-layer iris/pupil/highlight spheres recessed within the carved sockets; (4) Generate swept flowing appendages (flames, tails, hair, limbs) using 3D Bézier splines with per-point tapering radius (bp.radius); (5) Multi-layer PBR materials with linear hex colors, Subsurface Scattering (Subsurface Weight 0.25-0.35), and LayerWeight grazing rim glow; (6) Harden the runtime with dependency-injected verified helper functions (safe_remove_object, make_organic_pbr_material, create_swept_spline_mesh, fuse_objects_voxel_remesh, carve_boolean_recess, export_scene_models), preventing LLM syntax hallucinations and object removal ReferenceErrors.
  - *When to apply:* Image-to-3D generation requiring organic curvature, high geometric fidelity, and watertight multi-format exports (.glb, .obj, .stl, .fbx) on integrated hardware without high-VRAM CUDA.
  - *Evidence:* Elevates procedural output from ~400 disconnected faces to 52,000–70,000 polygons with smooth organic fillets and carved anatomical depth, compiling headlessly in Blender 5.2 LTS in 2.7–4.1 seconds.
