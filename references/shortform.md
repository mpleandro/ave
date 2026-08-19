# SHORT-FORM track (Reels / TikTok / Shorts) — Phase 2 + 3 reference

Read this file when the video is vertical short-form and the Phase-1 cut is
approved. Everything here rides on the **data-driven template** at
`assets/shortform/` — the code is immutable; a video is described by ONE JSON.

## The style (the proven default)

- **Frame rate:** render at **30fps when the source is 30fps or higher** (natural
  motion, matches Instagram/TikTok/Shorts capture); only slower sources use 24.
  `render.py` picks this automatically for `preview.mp4` — then set `edit-data.json`
  `fps` to the SAME value as `preview.mp4` (ffprobe it) so the Phase-2 render matches.
- **Base:** 1080×1920 (fps per the rule above), `<OffthreadVideo src=preview.mp4>` with the **dynamic
  camera**, whose three parts are separate picks on the Estilo tab: hard zoom per
  cut segment (`zoomCuts`, ~1.10–1.22, cycles), slow push-in (`zoomAuto`,
  +0.04/segment), clamped eye-tracking (`tracking`, target upper third, never
  reveals an edge). `zoomCuts` is what makes a talking head feel edited — if the
  user turns everything off, say what they lose and build it anyway.
- **Visual hook (first ~4s):** static copywriting headline, **always two lines**
  with the size fitted to them (see "Headline styles"). Always on.
- **Captions:** six styles — three animated (**karaoke**, **stacked**, **scatter**)
  and three static (**simples**, **serifada**, **classica**). The user already
  picked one on the Estilo tab; see the "Caption style" section.
  Karaoke: one line ≤3 words, words rise from below, Poppins Black, lower third,
  `measureText` fit into **SAFE_WIDTH 720** (~180px each side — clears
  Instagram/TikTok's right action rail; verified on a real screenshot). Never
  rely on `nowrap` alone.
- **Inserts (upper zone):** rounded-card + shadow motif synced to spoken nouns,
  slow Ken-Burns. Pexels for concrete objects; **bespoke motion graphics** when
  a word names something animatable (timeline for "cortes", typewriter sheet
  for "roteiro" — worked examples in `src/CustomGraphics.tsx`).
- **Zones:** inserts/graphics upper third, captions lower third, face clear.
  Minimalist; accent `#33e0a3`.
- **Audio:** whoosh ~0.09 on card entrances, pop ~0.12 on shapes, music ~0.12,
  and ALWAYS a final loudnorm pass (voice+music+SFX summed will clip). The
  shared sfx pack (`public/sfx/`) also ships `click1`/`click2` (element pops) and
  `tictac` (clocks/countdowns) — trigger any at a local frame by wrapping
  `<Sfx src="click2.mp3" volume={0.7}/>` in a `<Sequence from={frame} layout="none">`.

## Workflow

**Read `<edit>/preview_style.json` first — it IS the brief.** The user chose it on
the Estilo tab at the end of Fase 1; every key maps to something here:

| Pick | What it means |
|---|---|
| `edit: "limpa"` | rotulado **"Nenhum"** e **o padrão** — NO split inserts, full frame throughout. See that section |
| `edit: "split" \| "split2"` | **"Dividida ↑"** / **"Dividida ↓"** — the split-screen variant below; every image insert uses it |
| `headline: "outline" \| "card" \| "realce" \| "misto"` | `hook.style` in edit-data.json |
| `captions: "karaoke" \| "stacked" \| "scatter" \| "simples" \| "serifada" \| "classica"` | `captions.style` in edit-data.json (+ the director step for stacked) |
| `accent` (hex) | `hook.accent` + `captions.accent`. Only `realce`/`misto`/`stacked` paint it; `accentUsed:false` means the picked styles have none |
| `elements.tracking` | `face_track.py` + `track.json`; OFF → skip it, fixed frame |
| `elements.zoomAuto` | the slow push-in inside each segment (`+0.04/segment`) |
| `elements.zoomCuts` | the hard zoom change ON each cut (~1.10–1.22, cycles) |
| `elements.flashCut` | `transitions[]` in edit-data.json — see "Flash na transição" |
| `elements.sfx` | **"Aplicar efeitos sonoros"** — os efeitos LOCAIS de `assets/sfx/`, disparados pelos eventos da composição (entrada de cartão, flash, deixa em destaque). Ligado por padrão. OFF → nenhum efeito entra, mesmo havendo evento. Não custa token nem espera: é o caminho barato, e vem antes da geração por IA na lista por isso |
| `elements.musicAI` | **"Gerar com IA"** — Phase 3 via `treblo_music.py`; OFF → deliver with voice only. Custa token e minutos |
| `note` | free text — read it, it overrides the defaults above |

An unchecked box is an explicit NO, not a silence. Copy the picks into
`state.json` as `style`, clear `awaitingStyle`, delete `preview_style.json`.

**`helpers/phase2.py <edit>` faz os passos 1 a 5 sozinho.** O que segue é o que
ele faz por dentro — leia quando ele parar, não para executar à mão.

1. **Scaffold.** `phase2.py` monta `<edit>/hyperframes/` e linka o `preview.mp4`. Não
   existe mais template para copiar: a composição é GERADA por
   `compose_shortform.py` a partir dos dados.
2. **Dados na RAIZ do projeto (`<edit>/hyperframes/`, sem `public/`):**
   - `transcribe.py preview.mp4 --edit-dir <edit>` → `transcripts/cut.json`
     (cut times are already on the output timeline — never map the source EDL)
   - `captions_words.py --transcript transcripts/cut.json -o hyperframes/captions.json`
   - **Caption style** — from the Estilo tab pick. `stacked` ALSO needs
     `caption_style.py --transcript transcripts/cut.json -o hyperframes/caption-cues.json`
     plus `captions.style:"stacked"` (see the "Caption style" section).
   - `face_track.py preview.mp4 -o public/track.json` — **only when
     `elements.tracking` is on.** Off, the frame stays put — but the file must
     still EXIST: the template imports it statically and the bundle fails to
     build without it ("track.json doesn't exist" out of webpack, not a runtime
     warning). Write a neutral one instead: every point pinned to the camera
     target, so the follow has nothing to correct.
     ```bash
     python - <<'EOF'
     import json, pathlib
     ed = json.loads(pathlib.Path('public/edit-data.json').read_text())
     n = round(ed['durationSec'] * ed['fps'])
     tx, ty = ed['camera']['targetX'], ed['camera']['targetY']
     pathlib.Path('public/track.json').write_text(json.dumps(
         {"fps": ed['fps'], "width": ed['width'], "height": ed['height'],
          "count": n, "points": [[tx, ty]] * n, "neutral": True}))
     EOF
     ```
   - `public/segments.json` — cumulative cut boundaries **measured from the
     encoded segments' frame counts, never summed from the EDL's seconds**.
     **Regenerate it after EVERY Phase-1 re-render.** A stale segments.json is
     invisible: the render succeeds, the overlays look plausible, and every cut
     is off by a frame or three. Measured on this project after a re-grade — the
     file still carried EDL-summed times and drifted +1 frame by the 3rd cut and
     +3 by the 20th, while `VIDEO_LAG` quietly absorbed the first frame of it and
     made the error look fixed. The mechanism: ffmpeg quantises each segment to
     whole frames, so EDL arithmetic drifts a fraction of a frame per cut and the
     error ACCUMULATES. Anything that must land on a cut then sits visibly early.
     ```bash
     python - <<'EOF'
     import subprocess, glob, json, pathlib, sys
     # TWO assertions, because globbing a directory is only as good as the
     # directory. `_v.mp4` first: the J-cut writes video-only segments and a bare
     # glob also matches butt-join leftovers. Then check the COUNT against the EDL
     # and the SUM against preview.mp4 — a re-render with fewer ranges leaves the old
     # higher-numbered segments behind, and that gave segments.json 9.23s for a
     # 7.57s video. It renders clean and every overlay lands wrong.
     segs = sorted(glob.glob("clips_graded/seg_*_v.mp4")) or sorted(glob.glob("clips_graded/seg_*.mp4"))
     nranges = len(json.loads(pathlib.Path("edl.json").read_text())["ranges"])
     if len(segs) != nranges:
         sys.exit(f"{len(segs)} segments for {nranges} ranges — clips_graded is dirty")
     cum, t = [0], 0
     for f in segs:
         n = int(subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
             "-count_frames","-show_entries","stream=nb_read_frames",
             "-of","default=nw=1:nk=1",f], capture_output=True, text=True).stdout)
         t += n; cum.append(t)
     real = int(subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
         "-count_frames","-show_entries","stream=nb_read_frames",
         "-of","default=nw=1:nk=1","preview.mp4"], capture_output=True, text=True).stdout)
     if t != real:
         sys.exit(f"segments sum {t}f != preview.mp4 {real}f — do not ship this file")
     fps = 30  # match preview.mp4
     json.dump({"segments": [{"start": round(cum[i]/fps,4),
                              "dur": round((cum[i+1]-cum[i])/fps,4)}
                             for i in range(len(cum)-1)]},
               open("hyperframes/segments.json","w"), indent=2)
     EOF
     ```
   - **VERIFY segments.json against the picture — do not trust it.** `scdet`
     scores every frame by how much it differs from the one before, so a hard
     cut is a spike. The spike frame in `preview.mp4` must equal
     `round(segments[i].start * fps)`:
     ```bash
     ffmpeg -v info -i preview.mp4 -vf "select='between(n,344,358)',setpts=N/30/TB,scdet=threshold=0" \
       -an -f null - 2>&1 | grep scd.score
     ```
     In the RENDER the same cut lands one frame later — that is the
     `OffthreadVideo` lag `VIDEO_LAG` exists for. Both numbers together are the
     proof: cut spike at frame F in preview.mp4, at F+1 in the render, overlay
     window opening at F+1.
   - `pexels_search.py "<query>" --out-dir hyperframes/pexels --count 3 --orientation portrait`
3. **Write `hyperframes/edit-data.json`** — the whole edit in one file:
   durationSec (exact ffprobe of preview.mp4), camera zooms, hook lines/logo/sign,
   captions config, inserts[], behind[], soundtrack (leave `enabled:false` until
   Phase 3). Every `src` in it is relative to `hyperframes/`.
4. **Verify with stills, batched:** one contact sheet, not N images —
   `contact_sheet.py <render> --times t1 t2 t3 -o sheet.png`. The hook still goes
   to the user for approval before the full render.
5. **Render + deliver:** `phase2.py` runs `hyperframes check` (a gate — it blocks
   on errors), then `hyperframes render`, then loudnorms to `edit/final.mp4`.

Never hand-edit `hyperframes/index.html` — it is generated on every compose and
your edit is gone at the next run. Bespoke graphics go in
`<projeto>/compositions/<id>.html`, mounted as sub-compositions.

## Headline layouts — N linhas, corpo ajustado

Onze looks via `hook.style`, escolhidos na aba Estilo. Os quatro originais:
**`outline`** (branco + traço preto grosso), **`card`** (cartão escuro
arredondado, CAIXA ALTA), **`realce`** (cada linha numa tarja sólida de
destaque), **`misto`** (linha 1 leve, linha 2 pesada no destaque). Os sete
novos:

| id | o que é |
|---|---|
| `bloco` | linhas em caixa alta ALTERNANDO principal/destaque, entrelinha esmagada — o texto vira massa sólida |
| `etiqueta` | uma tarja pequena de rótulo (a PRIMEIRA linha) sobre a frase grande |
| `manuscrito` | manuscrita por cima encaixando na caixa alta pesada. **O único que usa as DUAS famílias** — é ele que justifica o par |
| `gigante` | a última linha é uma palavra ocupando a largura inteira; o resto pequeno em cima |
| `relevo` | caixa alta com extrusão DURA no destaque; preenchimento em degradê |
| `grifo` | cada PALAVRA com sua tarja (o `realce` faz por linha) |
| `contorno_duplo` | linha vazada em cima, cheia embaixo — o vazado deixa a imagem passar |

### A quebra: o `/` manda

**" / " no `hook.text` quebra a linha ali**, e define quantas linhas existem.
Sem barra, a divisão em DUAS é equilibrada pela largura MEDIDA. Foi o que
destravou os layouts de três linhas e os de linha herói: `sizes` dá o corpo por
linha, e `heroLast` faz a última ser medida sozinha contra a largura inteira —
no ajuste conjunto uma palavra curta ficaria pequena e uma longa puxaria todas
as outras para baixo com ela.

**Caixa alta é do CÓDIGO (`upper`/`upperLines`), nunca do CSS.**
`text-transform` aplica depois da medição: mede-se a minúscula e desenha-se a
maiúscula, que é mais larga. O `manuscrito` e o `gigante` estouraram o quadro
exatamente assim, sem erro nenhum, antes de a regra existir.

### As duas fontes (`hook.fontMain` / `hook.fontAccent`)

Catálogo curado do Google Fonts em `variants.json` → `gfonts`, com os pesos que
cada família TEM. Duas armadilhas, ambas silenciosas:

- **Peso inexistente derruba a folha inteira.** A API v2 devolve erro em vez de
  CSS; a headline sai na fonte de sistema com a largura toda diferente da
  medida. O peso pedido pelo layout é grudado no mais próximo que existe.
- **Família EMPACOTADA** (`gfonts[].file` — hoje a Bebas Neue, que o cache do
  HyperFrames não serve) fica FORA da consulta ao Google e entra por
  `@font-face` apontando para `styles/fonts/<file>`. Sem isso o render
  dependeria de a fonte estar instalada na máquina de quem renderiza.

- **Família LOCAL** (`k == "local"`) é uma fonte instalada na máquina, indexada
  por `local_fonts.py`. É o caminho para a tipografia da marca do usuário. Fica
  fora da consulta ao Google pelo mesmo motivo da empacotada, e o render a
  resolve pelo nome. **Um projeto com fonte local não sai igual em outra
  máquina** — o arquivo não viaja no `edit-data.json`. Para algo que precise
  sobreviver à troca de computador: catálogo do Google, ou empacote o arquivo.

Só os layouts com `fontRole` desenham a segunda família.

### As duas cores (`hook.color` + `hook.accent`)

`color` é a principal, `accent` o destaque; cada layout declara em `paint` quem
recebe qual. **O degradê é regra do MODELO, não escolha do usuário**: onde
existe (`gradient`), a cor escolhida é a parada de cima e a de baixo é DERIVADA
dela por `amount`. Pedir as duas pontas devolveria degradê sujo com o dobro de
perguntas.

A marca do usuário vive em `~/.avelin/brand.json`, fora do projeto — escreva ali
quando descobrir cor/fonte da pessoa por outro caminho.

## Estilos de legenda MEDIDOS do CapCut

Quatro estilos cujos números não foram escolhidos: foram extraídos dos pacotes
do CapCut instalado por `helpers/capcut_captions.py`.

| id | efeito de origem | curva |
|---|---|---|
| `popBloco` | Multiline Combo | escala 0→120%→100% em 403 ms |
| `popLinha` | Multi-Line | *a mesma* |
| `pop` | Bounce Out | *a mesma* |
| `revelar` | Multiline | varredura 0→100% em 1733 ms |

**Os três primeiros têm keyframes IDÊNTICOS byte a byte** — verificado por diff
dos pacotes. A diferença não está neles: está no AGRUPAMENTO, ou seja no que
estoura junto (palavra, linha, bloco). Por isso um `pop.css`/`pop.js` só, com o
grupo como classe (`grupo-palavra` etc.), e não três cópias.

Dois defeitos que só apareceram no render, e que voltam se alguém reescrever:

- **`Text_Percent_Start` é porcentagem de CARACTERES em ordem de leitura**, não
  posição na tela. Uma máscara única sobre o bloco corta as duas linhas no
  mesmo x, e meia palavra da linha de baixo aparece antes de a de cima
  terminar. A máscara é por palavra, com deslocamento em caracteres.
- **A pena do degradê vem ATRÁS da frente da varredura.** Adiante dela, em 0%
  sobra um fio da palavra ainda oculta — e como traço e sombra transbordam a
  caixa, o fio vira um risco solto ao lado do texto.

**Três lugares por estilo, e esquecer um é silencioso:**

| onde | o quê | sintoma se faltar |
|---|---|---|
| `STYLE_CATALOG.captions` + `PORTED` (app.js) | o cartão | aparece como "EM BREVE" |
| `CAP_BUILDERS` (app.js) | a prévia animada do cartão | cartão vazio |
| **`CAP_CSS` + um ramo em `renderLive`** | a legenda AO VIVO sobre o vídeo | **texto cru, branco, no topo** |
| `compose_shortform.py` | o render | escolhe e não sai no vídeo |

O terceiro é o que mais escapa, porque não dá erro nenhum: `liveCss(undefined)`
sai calado e o estilo cai no ramo genérico de legenda estática.

Não portado: **Zoom Switch**. É o único num formato diferente (binário do Lynx
Studio, `.lsanim`, com aberração cromática e desfoque gaussiano). Aproximar é
possível; entregar a aproximação com o nome do original, não.

### The accent colour (`accent` in preview_style.json)

O accent é o mesmo da headline e da legenda; o padrão DO PRODUTO é o
vermelho `#ff3b30` — é o que um usuário novo recebe ao instalar a Avelin.
A marca de QUEM edita mora em `~/.avelin/brand.json` (fora do repo) e
vence o default em todo projeto novo; o laranja `#FF5200` é a marca
PESSOAL do dono desta instalação, não o padrão do produto. The user picks it on the Estilo tab and it
arrives as a hex — set it on **`hook.accent`** and **`captions.accent`** in
edit-data.json so headline and caption stay the same colour. `preview_style.json`
also carries `accentUsed`: when it is `false`, the picked styles have no accent
and the colour is not a request to find somewhere to put one.

Hardcoding `#ff5200` anywhere in the template re-breaks this — the preview will
show the user's colour and the render will show orange, which is worse than not
offering the choice.

**Escreva `hook.text` como UMA frase, e use " / " onde quiser a quebra.** Sem
barra, o texto é redividido em duas linhas equilibradas pela largura MEDIDA e o
corpo é ajustado à mais larga. Três linhas encolhem o tipo — o que é uma escolha
legítima em `bloco` e `grifo`, e um erro nos layouts de duas.

- The break is measured, not counted: "É assim que vai" (4 words) and "ficar a sua
  headline" (3 words) are nearly the same width. Counting words breaks it wrong.
- **`fontSizePx` is a CEILING, not a fixed size.** As a hard override it defeats
  the whole feature: at a size the text cannot fit in, the line wraps and you are
  back to three lines. Measured, not guessed — the uppercase `card` style did
  exactly that at an inherited `fontSizePx: 66`.
- Per-style geometry (weights, cap, safeWidth, lineHeight, paddingTop) lives in
  `HL_STYLES` in `src/Main.tsx` **and is mirrored in the preview's `app.js`** so
  the Estilo tab shows the real break at the real size. Change one, change both.
- In a split layout, `paddingTop` still has to follow the seam — see the split
  section.

## Caption style — six of them

Three are animated (karaoke, stacked, scatter) and three are STATIC
(`simples`, `serifada`, `classica`) — no animation at all, a cue just replaces
the previous one. All three static ones live in `SimpleCaptions.tsx`, read
`captions.json` alone, and share one rule that is the whole point:

**Lines group by MEASURED WIDTH, capped at `maxWords` — never by word count.**
"inteligência" and "de" cannot obey the same rule: the long word takes the line
alone and the short ones ride together. A fixed 3-words-per-line gets this
backwards on every long word.

- `simples` — Poppins 600 at 82, squeezed to 0.9 on BOTH axes, one line, ≤3 words.
  Poppins ships no condensed cut, so this is a distorted regular: it thins the
  stems in both directions. If it ever reads too light, raise the weight to 700
  rather than compressing further.
- `serifada` — Libre Baskerville 700 at 84, same rules, no distortion.
- `classica` — Inter 500 at 52, TWO lines, classic subtitle. The split is width
  balance PLUS a penalty for ending a line on a short function word ("o", "de"),
  which a pure balance does constantly and no real subtitle ever does.
- **The horizontal squeeze changes the line grouping** (narrower glyphs → more
  words fit); the vertical one does not (grouping is measured on width). Worth
  knowing before "just squashing it a bit".
- All three sit at `bottom: 430`, the same band as the others. Lower than that
  and a 9:16 caption lands under the platform's own UI.

### karaoke (default), STACKED or SCATTER

Short-form ships two caption styles. **The user already picked one on the Estilo
tab**, where both previews run the real animation — do not ask again, just set
`captions.style` from `preview_style.json`. (`caption-styles/stacked.png` is
still there as a montage over real footage if a still is useful.)

- **`"karaoke"`** (default): one line ≤3 words, Poppins Black, lower third.
- **`"scatter"`** ("Disperso"): Lora serif, lowercase, off-white with a slight
  darkening toward the baseline, one word at a time in short ragged lines. Reads
  `captions.json` alone — no extra generation step. Ordinary words FADE only; one
  word per cue (the longest, ≥7 chars) resolves out of a heavy blur at 1.62× and
  dissolves back into blur on the way out. Tunables in `captions`:
  `scatterOffsetY` (block centre, default 0.72), `scatterFontSize` (72),
  `scatterSafeWidth` (820); `SPREAD` in the component caps how far a line wanders.
  Three things it took real footage to learn:
  - **Never `Math.random()`.** The engine renders frames independently, so a true
    random re-rolls the layout every frame and the text shakes. Positions are
    hashed off the cue index.
  - **The middle of the frame is the FACE.** The reference look lives over B-roll;
    on a talking head the block belongs on the chest (`scatterOffsetY` 0.72).
    Raise it only when the shot behind is not a face.
  - **Motion on every word is motion on nothing.** Ordinary words used to drop in
    from above too, and at one word per ~200ms the screen read as frantic. The
    blur on the highlighted word only reads because everything else is still.
- **`"stacked"`**: words stacked tight, mixing per line — Poppins bold-italic
  (white→gray gradient) / Poppins regular (smaller) / Playfair serif bold-italic
  in the ACCENT colour (default `#ff3b30`; brand/pick overrides) / Poppins bold. Emphasis words appear solo; key ones get a
  hand-drawn green pencil ellipse. **Baked SFX** (no extra step, no Premiere): a
  **click** on every solo word, a **scratch** when a word is circled.

For stacked, the ONE extra data step is the director (reads the same cut
transcript as `captions_words.py`):
```bash
uv run python helpers/caption_style.py --transcript <edit>/transcripts/cut.json \
    -o hyperframes/caption-cues.json
```
Then set `captions.style:"stacked"` in edit-data.json (keep the other caption
fields — they stay valid). Defaults match the user-approved look: the stack sits
~15.6% of the height below center and SFX play from `public/sfx/caption-click.mp3`
+ `caption-scratch.mp3` (both already in the template). Optional overrides inside
`captions`: `stackedOffsetY` (0–1 of height), `fontScale`, and
`sfx:{enabled,clickVolume(0.45),scratchVolume(0.16)}`. The director groups words
into short cues, gives the orange serif accent to the content word (never a
connective), keeps 1-letter/short connectors from standing alone, and flags
solo/circled words. It is language-tuned for pt-BR (`--lang`); for other
languages it falls back to length heuristics.

A solo word also needs DURATION, not just weight — a word spoken in under
`MIN_SOLO_MS` (340ms) renders as a one-frame flash and reads as a glitch, so the
director folds it into a neighbouring stack instead. Fast connective speech hits
this often. After generating cues, sanity-check the plan (it prints a summary):
every non-`STACK_MIXED` cue should span ≥0.34s, and the word list across all
cues must match the transcript exactly, in order.

## Visual hook — static headline, first ~4s (always on)

The first 1–2 seconds decide the swipe. Write `hook.lines` like a
social-media/copywriting/virality specialist, not a summarizer: read the cut
transcript, find the core promise/tension, and craft a scroll-stopper. Levers:
**curiosity gap · high stakes/bold claim · specificity/number · urgency ·
pattern interrupt**. Match the video's language; never clickbait it can't pay off.

**Two locked styles via `hook.style`** (both user-approved, encoded in the
template):
- **`"card"`** (default): Poppins Black white UPPERCASE on a dark-gray `#232326`
  rounded card, **every line the same font size (~54)** — never a big hero line +
  smaller kicker. Optional row above the card: real brand logo (rounded card,
  w300) + transparent symbol (drop-shadow, w128) — prefer real assets in
  `public/brand/` over drawn SVG; pick a symbol that frames the angle (danger,
  money, trophy…).
- **`"outline"`**: white text + thick black stroke (`WebkitTextStroke` +
  `paintOrder:'stroke fill'`), **no card**, **sentence-case** (write `lines[]`
  normally, not caps), sits lower (`paddingTop` ~330 — may overlap the top of the
  head, which is fine). The TikTok/MrBeast headline look. Tune `fontSizePx` (68),
  `strokePx` (12), `paddingTop` (330), `lineHeight` (1.06). Drop logo/sign.

Both are static hold, fade+rise at the edges, soft whoosh.

Example (Claude Fable video): "A IA MAIS / PERIGOSA DO MUNDO / ACABOU DE SER
LIBERADA". Draft 2–3 copy candidates in chat (text — no renders), let the user
pick, then render ONE still for design approval before the full render.

**De-conflict:** the hook owns the upper zone for its window — push any insert
that wants the same zone to after `hook.endSec` (e.g. move a 2.5s cutaway to
~4.1s).

### Riser no gancho — pergunte: sim / não / SEMPRE

Regra nascida no edvid e confirmada no ave (Fome de Poder v2): o gancho leva um
**riser de SFX que RESOLVE na virada** — a headline estática sozinha não cria
expectativa sonora; o riser transforma os primeiros segundos numa contagem para
alguma coisa. Riser que termina ANTES da virada vira som solto; que termina
DEPOIS atropela o acento que já existe ali.

Protocolo (decidido pelo usuário em 2026-08-18):

1. Com hook ligado e `elements.sfx` on, **consulte**
   `~/.avelin/preferencias.json` → `regras.shortform.hook_riser`. Valor
   `"sempre"` → aplica sem perguntar. Ausente → **pergunte** (AskUserQuestion)
   com as opções **sim / não / sempre**; resposta "sempre" grava a chave (edite
   o JSON preservando o resto) e aplica.
2. A **virada** é onde o riser crava o pico. Candidatos, do mais sutil ao mais
   forte: primeiro corte de take dentro do hook · saída da headline
   (`hook.endSec`) · primeiro acento pós-hook (flash/split/gráfico). Se houver
   mais de um candidato plausível, pergunte junto. (Este usuário escolheu o
   primeiro corte dentro do hook no Fome de Poder v2.)
3. **Como aplicar:** deixa manual em `edit-data.json` —
   `"sfxCues": [{"at": <t>, "kind": "intro"}]` (kind `intro` = `riser-short.mp3`,
   2,325s, vol 0,28, **pico no fim do arquivo**). O bloco final sai como
   `start = at − lead`, com o lead MEDIDO pelo `probe()` do `sfx.py` (para o
   riser-short: 0,864 — NÃO meça você com silencedetect, o limiar é outro).
   Para cravar o fim do arquivo na virada: `at = t_virada − duração + lead`
   (riser-short: `at = t_virada − 1.461`). **Confira no `sfx-events.json`**
   que o compose grava: `start + dur` do bloco do riser tem de ser a virada —
   foi assim que um `at` calculado com silêncio de -40dB saiu 0,5s cedo. Para
   subidas longas há `kind: "tension"` (`riser-tension.mp3`, 9,1s) — corte o
   começo do arquivo se precisar resolver antes.
4. Confira no render: energia subindo nas janelas anteriores à virada
   (`volumedetect` em janelas de 0,3s) e pico dentro de ±2 frames dela.

## Flash na transição (`elements.flashCut`)

A light beam whips across the frame with a bloom and a dry click. Data-driven:
one entry per cut in `transitions[]`, `at` being the cut time **exactly as
segments.json states it** — `VIDEO_LAG` lines it up with the frame the picture
changes on, same as the split windows. Never index it off its own clock.

```json
"transitions": [{"at": 11.7}]
```

Default placement when the element is ON: **one per split-insert entry, not per
cut.** The video has ~27 cuts; a flash on each one stops reading as an accent and
starts reading as a strobe. Put it where the layout changes, which is where the
transition means something. Optional per entry: `intensity` (default 1), `sfx`,
`volume`.

- **The beam LEADS the cut by 2 frames.** Starting it on the cut frame reads as a
  flash after the fact — the eye sees the picture change, then the light. Leading
  it makes the light look like the cause.
- **Blur is what separates a beam from a wash.** At 26px it read as a general
  brightening; 16px reads as a beam. Raise opacity and lower blur together.
- **CHECK THE SFX FILE BEFORE TRUSTING IT.** The pack's `click2.mp3` peaks at
  −25 dB — it is inaudible under speech at any sane volume, and the mix looks
  fine while nothing is heard. `ffmpeg -i <sfx> -af volumedetect -f null -` is
  the check. `cut-click.mp3` (−2 dB, 57ms) is the one that reads.
- **And check WHERE the transient sits inside the file.** The source this click
  came from had 180ms of silence before the hit; delayed to the cut it would have
  landed 180ms late — after a 230ms effect had already finished. Trim the lead-in
  so the transient is at t=0, then delay by the cut time.
- **O clique vive na composição, e é entregue de lá.** No motor antigo ele
  tinha de ser remixado no ffmpeg, porque a cura do drift jogava fora o áudio do
  render. Sem drift, o efeito fica onde foi autorado e chega inteiro na entrega —
  `sfx_blocks()` já compensa o silêncio inicial MEDIDO de cada arquivo.

## Style: "Nenhum" (`edit: "limpa"`) — no split inserts

The whole frame stays on the speaker. **Leave `splitInserts` out of
`edit-data.json` entirely** (an empty array is fine; a populated one is not) and
skip the split director step. Everything else is unchanged — captions, hook,
zoom, tracking, soundtrack and behind-the-subject all still apply, and they are
where the edit gets its life when there is no art on screen.

Two consequences of the frame never being split, both easy to miss:

- **The hook keeps its full-frame padding.** `hook.paddingTop` is tuned per split
  layout (738 / ~920 for a seam that does not exist here). Under `limpa` the
  headline places against the frame, not a seam — start from the template default
  and render one still, rather than carrying a split value over.
- **`captions.windows` has nothing to dodge.** Those entries only exist to move
  the caption off a split seam. Leave the array empty; a stale window from a
  previous render shoves the caption up for no reason.

**This is the default** (`STYLE_CATALOG.edits[0]`, rotulado "Nenhum"), so it is also what a user who
never opens the Estilo tab gets. Split inserts are opted INTO, not out of. It is a
legitimate final look — a talking-head cut, images to be placed by hand later, or
simply no B-roll worth showing — not a placeholder.

## Style: "Dividida ↑ / ↓" (split screen) — two variants

Both pin the FACE to a fixed region and give the rest of the frame to the image.
Data lives in `edit-data.json` `splitInserts[]` (`layout: "top" | "bottom"`); the
component is already in the template's `CustomGraphics.tsx`. Hard cut (no fade),
every window snapped to a take cut, consecutive images contiguous, and
`captions.windows` moves the caption to the seam while a window is up. Full rules
in `assets/shortform/README.md`.

| | **Dividida ↑** (`top`) | **Dividida ↓** (`bottom`) |
|---|---|---|
| Art | top band (750) | bottom band (750) |
| Head | raised underneath, `zoom 1.25 / focusY 400` | held high above, `zoom 1.0 / focusY 225` |
| Caption | ON the seam (`paddingBottom` 1074) | just ABOVE the seam (`paddingBottom` 790) |
| Seam gradient | yes — the caption sits over the art | **no** — it only greys the top of the photo |

**`focusY` is a SOURCE y that lands at the top of the video window** — a point
`y_src` renders at `(y_src - focusY) * zoom`. **Measure before trusting the
numbers:** pull a frame out of `preview.mp4`, read the hair-top and chin y, and set
`focusY` so the head lands where the user asked. The defaults fit a head ~660px
tall starting at y 455.

The two are opposites in one specific way, and it is the whole trick: the source
has a lot of headroom above the head. `top` has to zoom in to throw that headroom
away; `bottom` **keeps** it, and that is what puts the face under the frame edge
instead of in the middle. Swapping the zoom/focus pair between them breaks both.

**The hook does not transfer for free.** `hook.paddingTop` is tuned to the seam of
whichever layout is up: 738 for `top` (text on the seam under the art), ~920 for
`bottom` (text in the gap between chin and seam). Left at the `top` value, the
headline lands across the speaker's mouth. Render one hook still after switching.

## Style: "Broll Overlay" (`edit: "brollOverlay"`) — ênfase POR CIMA do vídeo

Animações HyperFrames que cavalgam o a-roll para dar ênfase — com ou sem
escurecer a tela. O conteúdo NÃO vem de catálogo: nasce de uma conversa sobre o
corte aprovado. O protocolo, na ordem (decidido pelo usuário em 2026-08-18):

1. **Cores primeiro, UMA vez na vida.** Leia `~/.avelin/brand.json`
   (`deep` + `accent`). Ausentes → é a PRIMEIRA pergunta (AskUserQuestion),
   e a resposta é SALVA lá — nunca mais se pergunta, a menos que o usuário
   peça outra cor. Override pontual por `brollColors` no edit-data.
2. **Sugestões vêm do corte, não da imaginação.** Com o pick `brollOverlay`
   salvo, leia o transcrito do corte aprovado, escolha os 2–4 MOMENTOS que
   merecem ênfase (números falados, conceito-chave, virada, enumeração) e
   mande **AskUserQuestion — uma pergunta por momento**, com 2–3 sugestões
   concretas ("o número 20 MIL contando", "JOGO DO TERRENO em letras grandes
   escurecendo a tela") + o Other para ele ditar. O servidor já terá rodado a
   Fase 2 base (o auto-run no salvar); depois das respostas escreva
   `brollOverlays[]` e rode `phase2.py` de novo — é o mesmo ciclo do rerender.
3. **Janelas cravadas em corte ou pausa medida**, nunca no meio de palavra —
   as bordas saem do `jcut_timeline`/`speech_regions`, como todo corte. Nunca
   durante o hook (o `check` acusa texto sob elemento opaco) e nunca
   sobrepostas entre si (a mídia divide track com o split).
4. **Posição respeita o rosto.** `pos: full` implica `dim` (a tela escurece,
   o rosto pode sumir); `top`/`bottom` sem dim exigem MEDIR a cabeça no frame
   (como no split: extraia um quadro, leia topo do cabelo e queixo) — o
   elemento não tapa o rosto. `bottom` acaba antes da faixa de legenda; a área
   útil do Instagram já está nas classes `pos-*` do CSS.
5. **O ritmo é medido, não configurado.** `_bo_ritmo()` no compose: janela
   <2,2s entra em 0,18s; >4,5s em 0,42s; o meio em 0,30s. Cadência dos filhos
   idem. Não invente keyframes por projeto — ajuste a régua no compose se o
   material pedir.
6. **Todo overlay soa.** Whoosh cheio na entrada de janela escurecida, suave
   nas que cavalgam; `stat` estala um pop quando o número assenta; `labels`
   clicam um a um. Já emitido pelo `broll_markup` — não acrescente à mão.

O schema, em `edit-data.json`:

```json
"brollOverlays": [
  {"kind": "words",  "text": "JOGO DO TERRENO", "start": 21.5, "end": 24.0,
   "dim": true, "pos": "full", "accentWords": [2]},
  {"kind": "stat",   "value": "20", "count": 20, "prefix": "R$", "suffix": " mil",
   "label": "por mês", "start": 25.0, "end": 28.2, "pos": "top"},
  {"kind": "labels", "items": ["mil", "dois mil", "20 mil"],
   "start": 29.0, "end": 31.0, "pos": "bottom"},
  {"kind": "media",  "src": "broll_x.mp4", "aspect": "16 / 9",
   "start": 32.0, "end": 34.0, "dim": 0.75}
]
```

- `dim`: `true` = scrim 0.9; número = opacidade do scrim. É um DIV preto sobre
  o vídeo — **nunca** `opacity` no a-roll (mata blend, cria stacking context).
- `accentWords`: índices pintados no accent; sem ele, a palavra mais longa.
- `count` ausente no `stat` → o valor entra pronto, sem contagem.
- `media`: mesmo relógio do split (`data-media-start`), vídeo mudo, e o
  arquivo mora na RAIZ do projeto (`hyperframes/`).
- As legendas pintam POR CIMA do scrim (ordem do DOM) — fala nunca some.
- Look em `assets/styles/broll-overlay.css`, tempo em `broll-overlay.js`
  (construtor `AVE_BROLL`, mesmo idioma do insert/split).

## Behind-the-subject (element between person and background)

Puts an image or giant word(s) BEHIND the person. Great on medium/wide shots;
on tight close-ups anchor elements to the TOP (template already does). Needs
the matting extra: `uv sync --extra matting` (torch).

```bash
uv run python helpers/person_matte.py preview.mp4 -o hyperframes/fg_<name>.mov --start <s> --duration <d>
```

Then describe each window in `edit-data.json` `behind[]` (kind image/words,
matte file, start, dur, words with per-word `at` times). Gotchas the template
already encodes — do not re-learn them:
- ProRes 4444 `.mov` (libvpx silently drops alpha on some builds)
- source RGB composited with alpha, not RVM's `fgr` (halo otherwise)
- `<OffthreadVideo transparent>` or the matte renders opaque
- matte gets the same camera via `frameOffset` or the person drifts

Matte ONLY the windows you need — each file's frame 0 = its window start.

## Gráficos sob medida (`brollGraphics`) — a escotilha

O que não cabe em nenhum estilo pronto vira uma sub-composição sua:

```json
"brollGraphics": [{"id": "roleta", "label": "roleta 029",
                   "start": 5.32, "end": 7.587}]
```

e o arquivo em `<projeto>/hyperframes/compositions/<id>.html` — um documento
COMPLETO, com `data-composition-id` igual ao `id`, `data-width`/`data-height`
1080×1920 e a linha do tempo registrada em `window.__timelines['<id>']`. Sem o
arquivo, o composer avisa pelo nome e a render segue sem ele. **`scaffold()` não
apaga `compositions/`** — o que você escreve ali sobrevive às re-renderizações;
o `index.html` não.

Medido montando a roleta da série "170 Questões":

- **A MÍDIA PRECISA DE DUAS CÓPIAS, porque os dois resolvedores discordam.** O
  extrator de quadros procura o `src` a partir da RAIZ do projeto; o navegador,
  a partir de `compositions/`. Com uma cópia só, um dos dois erra — e o erro do
  extrator é o barulhento: `Video "x" captured 0 of expected N frames`, com a
  render abortando. Ele avisa antes, numa linha de WARNING que some no meio do
  log (*"could not be resolved on disk"*) — **é essa linha que você procura**,
  não a mensagem de erro, que não diz o motivo. Deixe o arquivo em
  `<raiz>/nome.webm` **e** em `<raiz>/compositions/nome.webm`, com
  `src="nome.webm"`. Feio, mas é o único jeito de os dois acharem.
- **Anime o INVÓLUCRO, nunca o `<video>`.** Um `<div>` posicionado por fora, o
  vídeo parado dentro dele.
- **UM `<video>` DENTRO DE SUB-COMPOSIÇÃO ENTREGA ~0,5s E DEPOIS SOME.** Medido
  com clipe de 5,1s: o card aparecia até 5,2s e sumia pelo resto da janela, sem
  erro, sem aviso, com `minVideoFrameCoverageRatio: 1` (o motor jurava ter
  extraído os 154 quadros). Descartados um a um, com render de verdade:
  `mix-blend-mode`, animar o vídeo, codec (mp4 e webm), duração do bloco
  batendo com a da sub-composição, keyframes esparsos (reencodei com `-g 15`),
  cache de extração (renomeei o arquivo) e a própria linha do tempo GSAP
  (neutralizei). Nenhum era a causa. Um clipe de 2,9s no MESMO arranjo funciona
  inteiro — o teto é curto, não zero.
  **A saída é não depender disso: vídeo só para o que se MOVE, `<img>` para o
  que fica parado.** Na roleta, o giro virou um webm de 1,77s e os 3,4s de card
  travado viraram um PNG com alfa — que é o que eles sempre foram, 100 quadros
  idênticos. Sobreponha 2 quadros na emenda ou pisca um buraco. Imagem não tem
  seek, não tem codec, não tem teto.
- **O `snapshot` MENTE sobre tempo.** Ele posiciona o vídeo da sub-composição
  pelo tempo ABSOLUTO do pai; o renderizador usa o relativo. No mesmo instante
  o snapshot mostrava o card travado e a render mostrava o ocioso. Serve para
  ver layout e cor, **nunca** para conferir sincronia — para isso, render curto
  com `--end`.
- **Um gráfico que entra sem som lê como falha de render.** O composer já emite o
  whoosh de entrada, igual aos cartões de inserção — não acrescente à mão no
  `index.html`, ele é regerado.

### "Quero o vídeo transparente" — SEMPRE avalie o overlay primeiro

Quando o usuário pedir um vídeo transparente, ou pedir para tirar o fundo de uma
gravação de tela, **a pergunta a responder é qual dos dois mecanismos serve** —
e ela se responde OLHANDO a arte, não escolhendo por hábito:

| | quando serve | como fica |
|---|---|---|
| **`mix-blend-mode: screen`** | arte **clara** sobre fundo escuro: texto branco, linhas, brilho, fumaça, faísca | o escuro vira transparente de graça, sem matte nenhuma |
| **alfa de verdade** (VP9 `yuva420p`) | a arte tem partes **escuras que importam**: texto escuro, sombra, contorno preto | tudo chega intacto |

O screen não escolhe o que apagar: ele apaga **todo** pixel escuro. Numa gravação
de tela com card creme e texto escuro isso significa que o texto some junto —
medido nesta série, o texto saiu AZUL (misturado com a parede atrás) e a lombada
laranja saiu ROSA.

**Decida com evidência, não com teoria — e é barato.** Componha o quadro à mão
antes de gastar render: `1-(1-a)*(1-b)` sobre um quadro real do corte, lado a
lado com a versão opaca. Trinta segundos de numpy respondem o que uma render de
dois minutos responderia.

Se for **screen**: o fundo tem de ser preto ZERO (`colorlevels` com o `imin`
medido no próprio quadro, nunca chutado — cinza residual vira véu), e o fade vai
por `filter: brightness()`, NUNCA por `opacity` — opacidade abaixo de 1 cria
contexto de empilhamento e mata a mistura.

Se for **alfa**: `libvpx-vp9 -pix_fmt yuva420p -auto-alt-ref 0`. E a matte **não
sai da luminância** — o que é escuro e importa sairia semitransparente, com o
fundo aparecendo através das letras. Sai da SILHUETA: limiar + fechamento
morfológico (dilata R, erode R), com R maior que o maior buraco a tapar (o vão
entre duas linhas de texto) e menor que a menor separação entre dois elementos
distintos.

**Sincronia:** o gráfico serve a fala, não o contrário. Meça a janela de silêncio
em `preview.mp4` com `speech_regions.py` e encaixe o gráfico DENTRO dela, terminando
o movimento pouco antes de a voz voltar. Se a animação da fonte não couber,
**acelere e corte o estado ocioso** — entra já em movimento. Isso é decisão de
ofício (Princípio 9): faça e informe.

## Illustrative images

Pexels for generic concepts (key: `PEXELS_API_KEY`). For brands/people/specific
things, **Wikimedia Commons first** (`wikimedia_images.py` — no key, clean
licensing, prints license+author), then `google_images.py` (needs
`GOOGLE_API_KEY`+`GOOGLE_CSE_ID`, mind rights — pass `--rights cc`, flag
licensing to the user for logos/celebrities). Keep photographer credits.

## Phase 3 — soundtrack (short-form)

Ask: **AI-generated** (Treblo) or **local file** (copy to `public/trilha.mp3`).

**Writing the Treblo prompt — derive it from the video's context, and ask for
MUSIC, not a texture.** Read the cut transcript: what's the topic, energy and
emotional arc? Then describe a real **composed instrumental piece** — name a
**genre + key instruments + tempo/BPM + mood**, and (optionally) a reference
artist/style. Match the content: a hype tech/AI reel wants upbeat modern
electronic with a catchy synth melody; a calm tutorial wants warm lo-fi keys; a
luxury/story piece wants cinematic strings. **Avoid SFX-y phrasing** ("bed",
bare "beat", "sound design", "drones", "risers") — that's what makes Treblo
return sound effects instead of a song. `treblo_music.py` auto-frames the vibe
as a composed instrumental and bans SFX/vocals, but the vibe you pass still has
to read musical.
```bash
uv run python helpers/treblo_music.py "upbeat modern electronic, catchy synth melody, warm analog bass, crisp light drums, ~110 BPM, bright and motivational" -o hyperframes/trilha.mp3 --length-min 30 --length-max 60
```
Then flip `soundtrack.enabled: true` in edit-data.json. **Volume:** start ~0.25
and check it's clearly audible under wall-to-wall narration (a bed at 0.12 is
usually inaudible once the mix is loudnorm'd to the voice — confirm by listening,
not just by the meter). Re-render. Finish with the mandatory loudnorm:

**A entrega é o `deliver()` do `phase2.py` — não monte um re-mux.** Ele pega o
render do HyperFrames, aplica `loudnorm=I=-14:TP=-1:LRA=11` e escreve
`edit/final.mp4`. A Fase 1 já normalizou o corte, mas a Fase 2 acrescenta trilha
e efeitos: a mistura final é outra e o alvo tem que ser reaferido na saída.

**O re-mux do áudio está BANIDO** — está na lista de anti-padrões do SKILL.md, e
a razão é concreta. Ele existia porque o áudio do renderizador ANTIGO derivava
(+90ms aos 8s, +660ms aos 78s num corte de 95s), e a cura descartava junto todo
efeito embutido na composição — ~20 SFX para reconstruir à mão no ffmpeg, um por
um, adivinhando. No HyperFrames o drift medido é ZERO ao longo de 780s, então os
efeitos ficam onde nasceram: dentro da composição. Se algum dia você suspeitar de
drift, MEÇA por correlação em três janelas de 15s+ antes de mexer — e se o desvio
for constante, não é drift, é latência fixa e não pede re-mux nenhum.

**Confira as tags de cor da entrega na PRIMEIRA vez que rodar um projeto novo.**
Herança medida no renderizador antigo, ainda NÃO reaferida no HyperFrames: a
saída dele vinha `yuvj420p`, `color_range=pc`, `color_primaries=bt470bg` (PAL!) e
transfer desconhecido — luma 0–255 onde o `preview.mp4` está em 16–235. Como o
`deliver()` copia o vídeo (`-c:v copy`), tags erradas na origem passam INTEIRAS
para a entrega, e o grade que o usuário aprovou na Fase 1 escorrega no último
passo: um player que respeita as tags desloca o matiz, um que ignora o range
esmaga os pretos.

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=color_space,color_primaries,color_transfer,color_range \
  -of default=nw=1 edit/final.mp4
```

Tem de sair `bt709 / bt709 / bt709 / tv` — exatamente o que saiu da Fase 1. Se
não sair, o `-c:v copy` não serve para este motor: reencode convertendo o range e
carimbando as tags, e é o `setparams` que as faz colar (os flags de saída
`-color_primaries` / `-color_trc` sozinhos deixavam ambos `unknown`).

```bash
-vf "scale=in_range=full:out_range=limited,format=yuv420p,\
setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"
```

Confirme também `max_volume ≤ -1 dB` (`-af volumedetect`) na entrega.
