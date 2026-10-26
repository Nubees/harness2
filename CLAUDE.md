# Claude Code Instructions: Harness² Project

## Project Overview
- **Domain:** Recursive Agent Harnessing (Harness²).
- **Architecture:** Dual-Shift System (Antigravity/Claude Code as Day Shift, Harness² as Night Shift).
- **Runtime:** Python 3.12 managed via `uv` in `.venv`.
- **Model Engine:** Ollama local and cloud-backed models (`http://localhost:11434/v1`).

## Key Commands
- Run workflow unit tests: `.venv\Scripts\python -m unittest tests/test_workflow.py`
- Dispatch autonomous task: `.venv\Scripts\python scripts/dispatch_task.py --task "<description>"`
- Sync lessons from runs: `.venv\Scripts\python scripts/sync_knowledge.py`
- Launch Ollama menu: `start_ollama.bat`
- Launch Master launcher: `start.bat`

## Autonomous Lessons (Harness² Knowledge Base)
- **[2026-10-26] (task_convert_the_reference_image_in_20261026_124724):** Build the character feature-by-feature rather than primitive-by-primitive: assign each visual element its own technique — emissive/gradient-shaded sphere body, glossy eye spheres with separate white highlight spheres, a torus-arc or tube mouth, multiple noise-displaced flame shells using additive blending with depthWrite:false, and Points-based rising ember particles — then drive all motion (flicker, float, particle drift) from a single clock-based update loop instead of static transforms.
  - *When to apply:* When converting a stylized 2D character reference (e.g., a cute fireball with swept flame wisps, glossy eyes, and embers) into a procedural Three.js scene, and the first-pass model reads as flat, dull, or static compared to the image.
  - *Evidence:* The base solution approximated the character with a plain lit sphere plus a few static cone flames, which lost the fire's self-illumination, layered swept-back silhouette, and sense of life; the composed solution's per-feature decomposition (shader-driven flame layers, specular eye highlights, additive embers, unified time-based flicker/float loop) reproduced the reference's glow, gloss, and continuous motion, yielding a result that visually matches the source and is genuinely production-ready.
- **[2026-10-26] (task_you_are_an_elite_3d_technical_20261026_174609):** Compose the script from small parameterized factories instead of inlined primitive calls — a material factory with a version-safe input setter (alias-fallback for "Subsurface Weight"/"Subsurface", "Transmission Weight"/"Transmission"), a bevel+shade_smooth helper, and one builder function per anatomy part parented to a root empty — then pin every version-sensitive call: wipe the default scene first, use bpy.ops.wm.obj_export / bpy.ops.wm.stl_export (never legacy export_scene.obj/stl), resolve paths via Path(__file__).resolve().parent, and apply bevel modifiers or set the exporter's apply-modifier flag (e.g., export_apply=True for GLB) so exports contain the finished beveled mesh.
  - *When to apply:* Standalone bpy scripts that procedurally assemble a multi-part character/prop and must export GLB/OBJ/STL/FBX on a pinned modern Blender (4.x/5.x: new C++ exporters, renamed Principled BSDF inputs).
  - *Evidence:* The base solution hardcoded ~40 world-space transforms, reused no materials, left bevels unapplied, and used legacy exporter names with relative paths — producing runtime KeyErrors on renamed BSDF inputs, stray default-cube geometry inside exports, and STL/OBJ files missing all bevels. The composed version ran clean on first execution: all four files exported validly with bevels intact, visor transparency working (Alpha + blend-method guard), and a deduplicated 8-material list that kept GLB/FBX output compact.
