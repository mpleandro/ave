---
name: ave
description: Avelin — edit any video by conversation, in phases. Two tracks — SHORT-FORM (vertical 9:16 for Reels/TikTok/Shorts) and LONGFORM (horizontal 16:9 for YouTube: talking-head+B-roll, tutorials/screen-record, vlogs). PHASE 1 — clean cut + color grade + optional voice EQ/mastering (transcribe, select best takes, cut on silence for short-form or retention arc + cold open for longform, grade; ask if shot in LOG; master the voice), then show the user for approval. PHASE 2 (after the cut is approved) — HyperFrames visuals from a data-driven template: short-form gets karaoke captions, a static hook, a dynamic camera and behind-the-subject; longform gets B-roll cutaways, lower-thirds, chapter cards, callouts, plus YouTube chapters and .srt captions. PHASE 3 — soundtrack (AI via Treblo or a local file). Illustrative images/video via Pexels + Wikimedia/Google. Ask questions, confirm, execute, iterate, persist.
---

# Avelin — editor de vídeo

> **PHASE 2 RENDERS WITH HYPERFRAMES** (Apache 2.0). One command takes it end to
> end — `helpers/phase2.py <edit>` — and the visual vocabulary is complete: six
> caption styles, four headlines, three edit types, the dynamic camera, and the
> four longform layers. The LOOK lives in `assets/styles/` and the NUMBERS in
> `assets/styles/variants.json`; the composition is GENERATED, never scaffolded
> from a template.
>
> Still missing, and say so rather than faking: the behind-the-subject layer
> (the cutout tool is validated — `hyperframes remove-background` — but the
> effect is not assembled).
>
> Fork of [edvid](https://github.com/fillrochaa/edvid) (MIT, Creator Factory) —
> see `LICENSE`. Upstream is tracked as the `upstream` remote; keep the diff
> confined to Phase 2 so Phase-1 improvements keep merging cleanly.

## Principle

1. **Two phases, one gate between them.** PHASE 1 is the clean cut + color grade. Show it and **wait for approval**. PHASE 2 (captions, graphics, images) only starts after the cut is signed off.
2. **LLM reasons from raw transcript + on-demand visuals.** The only derived artifact that earns its keep is the packed phrase-level transcript (`takes_packed.md`). Everything else you derive at decision time.
3. **Audio is primary, visuals follow.** Cut candidates come from speech boundaries and silence gaps.
4. **Ask → confirm → execute → iterate → persist.** Never touch the cut until the user confirms the strategy in plain English.
5. **Generalize.** Look at the material, ask the user, then edit — never assume what kind of video it is.
6. **Artistic freedom is the default.** Specific values here are worked examples, not mandates. Only the Hard Rules are mandatory.
7. **Verify your own output before showing it** — numbers first, images only where the numbers flag (see Self-eval).
8. **Spend tokens where taste lives.** Machine data (raw transcripts, captions.json, track.json, template code) is for programs, not for reading. Batch visual checks into one montage instead of N images.
9. **Decisão de ofício é sua — você decide e INFORMA.** Ritmo, duração de um gráfico, curva de aceleração, onde um overlay entra e sai, qual quadro do B-roll usar, quanto acelerar uma tela gravada: escolha, execute, e diga em uma linha **o que fez e por quê**. Não pare para perguntar. O usuário pede diferente se quiser diferente — essa é a via, não a pergunta prévia. Isto NÃO afasta o item 4 nem a Hard Rule 8: **a estratégia do corte** (quais tomadas, o que entra, o que sai, o que o vídeo diz) continua confirmada antes de executar. A linha é: *o que o vídeo diz* se confirma; *como ele diz* se decide.

## Hard Rules (production correctness — non-negotiable)

1. **The phase gate is real, and it is SPOKEN.** A ordem, nesta sequência: **renderize o `preview_proxy.mp4` → MOSTRE → pergunte em palavras ("aprova a Fase 1?") → espere a resposta.** Ninguém aprova o que não viu — o proxy existe exatamente para ser a coisa vista, e é o primeiro artefato da Fase 1, não uma recompensa por aprovar. Só depois do sim vêm as duas consequências: o `preview.mp4` final é encodado (uma vez) e a Fase 2 destranca. Nada dela — estilo, legenda, gráfico, trilha — começa antes disso.
2. **Per-segment extract → lossless `-c copy` concat**, never a single-pass filtergraph. (Under the default J-cut the picture and the sound of a take are extracted as separate ranges and the audio tracks are summed — that is the one sanctioned mix, and the video path is still per-segment + lossless concat.)
3. **30ms audio fades at every segment boundary** (encoded in render.py).
4. **Never cut inside a word** — snap to word boundaries from the transcript.
5. **Pad every cut edge** (30–200ms window; trail slightly longer than lead). Cut on silence whenever possible.
6. **Cache transcripts per source.** Never re-transcribe unless the source changed.
7. **Color grade per-segment during extraction**, never post-concat.
8. **Strategy confirmation before execution.**
9. **All session outputs in `<videos_dir>/edit/`** — never inside the Avelin repo.
10. **PHASE 2 IS HYPERFRAMES-ONLY** — never burn text or overlays with ffmpeg/PIL. A style that is not ported yet is REFUSED BY NAME (`helpers/phase2.py` does this), never substituted by something that looks close.
11. **PHASE 2 is data-driven.** `edit-data.json` describes the video; the LOOK lives in `assets/styles/` and the NUMBERS in `assets/styles/variants.json` — the same files the editor's Estilo previews are meant to read, so the two can never disagree. Bespoke graphics are the one escape hatch: an HTML of your own under `<projeto>/compositions/<id>.html`, mounted as a sub-composition. Never hand-write a style inside the composer.
12. **Verify numerically first.** Run `verify_cut.py` on every rendered cut; open images only for flagged junctions. Batch any multi-frame look into one `contact_sheet.py` / `grade.py --candidates` montage.
13. **Never Read machine data into context**: `transcripts/*.json` (raw), `captions.json`, `track.json`, `segments.json`, matte/track binaries. Read `takes_packed.md` and helper stdout instead.
14. **UMA transcrição, não duas — e NENHUMA delas é "a boa".** A legenda sai das FONTES deslocadas pelo EDL (`cut_transcript.py` → `cut_mapped.json`), **nunca** de uma segunda transcrição do `preview.mp4`. O motivo não é precisão: duas passadas do mesmo modelo sobre o mesmo áudio erram em lugares DIFERENTES, e nesta série as metades erradas ficaram repartidas — a fonte trocou "trabalhar" por "avaliar", o corte perdeu "sem conhecimento". **Nunca resolva um desacordo escolhendo um lado por preferência** (eu escolhi, escrevi que a fonte era a correta, e queimei a palavra errada no vídeo; o usuário ouviu e desmentiu). Resolva com uma TERCEIRA passada isolada — `transcript_audit.py --recheck` — e grave o resultado em `transcripts/corrections.json` (com `from`, senão a correção pinta as palavras vizinhas). O que o mapeamento entrega é **um único texto corrigido num lugar só**: o que o usuário lê e edita na Fase 1 é LITERALMENTE o que entra no vídeo, senão apagar uma palavra no painel não corta o que ele acha que corta. Use `audio_start_in_output` do `jcut_timeline` — sob J-cut o áudio entra antes da imagem, e legenda segue a voz; somar durações de range atrasa cumulativamente (+1,08s no último trecho, medido).
15. **RODE O `transcript_audit.py --fix-times` ANTES DE ESCREVER O EDL.** O transcrito parecer bom não é evidência de que está certo, e ele mente de três jeitos:
    - **Engole gaguejo e repetição** sem deixar rastro no texto. Cada janela que o detector de densidade acusa é fala sem texto ou texto sem fala; leve as reais ao usuário junto com a estratégia de corte.
    - **Troca palavra por palavra** — resolva com `--recheck`, nunca escolhendo um lado por preferência (ver Regra 14).
    - **Estica o fim da palavra por cima da pausa seguinte.** Medido em C0012 do projeto 29: `"você"` carimbada 63,00–64,52 (1,52s para duas sílabas) com 0,92s de SILÊNCIO dentro do carimbo. Na fonte inteira eram 17 palavras e **7,5s de silêncio atribuído a palavras**. Os outros dois detectores não pegam isso: a pausa é longa o bastante para partir a região de fala em duas, então vira vão ENTRE regiões e a densidade de cada metade continua normal. `--fix-times` apara o fim até a fala medida, guarda o original em `<fonte>.raw.json` e é idempotente. **Importa porque é este carimbo que vira legenda queimada** (Regra 14) — sem o aparo o karaokê segura a palavra na tela por mais de um segundo enquanto ninguém fala.
    O aparo tem piso POR PALAVRA (~0,055s/caractere): quando o `silencedetect` parte a região dentro da própria palavra, aparar até o fim da região daria 0,09s — a leitura certa é que a região se partiu, não que a palavra esticou, e aí não se mexe. Sem essa guarda a primeira versão aparava `'pessoal'` para 0,09s e `'empreender'` para 0,17s.
    Pular esse passo entrega gaguejo no vídeo e legenda fora do tempo, e o usuário descobre assistindo.
16. **Pediu vídeo "transparente"? AVALIE O OVERLAY ANTES DE ESCOLHER.** Toda vez que o usuário quiser um vídeo transparente, ou tirar o fundo de uma gravação de tela, decida entre `mix-blend-mode: screen` (o escuro some de graça — só serve para arte CLARA) e alfa de verdade em VP9 `yuva420p` (a arte tem escuro que importa: texto escuro, sombra, contorno). **Olhe a arte e prove antes de renderizar** — compor `1-(1-a)*(1-b)` sobre um quadro real do corte custa segundos e responde o que uma render responderia em minutos. Screen apaga TODO pixel escuro, não só o fundo. A tabela de decisão, as armadilhas e a receita da matte estão em `references/shortform.md`, seção "Quero o vídeo transparente".

## Execution medium — ffmpeg pipeline (default) vs Adobe Premiere (MCP)

The default engine is the ffmpeg/HyperFrames pipeline below. **If the user wants the
edit done inside Adobe Premiere Pro via the `premiere-pro` MCP** (e.g. "edite a
sequência no Premiere", "corte via MCP"), the METHOD here is unchanged (audio-primary,
cut on silence, phase gate, grade with taste) but the hands change — **read
`references/premiere-mcp.md`** for the battle-tested Premiere workflow (razor +
ripple recipe, the V/A-link ripple caveat, `color_correct` LOG-strength lesson,
voice master, `export_frame` gotcha, tool cheat-sheet). Transcription/`edl.json`
are identical and cached — reuse an approved `edl.json`; skip `preview.mp4`/preview.

## Directory layout

```
<videos_dir>/
├── <source files, untouched>
└── edit/
    ├── project.md               ← memory; appended every session
    ├── takes_packed.md          ← phrase-level transcripts, the primary reading view
    ├── edl.json                 ← cut decisions (Phase 1)
    ├── transcripts/<name>.json  ← cached word-level transcripts (Groq Whisper / ElevenLabs Scribe)
    ├── clips_graded/            ← per-segment extracts with grade + fades
    ├── preview_proxy.mp4        ← PHASE 1 proxy (720p): o que se ITERA e se aprova
    ├── preview.mp4              ← corte final (1080p), encodado UMA vez APÓS a aprovação
    ├── clips_proxy/             ← extrações do proxy (descartáveis)
    ├── verify/                  ← montages / flagged-boundary views
    ├── captions.srt + chapters.txt   ← longform deliverables
    ├── final.mp4                ← delivered render (Phase 2 + 3, loudnorm'd)
    └── hyperframes/             ← projeto da Fase 2 (montado sozinho) E OS DADOS
        ├── edit-data.json       ← A EDIÇÃO
        ├── captions.json, caption-cues.json, track.json, segments.json
        ├── preview.mp4              ← link para o corte aprovado
        ├── pexels/ web/ brand/ film/ broll/, trilha.mp3
        ├── index.html           ← A COMPOSIÇÃO — gerada, nunca editada à mão
        ├── styles/              ← cópias de assets/styles/ (o look)
        ├── sfx/                 ← efeitos usados
        ├── compositions/        ← gráficos sob medida (a escotilha)
        └── renders/             ← saídas do motor
```

**Um destino só, e é a RAIZ do projeto.** Os dados moravam num `remotion/public/`
por duas razões que morreram juntas: o Remotion SERVIA essa pasta, e o nome
deixava uma sessão do fork de origem e uma do Avelin lerem o mesmo lugar. O
HyperFrames não serve nada — ele resolve `src`, `sfx/` e o vídeo a partir da raiz
do projeto. Enquanto as duas pastas coexistiram nenhum `src` de edit-data
resolvia: a composição procurava em `<proj>/<src>` e o pipeline escrevia em
`<edit>/remotion/public/<src>`. Projeto antigo é adotado sozinho na primeira
rodada do `phase2.py` — move o conteúdo, não sobrescreve nada.

## Setup

First-time install lives in `install.md`. On cold start just verify:

- `GROQ_API_KEY` resolves (env or `.env` at the Avelin repo root — this fork has its own). Groq Whisper `whisper-large-v3`; no diarization (every word is `speaker_0`).
- `ELEVENLABS_API_KEY` (optional) — used for LONG sources (>5 min, e.g. YouTube/course lessons) via ElevenLabs Scribe `scribe_v1`, since Groq's free tier chokes on long uploads. `backend=auto` (default) picks Scribe over 5 min when the key exists, else Groq; short clips stay on Groq. No key → long sources fall back to Groq. Ask for it lazily the first time a >5 min source shows up, write to `.env`.
- `whispercpp` (optional) — fully local transcription, no key, no upload cap, no network. Opt-in only: `auto` never picks it. Needs whisper.cpp built with a ggml model (auto-detected in `~/whisper.cpp`, or `WHISPERCPP_BIN`/`WHISPERCPP_MODEL` in `.env`). Offer it when the user has no Groq key or hits quota. **Text matches Groq; word TIMES don't** (measured: 66% of words inside a real speech region vs Groq's 97%, median drift 240ms). Phase 1 is unaffected — cut edges come from `speech_regions.py`. For Phase-2 karaoke captions, prefer Groq and say why.
- `ffmpeg` + `ffprobe` on PATH; Python deps (`uv sync`); Node 18+ for Phase 2. `yt-dlp` only for URL sources (`ingest_url.py`) — install lazily the first time a link shows up (`brew install yt-dlp` / `winget install yt-dlp.yt-dlp`).
- Fase 2: nada a instalar. `npx hyperframes@0.7.109` resolve do cache compartilhado (~365MB em `~/.cache/hyperframes`, uma vez para todos os projetos) e o projeto da sessão fica SEM `node_modules`. **Nunca carregue `remotion-best-practices`** — não é o motor desta skill.
- Lazy keys, ask on first use, write to `.env` (never to `<videos_dir>`): `PEXELS_API_KEY` (images), `GOOGLE_API_KEY`+`GOOGLE_CSE_ID` (brand/people images fallback), `TREBLO_API_KEY` (AI music).

Helpers live in `helpers/`, resolved relative to this SKILL.md (usually `~/.claude/skills/ave/`, or a symlink/junction pointing there). Run them as `uv run python helpers/<name>.py` — a bare `python` misses the `.venv` that `uv sync` builds.

## Helpers

Phase 1:
- **`ingest_url.py <url> --dest <videos_dir> [--section 12:00-25:30] [--max-height 1080]`** — edit from a link: yt-dlp → MP4 (≤1080p, ascii-safe filename) straight into the videos dir; from there it's a source like any other. `--section` downloads ONLY a time range of a longform source (keyframe-accurate) — the cheap way to clip minutes 12–25 of a 1h video. `--simulate` prints title/duration/resolution without downloading (confirm before big fetches; run those in the background).
- **`transcribe.py <video> --edit-dir <edit> [--language pt] [--backend auto|groq|elevenlabs|whispercpp]`** — word-level, cached. `backend=auto` (default): ElevenLabs Scribe for sources >5 min (when `ELEVENLABS_API_KEY` set), else Groq Whisper. Audio uploads as CBR 64kbps mono MP3 (~0.5 MB/min); oversized audio auto-chunks **by bytes**, so every chunk is guaranteed under Groq's 25 MB cap regardless of length. Chunks fetch **in parallel** with per-chunk resume cache and 5x backoff retries (provider blips don't restart the job).
- **`transcribe_batch.py <videos_dir> [--backend auto|groq|elevenlabs]`** — 4-worker parallel transcription for multi-take shoots; same per-file auto backend selection by length.
- **`pack_transcripts.py --edit-dir <dir>`** — transcripts → `takes_packed.md` (phrase-level, breaks on ≥0.5s silence). **The** reading view: 1/10 the tokens of raw JSON.
- **`transcript_audit.py <edit> [--recheck]`** — ONDE A TRANSCRIÇÃO MENTE, e é o portão que faltava antes do EDL. O Whisper **engole repetição**: o locutor gagueja, refaz a frase, e sai UMA passada limpa — o parágrafo lê perfeito e o `takes_packed.md` não tem como avisar. Também **troca palavra por palavra** ("trabalhar" → "avaliar", ambas plausíveis). Nenhum detector de TEXTO pega isso porque o texto está bem. Este pega por **densidade acústica** (região de fala com poucas palavras dentro = fala não transcrita; é física, não linguagem) e por **discordância entre as duas passadas** que o projeto já faz de graça. `--recheck` transcreve só a janela suspeita, isolada — sem contexto em volta o modelo não tem para onde suavizar e a repetição reaparece. Medido na série "170 Questões": achou 2 das 3 gaguejadas que o usuário só viu assistindo, uma delas com **0 palavras em 0,80s de fala**.
- **`cut_transcript.py <edit> -o transcripts/cut_mapped.json`** — o transcrito do CORTE por mapeamento do EDL, não por transcrever de novo. É o que a Fase 2 usa para legenda (veja a Hard Rule 15).
- **`speech_regions.py <video>`** — acoustic speech intervals via silencedetect. The source of truth for cut EDGES (Whisper times drift/stretch). Answers *where* speech is — never *how loud* it is.
- **`voice_levels.py <video> [--edit-dir <dir>] [--edl edl.json] [--drop-db 5]`** — the source of truth for speech LEVEL. Learns the noise floor (Ridler-Calvard intermeans, not a percentile) and the speaker's own median from the recording itself, then flags every phrase, sub-phrase run, and EDL range sitting ≥5 dB under that median and sizes a `gain_db` for each. Catches the failure nothing else sees: a whispered aside or a trailing-off sentence where every word is present, the transcript is perfect, `speech_regions` says "speech", `verify_cut` finds no pop and no dead air — and the viewer still hits a passage they cannot hear. **Run it in Phase 1 before writing the EDL.**
- **`detect_color.py <video> [--json]`** — resolves NORMAL vs LOG from the file instead of asking. Tier 1 metadata (HLG/PQ declare themselves; Apple Log's signature is ProRes 10-bit 4:2:2 + BT.2020 primaries + EMPTY transfer; vendor tags when present), Tier 2 image statistics when the metadata is silent — which is common, since a Sony shooting S-Log3 to H.264 often declares plain bt709 and any transcode drops the tags. Returns the profile, a **confidence**, the evidence, and the `grade` to apply (measured from the footage for non-Apple LOG). Only `confidence: low` should send you back to the user.
- **`render.py <edl.json> -o preview_proxy.mp4 --proxy --no-subtitles [--voice-master] [--keep-resolution] [--jobs N] [--no-jcut] [--jcut-lead N] [--jcut-tail-trim N]`** — per-segment extract (grade + fades, **parallel**) → **J-cut overlap assembly (default)** or lossless concat → optional voice master → loudnorm. Writes `jcut_timeline` into the EDL: the real output positions, which is what everything downstream must index off. Short-form fps is automatic: **30fps for 30fps+ sources, else 24** (longform keeps source fps via `--keep-resolution`). Set `edit-data.json` `fps` to match the resulting `preview.mp4`.
- **`verify_cut.py <edl.json> <preview.mp4> [--min-silence 1.2]`** — numeric self-eval: duration, per-junction pop/clipped-word probes, dead air, black frames, clipping, **and range level balance** (each range's RMS vs the median range; `LOW-LEVEL` under −4 dB). ~350 tokens of text instead of N images. The range-balance line is the convergence test for a `gain_db` fix — unlike `voice_levels`' run detector it compares a range against its peers rather than against a threshold it was selected by, so a corrected take actually stops being flagged.
- **`grade.py <in> -o <out>`** — grade presets/raw filters. **`--candidates "a=<filter>;b=<preset>;original=" --frame <t> -o cmp.png`** renders N looks on the SAME frame into one labeled montage.
- **`timeline_view.py <video> <start> <end>`** — filmstrip+waveform PNG for ONE flagged spot, not a scan tool.
- **`contact_sheet.py <video> --times t1 t2 … -o sheet.png`** — N frames in one labeled grid; the way to eyeball several moments **you already know**.
- **`watch_video.py <video> [--mode scene|keyframe|uniform] [--times t1 t2 …] [--start/--end] [--max-frames 24]`** — "what is IN this footage?" when you *don't* know where to look: scene-change detection (auto-fallback to uniform sampling on static/talking-head sources) + perceptual dedup (near-identical frames collapse — a held take becomes a handful of tiles) → labeled contact sheets in `edit/verify/watch_<stem>/`, one Read per sheet. Use for visual inventory of unknown material, eyeballing takes across sources, and surveying `preview.mp4` beyond verify_cut's numbers. `--times` pins transcript-cue frames: deictic moments from `takes_packed.md` ("olha isso", "como você pode ver") are LOW visual change and invisible to scene detection — pin them to decide B-roll/callout/zoom placement in Phase 2.

Phase 2/3 (see the track references for usage):
- **`phase2.py`** (Fase 2 inteira, um comando) · **`compose_shortform.py`** / **`compose_longform.py`** (a composição) · **`text_measure.py`** (largura com a fonte REAL do render) · **`backdrop_luma.py`** (variante de accent medindo o fundo) · **`sfx.py`** (confere nível e ataque de um efeito) · **`apply_edits.py`** (aplica os cortes salvos no editor)
- **`captions_words.py`** (legendas palavra a palavra, a base de todos os estilos) · **`face_track.py`** (eye-track JSON) · **`person_matte.py`** (RVM alpha matte; `uv sync --extra matting`) · **`pexels_search.py`** · **`wikimedia_images.py`** (no key, brands/people first choice) · **`google_images.py`** (fallback, mind rights) · **`captions_srt.py`** (longform .srt) · **`chapters.py`** (YouTube chapters) · **`treblo_music.py`** (AI soundtrack — pass a context-driven MUSICAL vibe: genre + instruments + tempo + mood, not SFX-y phrasing; auto-framed as a composed instrumental).

Interface:
- **`preview_server.py --root <edit> [--port 4820]`** — serves the standard preview interface (see the Preview interface section). App code lives at `assets/preview/` and is IMMUTABLE.

## Preview interface (standard — launch it at the start of every edit)

Every edit session gets the same interactive interface in the user's preview panel: a video-editor timeline (video track with filmstrip + audio track with waveform), a live playhead that scrubs the render in real time, per-take trim handles and take removal, and — from Phase 2 — caption and insert tracks. The layout follows the source aspect on its own: **vertical** sources put a tall player on the right with the transport + timeline on the left; **horizontal** sources keep the player stacked above the timeline. Dark glass, marca Avelin. **Never build a UI per session and never edit `assets/preview/`** — it is data-driven, like the styles in `assets/styles/`.

**Launch (do this when a session starts, even before the first render — the UI shows a waiting state):**
1. Write `<edit>/state.json`:
   ```json
   {"project": "Nome — C0000", "phase": 1, "video": "preview_proxy.mp4", "edl": "edl.json",
    "captions": "hyperframes/captions.json", "editData": "hyperframes/edit-data.json",
    "finalVideo": "final.mp4", "fps": 24, "message": "Fase 1 — cortando",
    "sourceDurations": {"C0000": 1038.5},
    "awaitingStyle": false,
    "style": {"edit": "split", "captions": "karaoke",
              "elements": {"tracking": false, "zoomAuto": true, "zoomCuts": true, "musicAI": true}}}
   ```
   (`captions`/`editData`/`finalVideo` only when they exist; the Fase-2 tab plays `finalVideo` — the render WITH captions/inserts — while Fase 1 plays the clean cut; `sourceDurations` lets the UI clamp take extensions; `awaitingStyle`/`style` drive the Estilo tab below.)
2. Ensure `.claude/launch.json` has the config (adjust `--root` per session). The
   server takes the port by flag only, so pass the harness-assigned `$PORT` and
   set `autoPort` — port 4820 is often held by another session:
   `{"name": "avelin-preview", "runtimeExecutable": "sh", "runtimeArgs": ["-c", "exec python3 <skill>/helpers/preview_server.py --root '<edit>' --port \"$PORT\""], "autoPort": true, "port": 4820}`
3. `preview_start` with name `avelin-preview`.
4. **Arm the watcher IN THE SAME TURN as `preview_start`** — never later, never
   "when the user starts editing":
   `Monitor(command="python3 <skill>/helpers/watch_edits.py '<edit>'", description="escolhas e marcações salvas no preview", persistent=true)`

   Without it the UI still writes `preview_style.json` / `preview_edits.json` and
   **nothing happens** — the user clicks Salvar, sees the confirmation toast, and
   waits for work that was never triggered. The failure is silent on both ends:
   they think they told you, and you never heard. `ps aux | grep watch_edits`
   is the one-second check when you are unsure.

**Keep state.json fresh** — bump `phase` and `message` at each milestone (cut rendered, cut approved, Phase 2 rendered…). The UI polls and hot-reloads by itself; waveform + filmstrip regenerate automatically when preview.mp4 changes.

The timeline shows one track per KIND: markers, captions, video, audio (the mix),
**A1 / A2** (the J-cut takes), **text** overlays (hook), **images** (inserts + any
data-driven CustomGraphics windows), soundtrack. Anything you leave in code instead
of data simply will not appear.

**A1 / A2 are folded inside the audio track**, opened by the caret on its chip —
they answer "where is the J-cut", which is a question you ask once, so they do not
sit on screen competing with the mix. They exist whenever the EDL carries a
`jcut_timeline`; the caret only appears then. The open/closed choice is remembered
across reloads (`localStorage`), so do not expect a fixed initial state.

Takes alternate between the two lanes, exactly as two audio tracks read in an NLE
— on a single lane an overlap is invisible, because two blocks sharing time just
look like one long block. The hatched orange head on each block is the lead: how
much voice arrives before that take's picture. Hover gives frames and tail trim.

Two structural constraints, learned the hard way:
- **Nothing in the ancestor chain of `.track-label` may have `overflow:hidden`** —
  the gutter mask rides `position:sticky` there, and an overflow ancestor makes a
  new scroll container and strands it. That rules out the usual max-height
  accordion; the reveal animates the blocks instead.
- **The panel's `pointerdown` must ignore the gutter.** It falls through to a
  scrub branch that calls `setPointerCapture` on the panel, which retargets the
  following click — a real click on a gutter control was swallowed entirely (while
  a programmatic `.click()` worked, which is what makes it confusing to diagnose)
  and the needle jumped to 0, since the gutter sits left of t=0.

**What the user can do in the UI:** scrub, trim take edges, delete takes, drag
insert/hook chips — and **mark correction ranges**: park the needle, press `M`
(or the IN button), move to the end of the problem, press `M` again — the note box
opens centred over the timeline — then type what should change. Many ranges per pass. Zoom: the slider is anchored on the needle, trackpad pinch
on the pointer. Shortcuts live behind the **?** button at the bottom right.

### The Estilo tab (between Fase 1 and Fase 2)

The cut is approved and nothing about the LOOK of Fase 2 is decided yet. **Do not
ask the style questions in chat** — set `"awaitingStyle": true` in `state.json`
and the UI opens its own tab, sitting between FASE 1 and FASE 2:

- **Tipo de edição** — `limpa` ("Nenhum": no split inserts, full frame throughout —
  **the default**, and the right pick for a talking-head cut or when the user will
  place images by hand later), `split` ("Dividida ↑", art on top), `split2`
  ("Dividida ↓", art on the bottom).
- **Cor de destaque** — `accent`, a hex. Sits BEFORE the text styles, because it
  is what they paint with. One spectral swatch (the OS picker) plus a hex field,
  synced both ways — no preset row. Only `realce`/`misto` headlines and the
  `stacked` caption paint an accent, so the save also carries **`accentUsed`**;
  when it is `false` the picked styles have none and the colour is not an
  instruction to invent a place for one.
- **Estilo de headline** — `outline`, `card`, `realce`, `misto`. Always two
  lines, size fitted to the text (see the track reference).
- **Estilo de legenda** — three animated (`karaoke`, `stacked`/"Empilhado",
  `scatter`/"Disperso") and three static (`simples`, `serifada`, `classica`).
- **Elementos da edição** — checkboxes: `tracking` (movimento de tracking),
  `zoomAuto` (automação de zoom in), `zoomCuts` (zoom in/out nos cortes),
  `flashCut` (flash na transição), `musicAI` (trilha sonora com IA), plus a
  free-text observation field.

Saving writes `<edit>/preview_style.json` (its OWN file — a style pick and a
timeline correction are different screens at different moments, and one shared
file would clobber the other) and `watch_edits.py` notifies you with the picks,
**what was left out**, and the observation. Then: build Fase 2 from exactly those
choices, **copy them into `state.json` as `style`**, clear `awaitingStyle`, and
delete `preview_style.json`.

Writing `style` back is not bookkeeping — it is what keeps the tab open. The tab
is enabled while `awaitingStyle` OR `style` is set, so the user can return, change
a caption style or tick one more element, and save again. That save arrives with
`"rerender": true` and the watcher says **REFAÇA a Fase 2** — re-render with the
new choices, don't treat it as a first pick.

**The catalog lives in `STYLE_CATALOG` (app.js), not in a session.** A new editing
or caption style is one entry there plus its implementation in the track
reference; adding it in chat only, for one project, makes it invisible to every
other project. What is in it today is the **short-form** vocabulary (dividida
↑/↓, karaokê/empilhado) — on a longform job the gate has nothing to offer
yet, so skip `awaitingStyle` and ask the layer questions in chat until longform
entries exist here.

**When the user saves timeline edits**, the UI writes `<edit>/preview_edits.json`
(never touches edl.json) and `watch_edits.py` notifies you automatically. To apply:
- `notes[]` — free-text correction requests, each with `start`/`end` on the draft
  timeline plus `renderedStart`/`renderedEnd` on the current `preview.mp4`, and the
  `phase` tab the user was on. Use the RENDERED pair to find the moment in the
  existing render. These are instructions in the user's words — read them, then do
  the edit they describe (re-cut, re-grade, swap an insert, fix a caption…).
- `edl.changes` / `edl.removed` — validate each new edge against
  `speech_regions.py` (warn if an edge clips a word — the user's intent wins, but
  say so), update `edl.json`, re-render, `verify_cut.py`.
- `editData` — insert/hook/behind timings → edit-data.json → re-render Phase 2.

Then delete `preview_edits.json` and update `state.json`.

---

# PHASE 1 — Clean cut + color grade

Goal: best take of every beat, cut on silence, graded image, clean `preview.mp4` for approval. No text, no graphics.

1. **Inventory + PAPEL DE CADA FONTE.** URL source? `ingest_url.py` first (`--section` when only a range of a longform video matters). `ffprobe` every source. `transcribe_batch.py` (or `transcribe.py`) → `pack_transcripts.py` → read `takes_packed.md`. Note dimensions/orientation and whether it looks flat/LOG. Material you can't picture from the transcript → `watch_video.py` for a one-Read visual survey.
2. **Pre-scan** `takes_packed.md` for verbal slips, mis-speaks, and dead-air-stretched words (Whisper stretches a word's end across silence — verify long "phrases" against `speech_regions.py`/waveform before trusting them). **Then rode DOIS auditores, porque o transcrito é cego de dois jeitos diferentes:**
   - **`transcript_audit.py <edit>`** — o transcrito é cego ao que ELE MESMO não escreveu. Gaguejo e repetição somem sem rastro: o parágrafo lê perfeito e falta uma frase inteira de áudio. Toda janela acusada é uma decisão a tomar ANTES do EDL. `--recheck` resolve as dúvidas transcrevendo só a janela, isolada.
   - **`voice_levels.py` em cada fonte** — o transcrito é cego ao NÍVEL, então um trecho inaudível lê igual a um normal. O que ele acusar: reforce com `gain_db`, ou corte o take.

   Os dois juntos cobrem o buraco que derrubou o #29 — três gaguejadas foram para o vídeo entregue porque nada olhava para "há fala aqui que ninguém transcreveu".
3. **Converse.** Describe what you see; ask questions shaped by the material (content type, target length/aspect, pacing, must-keep/must-cut). No fixed checklist.
4. **Detect the colour profile — do NOT ask.** Run `detect_color.py <source>`.
   The answer is in the file; asking put a measurable question on the user.
   - **`rec709` (normal)** → no grade. `"grade": ""`. A standard profile already
     carries its look; "improving" it loses the match with the user's other material.
   - **LOG / HLG / PQ** → apply the helper's `grade` field and say so in one line.
     Apple Log uses its approved preset; any other LOG gets an expansion **measured
     from that footage**, not a guessed vendor curve.
   - **`confidence: low`** → the ONLY case that still asks. It means the statistics
     are ambiguous — a bright, shadowless scene has the same lifted black floor as
     a LOG curve. Show what was measured, then ask.
   Still show the `--candidates` montage before committing a LOG grade: detection
   picks the curve, the user picks the look.
5. **Propose the cut strategy** (4–8 sentences: shape, takes, cut direction, grade direction, length estimate). **Wait for confirmation.**
6. **Escreva o EDL.** `edl.json` (schema below; editor sub-agent brief for multi-take). Set cut edges from `speech_regions.py`, not raw Whisper times.
7. **Encurte o ar morto — SEMPRE, antes do primeiro render.** `propose_breaths.py <edit> --apply`. Cortar no silêncio resolve o ar ENTRE tomadas; sobra o de DENTRO — a pausa no meio do próprio raciocínio, que nenhuma escolha de tomada remove porque está no meio da tomada escolhida. Num vídeo curto é o que mais custa retenção. A passada automática é conservadora de propósito (pausa >0,60s cai para 0,30s): tira o indefensável e para aí. O gosto fica para os chips da aba Transcrição, que descem até 0,15s — **o usuário refina o que sobrou, não faz a limpeza inteira à mão.** Diga em uma linha quantos respiros e quantos segundos saíram.
8. **Render do PROXY.** `render.py edl.json -o preview_proxy.mp4 --proxy --no-subtitles` (+`--voice-master` if wanted; longform: `--keep-resolution`). **The J-cut runs by default** — see below; you do not ask for it and you do not configure it per project. It applies per junction, only where a breath exists.
9. **Self-eval (numeric first).** `verify_cut.py edl.json preview_proxy.mp4` (longform: `--min-silence 1.2`). Clean → done. Flags → `timeline_view` ONLY the flagged junctions, fix, re-render the proxy. Cap 3 loops, then surface remaining flags to the user.
10. **Mostre o proxy e PEÇA A APROVAÇÃO, com todas as letras.** É o portão, e ele tem de ser dito — *"aprova a Fase 1?"* — não subentendido. **Nada depois disto começa sem um sim**: nem estilo, nem legenda, nem trilha. Itere sempre no proxy: cada rodada de correção o refaz, e a 720p/veryfast isso é 3,2× mais barato por segmento que o final. Diga que é proxy ao mostrar, para ninguém revisar a COMPRESSÃO em vez do corte.
11. **Aprovado → encode o final, uma vez.** `render.py edl.json -o preview.mp4 --no-subtitles` (mesmas flags do passo 8, menos `--proxy`). É o arquivo sobre o qual a Fase 2 compõe, e o `phase2.py` recusa rodar sobre o proxy. Aponte `state.json.video` para `preview.mp4` — **é isso que destranca as camadas do render na interface** — e regenere o `segments.json` a partir dos segmentos FINAIS: as contagens de frame de `clips_proxy/` descrevem outro render.
12. **Open the Estilo tab** — `"awaitingStyle": true` in `state.json`, and let the
   user pick the editing style, the caption style and the edit elements in the UI
   (see "The Estilo tab"). Do NOT ask this in chat. Only then read the track
   reference: **`references/shortform.md`** or **`references/longform.md`**.

## PHASE 2 — HyperFrames

**One command, start to finish.** It applies the Estilo pick, scaffolds the
project, composes, runs `check`, renders, loudnorms the delivery and writes the
paths the editor reads:

```bash
uv run python helpers/phase2.py <videos_dir>/edit
```

Everything below is what that command does, and what to do when it stops.

### The check is a gate, not a formality

`hyperframes check` runs before every render and BLOCKS on errors. It has
already caught three defects that would have shipped:

- `<audio>` without an `id` → the renderer never discovers it and **the video is
  silent**, with no error anywhere else.
- a composition with no timeline and no `data-no-timeline` → **45 seconds lost
  on every render** waiting for a registration that never comes.
- the hook under a split-screen art band → *text hidden beneath an opaque
  element*, caught before a single frame was rendered.

One tolerated exception, by name: `content_overlap` between the two `hl-line`
of a headline. Tight leading makes the line BOXES touch though the glyphs do
not — verified in the render. Any other error still blocks.

### What exists, and what is refused

| | |
|---|---|
| Legendas | `karaoke` `simples` `serifada` `classica` `disperso` `empilhado` |
| Headlines | `outline` `card` `realce` `misto` |
| Edição | `limpa` `split` `split2` |
| Câmera | zoom por corte, aproximação lenta, perseguição do olhar, flash |
| Curta | inserts, palavras em destaque, gráficos sob medida |
| Longform | B-roll, lower-thirds, cards de capítulo, callouts |
| Som | efeitos por evento + trilha |

**Not ported: the behind-the-subject layer.** A style outside the ported set is
refused BY NAME — never substituted.

`tracking` absorbs the zoom rather than animating alongside it: the translation
depends on the face point AND the zoom at that instant, so two separate
animations would fight over the same transform. It refuses to combine with
split-screen, which already pins the face by itself.

`empilhado` is the only style with a prep step (a director groups the words and
picks the orange serif accent). `phase2.py` generates it when missing.

### The two things that decide whether it looks right

**Measure the backdrop, not the intention.** `#FF6B1A` has MID luminance
(L=0.318): it only passes contrast against a dark or a bright backdrop, and sits
at 1.09–2.46 in between. `backdrop_luma.py` picks the palette variant per
window — canonical orange always, escalating only when it fails. But measured on
real footage, **choosing the colour is not enough**: the night-blue stroke is
what carries it (1.05 → 1.70 with the adaptive colour → 2.81 with the stroke).

**Animating `filter` REPLACES the whole value.** A shadow declared in CSS
vanishes on the first frame of any filter animation. Styles that animate blur
(`disperso`, `empilhado`) re-emit the shadow in every animated value. This bug
shipped twice before being understood — white words simply dissolved into a
white t-shirt.

### Sound

Effects live natively in the composition. **No re-mux.** No motor antigo a
entrega era remixada para corrigir o drift do áudio e isso DESCARTAVA os efeitos,
obrigando a refazer ~20 deles à mão no ffmpeg. Drift here is zero (measured: 9 windows
up to 780s, lag of exactly 0 samples), so they simply stay.

Two checks that only surface by LISTENING — the mix looks right and nothing is
heard. `helpers/sfx.py` does both: level (below −12 dB the effect disappears
under speech; the pack has two such files) and where the attack sits INSIDE the
file (`caption-click` has 158ms of lead-in silence — scheduled at the event, it
lands late). The compensation is measured at compose time, never tabled, so
swapping a file cannot reintroduce silent delay.

### Bespoke graphics — the escape hatch

Replaces `CustomGraphics.tsx`. Write `<projeto>/compositions/<id>.html` as a
COMPLETE composition document (its own `data-composition-id`, dimensions and
body) and reference it from `brollGraphics` in edit-data. Without the file the
composition renders WITHOUT ERROR and the absence only shows when watching — the
composer warns by name.

### Delivery

Loudness is re-measured on the OUTPUT (−14 LUFS), not inherited from `preview.mp4`:
Phase 2 adds a soundtrack and effects, so the final mix is a different one.


## Papel de cada fonte — e o tempo RESERVADO

Nem toda fonte é fala. Antes de escrever o EDL, decida o que cada arquivo É, porque
isso muda o que entra na Fase 1 e o que o usuário aprova.

| Papel | O que é | Ocupa tempo? | Onde entra |
|---|---|---|---|
| **fala** | a cabeça falante, a espinha do áudio | é o tempo | ranges do EDL |
| **multicam** | outro ÂNGULO do mesmo momento | não — troca a imagem | range com a mesma janela de áudio, fonte diferente |
| **insert** | toma a tela por alguns segundos (roleta, animação, gravação de tela) | **SIM** | reservado na Fase 1, montado na Fase 2 |
| **tela dividida** | arte/vídeo numa faixa, rosto na outra | **SIM** (muda o enquadramento) | reservado na Fase 1 |
| **B-roll** | corte de apoio sobre a narração | **SIM** | reservado na Fase 1 |
| **overlay** | cavalga a imagem sem substituí-la (logo, marca d'água) | não | Fase 2 |

**A regra que separa as duas colunas:** *ocupa tempo de tela* vai para a Fase 1 como
**RESERVADO**; *cavalga o tempo que já existe* espera a Fase 2. Legenda, headline,
zoom e cor são cosméticos — mudar de karaokê para empilhado não move um frame.
A roleta, o B-roll e a tela dividida **são a montagem**.

**Como reservar.** Escreva a entrada em `hyperframes/edit-data.json` já na Fase 1,
com `planned: true` e sem `src`. O editor carrega esse arquivo desde a Fase 1 e
desenha um chip tracejado — tempo guardado, mídia ausente. Nada é renderizado; o
portão continua de pé.

```json
{"inserts": [{"label": "roleta — giro + card 029", "start": 0.0, "end": 5.2, "planned": true}]}
```

**Por que isto existe.** Sem o reservado o usuário aprova uma montagem com buracos
que não consegue ver. Aconteceu no #29: a abertura foi escolhida *"para dar tempo de
tela pro giro da roleta na Fase 2"* — o corte foi construído em volta de um elemento
invisível, e a aprovação era de 57s de cabeça falante onde os primeiros segundos são
outra coisa. Se a roleta não coubesse no vão reservado, a descoberta viria depois do
portão, que é o que o portão existe para evitar.

**Quando o papel não for óbvio, PERGUNTE — e pergunte pelo uso, não pelo formato.**
Uma gravação de tela pode ser insert, tela dividida ou overlay, e o arquivo não diz
qual. Junte a evidência primeiro (`ffprobe`: duração, resolução, proporção, tem áudio?
`watch_video.py`: o que aparece) e faça UMA pergunta concreta, com as opções descritas
pelo que o espectador vê:

> Peguei três arquivos. Os dois DJI são você falando — o segundo é o refazer, e vou
> usar ele. O terceiro é uma gravação de tela de 55s com uma roleta girando que para
> no card 029. Como ela entra?
>   **(a)** toma a tela inteira por alguns segundos na abertura
>   **(b)** fica numa faixa em cima, com você embaixo (tela dividida)
>   **(c)** aparece pequena por cima da imagem, sem tapar você
>   **(d)** é só referência, não entra no vídeo

Nunca pergunte "qual o papel desta fonte?" nem ofereça os nomes da tabela: eles são
vocabulário desta skill, não do usuário. E não pergunte o que a evidência responde —
duração, resolução e se tem áudio se medem.

## J-cut — the default Phase-1 cleanup

Takes are OVERLAPPED, not butted. The outgoing take's audio runs to its natural
end; the incoming take's audio starts `lead` frames earlier **on its own track**
and the two are summed; the incoming PICTURE starts where the outgoing audio ends,
skipping `lead` frames of its own head. The voice arrives before the face.

Why it is the default: a straight concat leaves a beat of silence at every
junction — the outgoing take keeps its trailing pad and the incoming one starts
with its own. Measured on a real 3-take edit: **130ms and 140ms**. Small on paper,
a clear pause in the room. The J-cut removes it and the takes interlock.

Defaults, in `render.py`: **lead up to 5 frames**, **tail trim up to 2 frames** —
both are ceilings, not fixed amounts. Override per project with
`"jcut": {"lead_frames": N, "tail_trim_frames": N}`; turn it off with
`"jcut": false` or `--no-jcut` (single-range EDLs skip it anyway).

**The J-cut is per-junction, not per-project: it only happens where there IS a
breath.** The overlap falls on the outgoing take's trailing silence, so that
silence is the budget. Where two takes butt tight, pulling the incoming audio
back lands it on top of the outgoing take's last word — two voices over each
other for ~200ms, which reads as slurred speech rather than as an obvious defect,
and that is what makes it hard to diagnose. So the lead is capped the same way
the tail trim always was:

```
lead(i) = min(lead_frames, trailing_silence(i-1) − tail_trim(i-1) − 20ms)
```

The trim and the overlap eat the SAME silence, hence the subtraction — trim
first, and the lead may only use what is left. No breath, no overlap: that one
junction butt-joins while the rest of the edit keeps its interlock. The
measurement was already being run for the trim, so this costs nothing.
`render.py` prints which junctions overlapped and which butt-joined; the
per-take `⤶` note says the same thing per line.

Four things that are not obvious:

- **Tighten with the TAIL, not the lead.** A bigger lead also pushes the picture
  deeper into the incoming take's speech, which reads as entering mid-word. The
  tail trim tightens the seam and leaves the picture entry alone. Measured: 5f
  lead alone gave 62/46ms of interlock; adding a 2f tail trim doubled it to
  129/112ms with the picture still entering 140ms into the speech.
- **Both trims are measured, never blind.** `render.py` reads the silence
  actually present at the end of each range. A fixed 2 frames would eventually
  decapitate a word on a take that ends tight; a fixed 5-frame lead was landing
  the next voice inside the previous word whenever the takes ran together.
- **A hand-typed value wins outright.** `jcut_lead_frames` / `jcut_tail_frames`
  on a range are instructions, not suggestions — they skip the cap. Same
  principle both ways: the machine trims the edges the machine found; nobody
  touches an edge a person placed.
- **Sync is by construction:** `video_in = audio_in + lead` and
  `video_offset = audio_offset + lead`. Break that pairing and the take drifts.
  It holds per-take, so a variable lead does not disturb it.

`render.py` writes a `jcut_timeline` block into the EDL — the real output
positions. Everything downstream (preview timeline, `segments.json`, Phase-2
overlays) must index off THAT, not off the sum of the ranges: the J-cut output is
shorter than `Σ(end−start)`, so summing places every take after the first too late.

## Color grade

Reason about the image, don't preset-blind. Mental model ASC CDL: per channel `out = (in*slope + offset)**power`, then saturation. Applied per-segment at extraction (Hard Rule 7).

- **Iterate on ONE frame via a candidates montage, and let the user choose:**
  `grade.py <src> --candidates "punch=eq=contrast=1.15:saturation=1.25;suave=…;original=" --frame <t> -o edit/verify/grades.png` — one image, all looks labeled, side by side. Only render the full cut once the grade is locked.
- **Build from spaceless filters** so the string survives the EDL: `eq=…`, `colorbalance=…`, `colorlevels=…`. No `curves` with spaces (breaks filtergraph parsing).
- **The grade always runs at 8-bit.** `render.py` prepends `format=yuv420p` to the
  grade segment of the vf chain, because ffmpeg's `colorlevels` is broken on 9–14
  bit RGB — on a 10-bit source it collapses the frame to a constant TV black
  (measured `YAVG=64/1023`, `YBITDEPTH=1` on an iPhone Apple Log ProRes) while
  behaving correctly at 8- and 16-bit. `curves`, `colorbalance`, `hue` and `eq` are
  bit-depth-safe. Keep that guard in front of any new grade caller.
- **Standard/Rec.709** → light corrective or none. A user `.cube` goes first as `lut3d=`.

### LOG profiles — what `detect_color.py` is deciding

`detect_color.py` resolves this automatically; the table below is what it encodes
and what you need when reading its evidence or extending it. Probe by hand only
when the helper reports `low` confidence:

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,profile,color_transfer,color_primaries,color_space \
  -show_entries stream_tags=com.apple.proapps.logprofile -of default=nw=1 <source>
```

| What you see | Profile | Grade |
|---|---|---|
| `codec_name=prores`, `pix_fmt=yuv422p10le`, `color_primaries=bt2020`, `color_transfer=unknown`, encoder tag `Apple ProRes` | **Apple Log** | preset `apple_log` |
| `color_transfer=arib-std-b67` | HLG | tonemapped by `render.py`; light corrective only |
| `color_transfer=smpte2084` | PQ / HDR10 | tonemapped by `render.py`; light corrective only |
| Sony `slog3`/`s-gamut3`, Panasonic `v-log`, Canon `clog3` in the tags | that vendor's LOG | its own expansion — build one, then add it to `PRESETS` |

**Nothing in the file says "Apple Log".** The signature above IS the
identification — measured on a real iPhone ProRes file: BT.2020 primaries, a
10-bit 4:2:2 ProRes stream, and an EMPTY transfer tag. If you wait for a tag that
names the profile you will never find one, and an HDR-only check calls it plain SDR.

**Apple Log is the one that is already proven** (`apple_log` in `grade.py`,
approved 2026-07 on an iPhone ProRes talking head): cool, contrasty, skin rosy.
Two things about it that are not obvious:
- The file declares **BT.2020 primaries with an empty transfer tag**, so an
  HDR-only check reads it as ordinary SDR. `render.py`'s `wide_gamut_chain`
  converts it to Rec.709 before the grade — the preset assumes that already ran.
- `hue=h=-9` is load-bearing: expanding Apple Log pushes skin yellow-green, and
  the negative rotation brings it back. Rotating positive makes it worse.
- Its `colorlevels` **must** be fed 8-bit (see the 8-bit bullet above). LOG sources
  are the 10-bit ones, so this preset is exactly where the bug bites — and it bites
  silently: the `--candidates` montage grades an 8-bit frame and looks right, so
  only the rendered cut goes black. `verify_cut.py` catches it on the "black
  frames" line; don't dismiss that line as a false positive on a LOG source.

Still show the candidates montage and get a pick — a preset is a starting point,
not permission to skip the approval.
- **Skin is the guardrail.** The moment skin goes orange/magenta/clipped, back off. Check a mid-shot face at each step.
- **Relative tweaks** ("+1 exposure", "mais saturação") → nudge that one term, re-montage the same frame, show again.
- **Rec.709 is the only color space allowed to leave Phase 1.** `render.py` handles
  this (tonemaps HDR, converts wide-gamut SDR, tags every output bt709/tv) — but
  VERIFY on the rendered cut: `ffprobe -v error -select_streams v:0
  -show_entries stream=color_space,color_primaries,color_range preview.mp4` must read
  bt709 / bt709 / tv. Anything else means a second interpretation is still alive
  downstream: Chrome (the Phase-2 decoder, now HyperFrames) re-reads those tags and
  silently re-grades the image — typically ~1.2 gamma darker with a hue shift — so
  the Phase-2 render stops matching the cut the user approved. Phone/mirrorless
  sources routinely write bt2020 primaries with `color_transfer=unknown`; that is
  wide-gamut SDR, **not** HDR, and an HDR-only check will miss it.

## Voice EQ + mastering (optional Phase-1 audio polish)

Opt-in: `render.py … --voice-master` or `"voice_master": true` in the EDL. Runs after compositing, before loudnorm. Chain (`VOICE_MASTER_CHAIN` in render.py): highpass 80 → mud cut −2.5dB@200 → compressor (3:1, −20dB, makeup 3) → presence +2.5dB@3.2k → air +3dB@9k shelf → deesser → limiter 0.95.

Tune per voice: brighter → raise treble/3.2k; warmer → back those off, lift ~200Hz; more "radio" → lower threshold / raise ratio; more natural → ratio 2, threshold −24dB. **Verify:** `ffmpeg -i preview.mp4 -af astats -vn -f null -` → Flat factor 0, peak < 0dB; loudnorm summary ≈ −14 LUFS / TP ≤ −1. Then let the user hear it.

## Cut craft

- Silences ≥ 400ms are the cleanest cuts; 150–400ms usable with a check; < 150ms unsafe.
- Preserve peaks (laughs, punchlines, emphasis) — extend past a punchline to include the reaction.
- Every cut must work on audio AND video.

**Fine-comb the silences — Whisper times are NOT cut edges:**
- Onsets drift early (bakes dead air at a segment head); ends stretch across silence (a 4s "phrase" may be 1s of talk); restarts get collapsed into one stretched word (the doubled take is invisible in text but audible).
- Fix: edges from `speech_regions.py` — start → region onset −30ms, end → offset +50–80ms (the trail keeps the word's decay; cutting at the offset clips the last sibilant). Inside merged speech blocks, place the edge by eye on a fine `timeline_view`.
- If the user flags a gap/clip after render, re-run `speech_regions.py` around that timestamp — don't nudge blindly.
- **A stretched word can hide a false start, and the stretch also mis-attributes every word around it.** When "de" spans 6.16→8.64, the words the source transcript places on either side may belong to *different takes* — the speaker trailed off, paused, and restarted the whole sentence. The text shows one clean sentence; the audio holds two attempts.
- **Never conclude a range is missing content from the SOURCE transcript's word times.** Extract the exact range and transcribe it in isolation — no surrounding context for the LM to complete from. If the answer changes a deliverable (a caption rewrite, dropping a take), get a second opinion from the other backend (`--backend elevenlabs` vs `groq`); two models agreeing on an isolated clip is trustworthy, one model reading the full file is not.
- **Rotation:** phone clips are often stored landscape with a ±90° display-matrix; render.py handles it — don't force dimensions.

**Level the takes — presence is not audibility:**
- People drop their voice on asides, parentheticals and sentence tails ("além de, *claro*, …"). It sounds natural in the room and disappears on a phone speaker. The transcript is perfect, so nothing in the text pipeline flags it.
- Find it with `voice_levels.py --edl edl.json`: it reports each range's average AND the worst low run inside it, and suggests a `gain_db`. Size the gain off the **worst run**.
- Fix it per-range with `gain_db`, never with a global compressor.
- Confirm with `verify_cut.py`'s range-balance line. Target a ~2 dB spread between ranges — that is levelled. Driving it to 0 dB flattens the delivery and lifts room tone for nothing.
- Room tone is the real ceiling on a boost, not clipping. Before committing a large gain, compare the boosted take's internal pause against a pause elsewhere in the cut; if the boosted one is now the louder pause, back off.

## Editor sub-agent brief (multi-take selection)

```
You are editing a <type> video. Pick the best take of each beat and assemble
chronologically by beat, not clip order.
INPUTS: takes_packed.md; narrative context (2 sentences); speaker note;
expected structure (archetype or invent); verbal slips to avoid; target runtime.
Archetypes: launch (HOOK→PROBLEM→SOLUTION→BENEFIT→EXAMPLE→CTA); tutorial
(INTRO→SETUP→STEPS→GOTCHAS→RECAP); interview (Q→A→FOLLOWUP…); essay
(COLD-OPEN→THESIS→POINTS→COUNTER→CONCLUSION→CTA); vlog; or invent.
RULES: edges on word boundaries; pad 30–200ms; prefer ≥400ms silences; keep
unavoidable slips only if no better take (note in "reason"); if over budget,
drop a beat or trim tails and report.
OUTPUT (JSON array, no prose):
[{"source":"C0103","start":2.42,"end":6.85,"beat":"HOOK","quote":"…","reason":"…"}]
```

For a single long source (longform), the main context can pick cuts directly from `takes_packed.md`; for sources > ~30 min, delegate to the sub-agent so the full transcript never enters the main context.

## EDL format (Phase 1)

```json
{
  "version": 1,
  "sources": {"C0103": "/abs/path/C0103.MP4"},
  "grade": "eq=contrast=1.06:saturation=1.05",
  "voice_master": true,
  "jcut": {"lead_frames": 5, "tail_trim_frames": 2},
  "ranges": [
    {"source": "C0103", "start": 2.42, "end": 6.85, "beat": "HOOK",
     "quote": "…", "reason": "…", "gain_db": 0,
     "breaths": [{"at": 4.10, "to": 5.00, "keep": 0.15}],
     "chapter": "Only on longform section openers"}
  ],
  "total_duration_s": 87.4
}
```

`grade`: preset name, raw filter, or `"auto"` — normally whatever `detect_color.py`
returned. `chapter` fields feed `chapters.py` (longform).

`jcut`: optional. **Omit it and the J-cut runs with the defaults** (lead up to 5f,
tail trim up to 2f — both capped by the breath measured at each junction, so a
seam with no silence butt-joins by itself); `false` butt-joins everything
instead. After a render, `render.py` adds a
`jcut_timeline` array — the real per-take video/audio offsets in the output. That
block, not `Σ(end−start)`, is the timeline Phase 2 and the preview must use.

`breaths`: silêncios DENTRO do trecho para encurtar — o que o usuário marcou nos
chips da aba Transcrição. Cada entrada é `{at, to, keep}` em segundos da FONTE:
`at`/`to` são as bordas do silêncio e `keep` é o que fica (padrão 0,150s).

**Escreva a intenção, não a aritmética.** `render.py` expande cada respiro em
dois trechos antes de qualquer outra coisa olhar os ranges, e faz três coisas que
um recorte à mão erraria:

- **Fixa a emenda que acabou de criar** (`jcut_tail_frames: 0` no pedaço que
  fecha, `jcut_lead_frames: 0` no que abre). Sem isso o J-cut trata a emenda nova
  como qualquer outra e come o piso: com 150ms preservados ele apara 67ms de
  cauda e sobrepõe 33ms de lead — **sobram 50ms**, um terço do que a pessoa
  escolheu, sem aviso nenhum. O aparo original do range continua valendo para o
  ÚLTIMO pedaço e o lead original para o PRIMEIRO: só as emendas do meio são
  fixadas.
- **Roda ANTES do alinhamento de frame.** Um range que nasce depois do snap chega
  à extração com bordas fora do frame, que é o erro que o snap existe para
  evitar.
- **Valida e morre pelo nome.** Respiro fora do trecho ou invertido produziria um
  range de duração negativa, e o ffmpeg aceita isso devolvendo segmento vazio: o
  corte encurta e nada avisa. Respiro que já é menor que o piso é ignorado com
  uma linha, não aplicado.

**`at`/`to` vêm do detector ACÚSTICO, não do Whisper.** O `preview_edits.json`
manda `srcFrom`/`srcTo` (tempos de palavra) para você LOCALIZAR o respiro; as
bordas do corte se tiram do `speech_regions.py`, como toda borda de corte nesta
skill. O Whisper estica o fim da palavra por cima do silêncio, então cortar no
carimbo dele encurta o respiro por um valor que ninguém pediu.

Cada respiro soma um trecho — 15 respiros num corte de 20 tomadas dá 35
segmentos para extrair. No proxy isso é barato; é mais uma razão para os
respiros serem resolvidos antes do encode final.

`gain_db`: per-range level correction in dB, sized by `voice_levels.py`. Applied at
extraction, before the edge fades, with a limiter on any boost so a loud syllable
inside a quiet take cannot clip. This is the fix for an under-level take — not a
global compressor, which would pump the good takes to rescue the bad one.
Cap around +12 dB: past that the room tone rises with the voice and the take
starts sounding like a different microphone.

---

# PHASE 2 + 3 — read the track reference (after the gate)

The cut is approved and the user picked the style in the UI (`preview_style.json`)
→ load **one** file and build exactly what was picked:

- **Vertical / Reels / TikTok / Shorts → read `references/shortform.md`.** Karaoke captions, static hook headline, dynamic camera, inserts, behind-the-subject, SFX, soundtrack.
- **Horizontal / YouTube / tutorial / vlog → read `references/longform.md`.** Retention cut is there too (read it BEFORE Phase 1 on longform jobs), B-roll, lower-thirds, chapter cards, callouts, .srt + chapters, soundtrack.

Both tracks: `helpers/phase2.py <edit>` faz tudo — aplica a escolha da aba Estilo, monta o projeto, compõe, roda o `check`, renderiza, normaliza a loudness e devolve os caminhos ao editor. A edição inteira é o `edit-data.json`; nada de código por sessão fora dos gráficos sob medida em `compositions/`. **Não carregue a skill `remotion-best-practices`.** Não é o motor desta skill.

## Memory — `project.md`

Append one section per session at `<edit>/project.md`:

```markdown
## Session N — YYYY-MM-DD
**Phase reached:** …  **Strategy:** …
**Decisions:** takes, cuts, grade (LOG?), layer choices + why
**Outstanding:** deferred items
```

On startup, read it if it exists and summarize the last session in one sentence before asking whether to continue.

## Anti-patterns

- Starting Phase 2 before cut approval (the gate is a Hard Rule).
- Asking the style questions in chat, or starting Phase 2 before the pick lands.
  The gate screen exists so the user SEES what each style does — a chat list of
  names asks them to choose blind. Set `awaitingStyle` and wait for
  `preview_style.json`.
- Treating an unchecked element as "não pediu". It is an explicit NO: the user
  looked at "Movimento de tracking" and left it off. `watch_edits.py` prints the
  `fora:` line for exactly this reason.
- Hardcoding `#ff5200` (or any accent) in the template. The Estilo tab lets the
  user pick it, so a literal makes the preview show their colour and the render
  show orange — worse than not offering the choice. Feed `accent` into
  `hook.accent` + `captions.accent`.
- Changing a caption's look in the template without changing its preview in
  `app.js` (`buildKaraokeDemo` / `buildStackedDemo`). The gate's previews render
  the real faces, sizes and motion, scaled from 1080-wide — that is the whole
  reason the user can choose by looking. A preview that lies about the style is
  worse than no preview.
- Reading `transcripts/*.json`, `captions.json`, `track.json`, `segments.json`, or template TSX into context — machine data; read `takes_packed.md`/helper output instead.
- Editing `src/Main.tsx` — the template is data-driven; the JSON is the edit.
- Hardcoding a bespoke graphic's timings inside `CustomGraphics.tsx`. Put the
  windows in an `edit-data.json` array (a key the template ignores, e.g.
  `splitInserts`) and map over it — otherwise the graphic is invisible to the
  preview timeline and the user cannot see or retime it.
- Re-rendering Phase 1 without regenerating `segments.json`. Every Phase-2
  overlay that must land on a cut is indexed off that file; stale, it is off by
  frames and nothing errors. Worse, a `VIDEO_LAG`-style constant can absorb the
  first frame of the drift and make a broken file look correct at the one
  boundary you happen to check.
- `timeline_view` on every boundary — run `verify_cut.py` and image ONLY the flags.
- N single-frame images when one `contact_sheet.py` / `--candidates` montage answers it.
- Setting cut edges from Whisper word times (drift/stretch/collapsed repeats) — use `speech_regions.py`.
- Judging audio by the transcript. A perfect transcript says nothing about level: Whisper reads a whisper fine, the viewer does not. Run `voice_levels.py` on every source in Phase 1.
- Rewriting a caption, or telling the user a sentence broke, on the strength of the source transcript's word times. Transcribe the isolated range first — a stretched word mis-attributes its neighbours and an under-level passage is usually a false start the speaker already re-took.
- Sizing a range's `gain_db` off the range average — a range holding a whispered clause plus a normal one averages out to "fine" while the whisper stays inaudible. Size it off the WORST low run inside the range (`voice_levels.py --edl` does this).
- Chasing `voice_levels`' low-run numbers to zero on a corrected render. Runs are SELECTED for being under the threshold, so the passage you just fixed still lists its decay tails. Convergence is `verify_cut.py`'s range-balance line; a ~2 dB spread between ranges is a finished job, 0 dB is over-flattened delivery.
- Fixing an under-level take with a global compressor or `--voice-master` — that pumps the takes that were already fine. Use per-range `gain_db`.
- Cutting exactly at a word's offset (clips the sibilant) — leave the 50–80ms trail.
- Committing a grade without the one-frame candidates montage + user pick.
- Shipping a `preview.mp4` that is not tagged bt709/tv — Phase 2 will re-interpret it and the approved grade drifts.
- Re-muxing the delivery audio "to fix drift". That was the OLD engine's workaround and it DISCARDED every baked SFX. Measured on HyperFrames: drift is zero across 780s, so the effects live in the composition and the re-mux must not come back.
- Judging A/V sync with short correlation windows — speech is quasi-periodic and a 2–3s window happily locks onto the wrong syllable, inventing a drift. Use 15s+ windows, and remember a PARTIAL render cannot show drift that accumulates over the full timeline.
- Burning captions/overlays with ffmpeg/PIL — Phase 2 is HyperFrames-only.
- Trusting an SFX file without measuring it: two files in the pack are inaudible under speech, and several have >140ms of silence before the attack.
- Declaring a shadow only in CSS on a style that animates `filter` — the animation replaces the whole value and the shadow vanishes on frame one.
- Asking "NORMAL ou LOG?" — that is `detect_color.py`'s job now. Ask only on `confidence: low`.
- Butt-joining the takes GLOBALLY. The J-cut is the default; `--no-jcut` is a deliberate exception, not a shortcut. A junction that butt-joins on its own because there was no breath is the feature working, not a regression.
- Tightening a J-cut seam by raising the lead. That buys tightness by shoving the picture deeper into the incoming take's speech. Trim the outgoing TAIL instead.
- A fixed tail trim. It must be bounded by the silence actually measured at that range's end, or it eventually cuts a word off.
- `adelay` in milliseconds when placing overlapped audio, or `-shortest` on the mux. `adelay`'s integer-ms rounding leaves the mix a fraction short of the video and `-shortest` then amputates whole FRAMES of picture — and whether it bites depends on which way the numbers round, so it passes by luck until it doesn't. Delay in samples (`=NS`), and pin the length with `-t`.
- Indexing Phase 2 off `Σ(end−start)` when a `jcut_timeline` exists — the J-cut output is shorter, so everything after the first take lands late.
- Assuming the color profile without running the detector.
- Re-transcribing cached sources; re-rendering Phase 1 when only Phase 2 changed.
- Launching the preview without arming `watch_edits.py` in the same turn. This
  is the one failure mode where the user reasonably believes they handed you a
  decision and you never got it — the toast says saved, the file is written, and
  no one is reading it.
- Building a per-session preview UI — launch the standard interface and feed it `state.json`. (Improving `assets/preview/` itself IS allowed when the user asks for a UI change; it is shared, so the improvement lands for every project.)
- Applying `preview_edits.json` blindly — validate new edges against `speech_regions.py` first (flag clipped words to the user).
- Assuming what kind of video it is. Look first, ask second, edit last.
