"""Interactive Harnessed CLI Chat.

Connects to Ollama using the selected model, with active harness system prompts,
guardrails, and persistent context injected into the conversation.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Load harness prompt & guardrails if available
BASE_HARNESS_DIR = ROOT / "third_party" / "jb_runner" / "harness_baseline_oc"
SYSTEM_PROMPT_PATH = BASE_HARNESS_DIR / "systemprompt.md"
GUARDRAILS_PATH = BASE_HARNESS_DIR / "guardrails.md"


def load_harness_system_message() -> str:
    parts = []
    if SYSTEM_PROMPT_PATH.is_file():
        parts.append(SYSTEM_PROMPT_PATH.read_text(encoding="utf-8", errors="replace").strip())
    if GUARDRAILS_PATH.is_file():
        parts.append("# Guardrails & Rules:\n" + GUARDRAILS_PATH.read_text(encoding="utf-8", errors="replace").strip())
    if not parts:
        return "You are an expert AI agent running within the Harness² autonomous framework."
    return "\n\n".join(parts)


def send_chat_completion(base_url: str, model: str, messages: list[dict]) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        choices = body.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            return msg.get("content") or ""
        return ""


def main():
    model = os.environ.get("OLLAMA_MODEL") or (sys.argv[1] if len(sys.argv) > 1 else "kimi-k2.7-code:cloud")
    base_url = os.environ.get("HARNESS2_CODEX_BASE_URL") or "http://localhost:11434/v1"

    print("=" * 60)
    print(f"  Harness² Interactive AI Chat  ")
    print("=" * 60)
    print(f"Model:    {model}")
    print(f"Endpoint: {base_url}")
    print("Harness:  System prompt & guardrails active")
    print("Commands: /clear (reset history), /exit or /quit (leave)")
    print("=" * 60 + "\n")

    system_prompt = load_harness_system_message()
    history = [{"role": "system", "content": system_prompt}]

    while True:
        try:
            user_input = input("You > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting chat.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("/exit", "/quit", "exit", "quit"):
            print("Goodbye!")
            break

        if user_input.lower() == "/clear":
            history = [{"role": "system", "content": system_prompt}]
            print("[History cleared. Harness re-initialized.]\n")
            continue

        if user_input.lower() == "/help":
            print("\nAvailable commands:")
            print("  /clear - Clear chat memory and reset harness")
            print("  /exit  - Return to terminal")
            print("  Any other message will be sent to the model.\n")
            continue

        history.append({"role": "user", "content": user_input})
        print(f"\n{model} is thinking...", end="\r", flush=True)

        try:
            reply = send_chat_completion(base_url, model, history)
            print(" " * 40, end="\r")  # clear thinking line
            print(f"AI > {reply}\n")
            history.append({"role": "assistant", "content": reply})
        except urllib.error.HTTPError as exc:
            print(" " * 40, end="\r")
            print(f"[Error: HTTP {exc.code} {exc.reason}]")
            if exc.code == 410:
                print("Note: This remote cloud model endpoint has expired or is unavailable.")
            print()
            history.pop()  # remove failed prompt
        except Exception as exc:
            print(" " * 40, end="\r")
            print(f"[Connection Error: {exc}]\n")
            history.pop()


if __name__ == "__main__":
    main()
