---
name: ave-install
description: Install Avelin (A.V.E.) into the current agent with one command — no brew, no sudo, no API key — and verify it with a real check.
---

# Avelin install

Use this file only for first-time install, update or repair. For editing, read `SKILL.md`.

## The one command

```bash
# macOS / Linux
bash <(curl -fsSL https://raw.githubusercontent.com/mpleandro/ave/main/install.sh)
# or, with the repo already cloned:
bash ~/.claude/skills/ave/install.sh
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\skills\ave\install.ps1"
```

It does, in order: `uv` (Python installer, user-level, no sudo) → clone or
update the repo into `~/.claude/skills/ave` (the clone *is* the skill; nothing
to register) → Python deps, which include a **complete ffmpeg build** (with
`zscale` for iPhone HDR) and the **local transcription engine** (Silero VAD +
Whisper) → the voice model (~1.6 GB, once) → `helpers/doctor.py`, a real check
that runs the VAD and the Whisper engine on synthetic audio.

**No API key is required.** Transcription is local. Groq/ElevenLabs are
optional fallbacks for machines without a usable local engine; Pexels/Treblo
only for stock images and AI music. Ask for a key only when the user picks a
feature that needs it, never at install.

**Node.js 18+** is the only system prerequisite left, and only for Phase 2
(captions, graphics). `doctor.py` reports it; if missing, say so in one line
("a Fase 2 precisa do Node.js — nodejs.org, versão LTS") and continue: Phase 1
works without it.

## When you run it as the agent

- Talk in plain Portuguese; the person is a creator, not a developer. Say what
  they get and what *they* need to do next, not package names or flags.
- Run `install.sh` (or `.ps1`) as one command and wait for the in-chat approval
  prompt; never tell the user to open a terminal. Never ask for sudo.
- Fewer approval prompts: `doctor.py` prints an allowlist for
  `~/.claude/settings.json` → `permissions.allow`. Offer it once; apply it only
  with explicit consent. Claude Code's `fewer-permission-prompts` skill builds
  the same list from history.
- After install, verify with one real command on one real file — the installer
  already ran `doctor.py`; show its ✓/✗ lines in plain words.

## Diagnose

```bash
uv run --directory ~/.claude/skills/ave python helpers/doctor.py              # ✓/✗ + fix per line
uv run --directory ~/.claude/skills/ave python helpers/doctor.py --preparar   # re-download ffmpeg/model
curl -s localhost:4820/api/state | python3 -m json.tool | sed -n '/deps/,/}/p'  # what the editor sees
```

Common failures:
- `ModuleNotFoundError` → run helpers with `uv run python helpers/<name>.py`, never bare `python`.
- `ffmpeg` missing or without `zscale` → `doctor.py --preparar` links the pip build into `~/.local/bin`.
- Windows: after any install, `$PATH` only refreshes in a **new** PowerShell window.
- Old `uv sync` habit: always `uv sync --inexact`, or the on-demand resources (matting, 3D) get removed.

## Update

`git -C ~/.claude/skills/ave pull --ff-only && uv sync --directory ~/.claude/skills/ave --inexact`
— or just run the install command again; it is idempotent. `helpers/atualizacoes.py`
tells the user when there is something to pull (weekly fetch; `AVE_ATUALIZACOES=nunca` disables;
`AVE_OFFLINE=1` disables every network call).

## Optional resources (install themselves on first use)

| Resource | Size | Installed when the user asks for |
|---|---|---|
| `recorte` (torch + Robust Video Matting) | ~2 GB | head over the card border, cutout test, element behind the presenter |
| `anim3d` (MediaPipe + Depth Anything) | ~2.5 GB | the "Animação em 3D" format |
| `enquadramento` (MediaPipe + 3 small models) | ~100 MB | vertical reframing in the cuts gallery |
| `link` (yt-dlp) | ~10 MB | editing from a URL |

Do not pre-install them. `uv run python helpers/instalar.py status` shows what this machine has.
