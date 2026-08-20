---
name: ave
description: Avelin — edit any video by conversation, in phases. Two tracks — SHORT-FORM (vertical 9:16 for Reels/TikTok/Shorts) and LONGFORM (horizontal 16:9 for YouTube: talking-head+B-roll, tutorials/screen-record, vlogs). PHASE 1 — clean cut + color grade + optional voice EQ/mastering (transcribe, select best takes, cut on silence for short-form or retention arc + cold open for longform, grade; ask if shot in LOG; master the voice), then show the user for approval. PHASE 2 (after the cut is approved) — HyperFrames visuals from a data-driven template: short-form gets karaoke captions, a hook headline (a band over the video or a full-screen cartela that hands the video over on exit), a dynamic camera and behind-the-subject; longform gets B-roll cutaways, lower-thirds, chapter cards, callouts, plus YouTube chapters and .srt captions. PHASE 3 — soundtrack (AI via Treblo or a local file). Illustrative images/video via Pexels + Wikimedia/Google. Ask questions, confirm, execute, iterate, persist.
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
10. **Resposta ao usuário é simples, objetiva e direta — SEMPRE.** O chat não é relatório técnico: diga o que fez, o que precisa dele e onde olhar, em poucas linhas. Sem jargão, sem nome de helper, sem número de instrumento, sem parágrafo longo — o detalhe técnico só entra se o usuário pedir. Combina com o item 9: decida, execute, informe em uma linha.

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


17. **INÍCIO DE REGIÃO ACÚSTICA NÃO É INÍCIO DE FRASE NOVA.** A retomada engolida
    mora no COMEÇO da região seguinte, escondida dentro do carimbo esticado da
    primeira palavra — medido DUAS vezes no mesmo take: "isso explica muito"
    dentro do carimbo de `'porque'` (4.28→7.02) e "um sistema" dentro do de
    `'eficiente'` (16.80→18.62). Um range que começa logo depois de uma pausa
    que segue tentativa truncada ou repetida NÃO pode confiar na fronteira:
    transcreva a CABEÇA da região isolada (2–3s, local) antes de fixar o start.
    Errar isto recola a repetição que o corte existia para remover.
18. **DETECTOR ACUSOU + RE-VERIFICAÇÃO DISCORDOU = INCERTO → O USUÁRIO DECIDE.**
    O modelo nunca resolve sozinho — nem por "alucinação do detector", nem por
    "anáfora deliberada". As duas auto-resoluções foram tentadas NO MESMO DIA e
    as duas estavam erradas: o "um sistema ×2" foi acusado duas vezes, descartado
    duas vezes, e era real das duas. Divergência entre instrumentos vira pergunta
    com timestamp clicável, nunca veredito. (Vale igual para o
    `precisa_julgamento` do `detect_restarts`: recomende — "parece anáfora" — e
    deixe a decisão com quem gravou.)
19. **O USUÁRIO APONTOU DEFEITO? MEÇA ANTES DE EXPLICAR.** Extraia a janela
    apontada e transcreva/ouça ISOLADA antes de qualquer resposta — nunca releia
    o transcrito para responder sobre o áudio (o transcrito é a parte que mente,
    ver Regras 15 e 17). E cada defeito apontado vira fixture
    (`tests/regressao.py --criar`): o vídeo que te corrigiu é a régua dos
    próximos.

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
- **`source_roles.py <videos_dir> [--json]`** — **O PAPEL DE CADA FONTE, medido, antes de transcrever qualquer coisa.** Separa MULTICAM de B-ROLL pelo ÁUDIO: duas câmeras no mesmo momento gravam a mesma voz, então os envelopes de energia correlacionam alto e com um deslocamento fixo — e esse deslocamento é o sync da multicam, de brinde. Também desmascara **DUPLICATA** (o mesmo arquivo com e sem timecode dá correlação 1,00 com deslocamento 0; contá-la como ângulo faz você oferecer ao usuário uma troca de câmera que não muda um pixel) e **MESMO MOMENTO, OUTRO FORMATO** (a gravação de tela feita enquanto a câmera rodava casa tão bem quanto uma segunda câmera e NÃO é um ângulo dela). Medido no Fome de Poder: 4 arquivos → 2 ângulos reais (+6,32s) e 2 duplicatas. **O relatório separa o que foi MEDIDO do que é palpite** — `áudio ativo` não é voz — e tudo o que não foi medido cai na lista PERGUNTE, que é a entrada do `AskUserQuestion`.
- **`capcut_captions.py [--novos N] [--id <id>] [--json]`** — lê os modelos de legenda do **CapCut instalado** e descreve o que cada um FAZ. O catálogo dele mistura TRÊS coisas em arquivos diferentes: **modelo** (`content.json` — look + comportamento), **animação** (`modules/AEData.lua` — keyframes no formato do After Effects) e **efeito de estilo** (`effectStyle.json` — preenchimento, sombras, contorno). Traduz cor de float para hexa, resolve o `richText` (que é o visual inteiro numa string) e converte os keyframes em `cubic-bezier` + milissegundos. **Copia PARÂMETROS, nunca as fontes proprietárias (`ZY*`) nem o JS deles** — o look é reconstruído em CSS nosso. Duas armadilhas de leitura registradas no arquivo: os trechos de keyframe têm ARIDADE variável (12 alças num formato, 4 noutro), e o bezier de 12 números se lê em COLUNA — ler em linha produz curvas plausíveis e erradas.
- **`local_fonts.py [--rebuild] [--grep <trecho>]`** — índice das fontes INSTALADAS nesta máquina, para o seletor de fonte da headline (`~/.avelin/localfonts.json`, refeito só quando as pastas de fonte mudam). Existe porque o catálogo do Google cobre o genérico e não cobre a MARCA de ninguém. Guarda o CAMINHO de cada corte porque a medição (`text_measure`) precisa abrir o arquivo — a prévia e o render resolvem a família pelo nome, direto do sistema.
- **`transcribe.py <video> --edit-dir <edit> [--language pt] [--backend auto|groq|elevenlabs|whispercpp]`** — word-level, cached. `backend=auto` (default): ElevenLabs Scribe for sources >5 min (when `ELEVENLABS_API_KEY` set), else Groq Whisper. Audio uploads as CBR 64kbps mono MP3 (~0.5 MB/min); oversized audio auto-chunks **by bytes**, so every chunk is guaranteed under Groq's 25 MB cap regardless of length. Chunks fetch **in parallel** with per-chunk resume cache and 5x backoff retries (provider blips don't restart the job).
- **`transcribe_batch.py <videos_dir> [--backend auto|groq|elevenlabs]`** — 4-worker parallel transcription for multi-take shoots; same per-file auto backend selection by length.
- **`pack_transcripts.py --edit-dir <dir>`** — transcripts → `takes_packed.md` (phrase-level, breaks on ≥0.5s silence). **The** reading view: 1/10 the tokens of raw JSON.
- **`transcript_audit.py <edit> [--recheck]`** — ONDE A TRANSCRIÇÃO MENTE, e é o portão que faltava antes do EDL. O Whisper **engole repetição**: o locutor gagueja, refaz a frase, e sai UMA passada limpa — o parágrafo lê perfeito e o `takes_packed.md` não tem como avisar. Também **troca palavra por palavra** ("trabalhar" → "avaliar", ambas plausíveis). Nenhum detector de TEXTO pega isso porque o texto está bem. Este pega por **densidade acústica** (região de fala com poucas palavras dentro = fala não transcrita; é física, não linguagem) e por **discordância entre as duas passadas** que o projeto já faz de graça. `--recheck` transcreve só a janela suspeita, isolada — sem contexto em volta o modelo não tem para onde suavizar e a repetição reaparece. Medido na série "170 Questões": achou 2 das 3 gaguejadas que o usuário só viu assistindo, uma delas com **0 palavras em 0,80s de fala**.
- **`cut_transcript.py <edit> -o transcripts/cut_mapped.json`** — o transcrito do CORTE por mapeamento do EDL, não por transcrever de novo. É o que a Fase 2 usa para legenda (veja a Hard Rule 15).
- **`transcribe.py <video> --edit-dir <edit> --repair-spacing`** — REESCREVE a pausa de um transcrito já gravado, medindo o áudio. Não re-transcreve, não sobe nada: as palavras do Whisper ficam, só a informação de silêncio é refeita. **Todo transcrito Whisper anterior a esta correção nasceu cego a pausa** — o adaptador reconstruía o token `spacing` do gap entre palavras do próprio Whisper (`s > prev_end`), e esse número é sempre 0.00 porque a timeline dele é contígua e a pausa vira DURAÇÃO da palavra anterior. Medido num take de 60s: 10 tokens `spacing` para 14 silêncios reais, os 8 ausentes exatamente os que caíam dentro de uma palavra; o `takes_packed.md` foi de 7 para 16 frases depois do reparo. Rode em qualquer projeto antigo antes de reaproveitar o transcrito.
- **`detect_restarts.py <edit> [--edl] [--json]`** — FRASE REFEITA, por n-grama repetido em janela curta. Quatro delas foram para um corte final estando escritas, em português, no `takes_packed.md` que o editor leu. Três regras, nesta ordem: **truncada** (a primeira versão morre em palavra funcional — "é um negócio DE") → remove sozinho; **idêntica** → fica a última; **semântica** → PERGUNTA. `--edl` roda sobre o corte e pega repetição que atravessa emenda. Todo hit semântico sai marcado `precisa_julgamento`: repetição também é anáfora ("com um sistema impecável" / "Um sistema eficiente"), e separar as duas é significado, não string — é o único ponto do pipeline onde julgar é o trabalho certo.
- **`perguntar.py <edit> [--contexto NOME] [--teto N]`** — o que perguntar ao usuário, e o que NÃO perguntar. **A pergunta nunca mostra um número** ("hesitação de 0,38s abaixo do limiar" descreve o instrumento, não a escolha): mostra o áudio, com timestamp para clicar no editor que já está no ar, e a consequência. **Uma pergunta por classe, não por ocorrência** — sete respiros viram uma pergunta com três exemplos. Consulta o `preferencias.py`: confiança alta aplica calado, média aplica e informa, baixa pergunta.
- **`preferencias.py [--mostrar|--aprender <edit>|--consultar F C|--reset]`** — o que ESTE usuário costuma querer, aprendido das decisões dele. Mora em `~/.avelin/preferencias.json`, **fora do clone** (preferência de meses não pode morrer num `git clean`). O limiar é o ponto médio entre o maior vão que ele MANTEVE e o menor que ele REMOVEU; faixas que se cruzam derrubam a confiança em vez de inventar um número. `--aprender` lê o `preview_edits.json` — o que ele corrigiu à mão depois da entrega, que é o sinal mais forte que existe e estava sendo descartado. Confiança governa autonomia (<5 pergunta, 5–15 informa, >15 calado), e contradizer um limiar confiante derruba a confiança: discordar do usuário custa autonomia à ferramenta, nunca o contrário.
- **A ABA ESTILO LEMBRA.** As escolhas do último envio (formato do corte, headline, estilo de legenda, elementos ligados, deslocamento da legenda) ficam em `~/.avelin/estilo.json`, escritas pelo servidor no mesmo ato do envio — fora do clone, como o `brand.json` e o `preferencias.json`. O editor empilha quatro camadas nesta ordem: padrão de fábrica → escolhas da última vez → marca (cor e letra) → **o que o projeto gravou, que vence sempre**. Reabrir um vídeo entregue tem de mostrar como ele foi entregue, não o gosto de hoje.
- **`biblioteca.py [--registrar <arquivo> --tipo <t>] [--pasta <dir>] [--listar] [--resolver] [--candidatos <edit>] [--usar <id> --projeto <edit>] [--esquecer <id>] [--adotar-sfx]`** — **O ACERVO DE QUEM EDITA**: logo, trilha, efeito, LUT, vinheta, fonte. Mora em `~/.avelin/biblioteca.json` + `~/.avelin/biblioteca/<tipo>/`, fora do clone e fora do projeto, pela razão do `brand.json`: um asset que vive só dentro de `<edit>/` é um asset que o PRÓXIMO vídeo vai pedir de novo, na mão, a quem já o entregou uma vez. **O que ele guarda é MEDIDO** — alfa do PNG (sem canal alfa, o logo vira um retângulo branco sobre o vídeo), pico e ATAQUE do efeito (o `sfx.py` já sabe medir: o `riser-short` tem 864 ms de silêncio antes da batida), duração da trilha (mais curta que o corte = emenda audível). O alerta sai no registro, não no render. **`--candidatos <edit>` é a entrada da pergunta**: lista o que o usuário TROUXE e o acervo ainda não tem, ignorando o que o pipeline baixou (`pexels/`, `web/`) — isso se acha de novo buscando, e perguntar sobre isso gasta a paciência de que a pergunta seguinte vai precisar. `--usar` é o que faz a régua subir (veja a seção da biblioteca); `--pasta` registra um DIRETÓRIO com um papel, porque quem tem 300 risers não vai registrá-los um a um; `--adotar-sfx` migra o `~/.avelin/sfx.json` antigo.
- **`verify_takes.py <edit> [--video preview_proxy.mp4]`** — **OUVE o corte pronto** e acusa frase repetida, sem confiar em transcrito nenhum. Existe porque o `detect_restarts.py` lê o TEXTO e o Whisper **engole a segunda passada**: quatro repetições chegaram ao usuário num corte cujo `takes_packed.md` mostrava duas frases emendando perfeitamente, enquanto o áudio dizia *"Isso explica muito, isso explica muito, porque você ganha"*. Re-transcrever o corte inteiro NÃO resolve — com contexto o modelo suaviza de novo (verificado: a passada completa sobre o render saiu limpa). O que funciona é **janela curta e ISOLADA**, em várias larguras (2,4/4,0/6,0s), ficando com a menor em que cada achado apareceu. Roda local com mlx-whisper — grátis, offline, ~1min num corte de 40s. Exit 1 se achar algo.

- **`portao_fase1.py <edit> [--pular-render]`** — **O PORTÃO. Exit 1 = o corte não vai para aprovação.** Checa, nesta ordem: `spacing` medido (sem ele a seleção de tomada foi às cegas e o resto é teatro), reinício sobrevivente, `quote` × conteúdo real do range, e `verify_cut` sobre o render. Existe porque os auditores já existiam quando dez defeitos de fala chegaram ao usuário — não faltava ferramenta, faltava obrigação. A diferença entre recomendação e portão é o exit code.
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
- **`preview_server.py [--root <edit>] [--port 4820]`** — serves the standard preview interface (see the Preview interface section). App code lives at `assets/preview/` and is IMMUTABLE. **`--root` is optional**: without it the editor opens on its home screen (dropzone + recent/found projects) and the project is chosen on screen; with it, the session opens straight into that project.

## Preview interface (standard — launch it at the start of every edit)

Every edit session gets the same interactive interface in the user's preview panel: a video-editor timeline (video track with filmstrip + audio track with waveform), a live playhead that scrubs the render in real time, per-take trim handles and take removal, and — from Phase 2 — caption and insert tracks. The layout follows the source aspect on its own: **vertical** sources put a tall player on the right with the transport + timeline on the left; **horizontal** sources keep the player stacked above the timeline. Dark glass, marca Avelin. **Never build a UI per session and never edit `assets/preview/`** — it is data-driven, like the styles in `assets/styles/`.

**Launch (do this when a session starts, even before the first render — the UI shows a waiting state):**
1. Write `<edit>/state.json`:
   ```json
   {"project": "Nome — C0000", "phase": 1, "video": "preview_proxy.mp4", "edl": "edl.json",
    "captions": "hyperframes/captions.json", "editData": "hyperframes/edit-data.json",
    "finalVideo": "final.mp4", "fps": 24, "message": "Fase 1 — cortando",
    "startedAt": 1787000000,
    "sourceDurations": {"C0000": 1038.5},
    "awaitingStyle": false,
    "style": {"edit": "split", "captions": "karaoke",
              "elements": {"tracking": false, "zoomAuto": true, "zoomCuts": true, "musicAI": true}}}
   ```
   (`captions`/`editData`/`finalVideo` only when they exist; the Fase-2 tab plays `finalVideo` — the render WITH captions/inserts — while Fase 1 plays the clean cut; `sourceDurations` lets the UI clamp take extensions; `awaitingStyle`/`style` drive the Estilo tab below.)
2. Ensure `.claude/launch.json` has the config (adjust `--root` per session). The
   server takes the port by flag only, so pass the harness-assigned `$PORT` and
   set `autoPort` — port 4820 is often held by another session:
   `{"name": "avelin-preview", "runtimeExecutable": "sh", "runtimeArgs": ["-c", "exec \"$([ -x <skill>/.venv/bin/python ] && echo <skill>/.venv/bin/python || echo python3)\" <skill>/helpers/preview_server.py --root '<edit>' --port \"$PORT\""], "autoPort": true, "port": 4820}`
3. `preview_start` with name `avelin-preview`.
4. **Arm the watcher IN THE SAME TURN as `preview_start`** — never later, never
   "when the user starts editing":
   `Monitor(command="python3 <skill>/helpers/watch_edits.py", description="escolhas e marcações salvas no preview", persistent=true)`

   **Pass NO path.** Without an argument the watcher follows whichever project
   the editor has open, reading the pointer the server publishes at
   `~/.avelin/current.json`. Pinning it to one `<edit>` — which is what the
   path argument does — makes it go deaf the moment the user switches projects
   on the home screen: they save a marking, see "enviado", and the notification
   never arrives. Pass a path only to watch a folder the editor is NOT showing.

   Without it the UI still writes `preview_style.json` / `preview_edits.json` and
   **nothing happens** — the user clicks Salvar, sees the confirmation toast, and
   waits for work that was never triggered. The failure is silent on both ends:
   they think they told you, and you never heard. `ps aux | grep watch_edits`
   is the one-second check when you are unsure.
5. **Dê a URL ao usuário, na mesma mensagem.** Ver "A URL é parte da resposta",
   logo abaixo — o painel do harness não é o único lugar de onde ele assiste.

### A URL é parte da resposta

O editor é o apoio VISUAL de quem está esperando: é onde ele acompanha o corte
nascer, e não a cada mensagem sua no chat. Mas a porta é decidida na hora
(`autoPort`; a 4820 vive ocupada por outra sessão), e quem não recebe o endereço
fica com uma ferramenta aberta que não consegue abrir.

**Toda mensagem que mostra algo, pede algo ou anuncia que uma etapa começou
termina com a linha do editor:**

```
🖥️ Editor: http://127.0.0.1:<porta>
```

O endereço não se adivinha: o servidor o publica em `~/.avelin/server.json`
(`url`, `port`, `pid`, `at`) assim que sobe. Leia dali — é uma linha:

```bash
python3 -c "import json,pathlib;print(json.loads((pathlib.Path.home()/'.avelin/server.json').read_text())['url'])"
```

**Sem painel de preview no harness** (agente de terminal, máquina nova), suba o
servidor com `--open`: ele abre o editor no navegador padrão sozinho. Com
painel, não use — abrir a mesma tela duas vezes confunde qual das duas é a viva.

Vale para as três fases, e principalmente para os minutos em que você está
trabalhando e ele não tem o que ver no chat: quem sabe onde olhar espera; quem
não sabe pergunta se travou.

### Trocar de projeto é `POST /api/open` — nunca escrever o ponteiro na mão

`~/.avelin/current.json` é publicado pelo servidor e lido pelo watcher.
Escrevê-lo direto no disco parece atalho e é uma armadilha: o VIGIA passa a
seguir o projeto novo e a aba aberta continua no antigo, sem nada em tela
dizendo que os dois discordam. O sintoma é cruel porque cada metade está certa
sozinha — o chat fala do vídeo novo, a tela mostra "Aguardando o primeiro
render" do vídeo velho, e o usuário conclui que o corte não saiu.

```bash
curl -s -X POST localhost:<porta>/api/open -H 'Content-Type: application/json' \
     -d '{"path": "<pasta de vídeos ou o edit/>", "create": true}'
```

A rota valida a pasta, registra nos Recentes e devolve o cartão do projeto. O
servidor hoje também **segue** o `current.json` se alguém o escrever por fora
(a aba se corrige no poll seguinte, em ~2s), mas isso é rede de proteção, não
o caminho: pela rota você descobre na hora se a pasta não existe, em vez de
descobrir pela tela do usuário.

### A tela sem projeto — a dropzone

**O editor abre vazio.** Sem `--root`, a primeira tela é uma dropzone
("Solte seu vídeo aqui") com os projetos recentes e os encontrados no disco
abaixo. O botão ⌂ no cabeçalho volta para ela a qualquer momento — trocar de
projeto não exige mais matar o servidor.

O que o navegador NÃO entrega, e que explica o desenho: **o caminho do arquivo
solto**. `File` traz nome, tamanho e conteúdo; `webkitdirectory` traz os nomes
dos filhos. Nenhum diz onde a coisa está — é fronteira de segurança, não falta
de API. Então:

- **vídeo solto** → o servidor procura o par nome+tamanho no disco e usa o
  arquivo ONDE ELE ESTÁ (cópia zero; uma fonte de 5 GB não vira duas). Só
  quando não acha é que os bytes sobem, para `~/Movies/Avelin/<slug>/`.
- **pasta solta** → mesma busca, desempatada pelos nomes dos filhos.
- **"selecione uma pasta"** → navegador de pastas servido pelo próprio
  servidor (`/api/browse`), que é o único lado que conhece caminhos absolutos.

Um vídeo que já mora dentro de um projeto (`base.mp4`, `cut.mp4`, `final.mp4`)
**abre aquele projeto** — não cria um `edit/edit` nem pede Fase 1 num trabalho
pronto.

### O primeiro envio — direto para a tela de carregamento

Soltar o vídeo **monta o projeto e já dispara a Fase 1**. Não existe tela
entre o drop e o processamento: a que perguntava formato e briefing foi
removida. O corte **segue o aspect ratio do material de origem** — vertical
corta como short-form, horizontal como longform — e formato ou briefing
diferentes o usuário pede no chat, a qualquer momento.

**`preview_request.json` — o drop chegando até você.** É o `/ave <pasta>` sem o
terminal: o servidor escreve o arquivo ao criar o projeto, e o watcher te avisa:

```json
{"type": "new-project", "videosDir": "…", "source": "…", "sources": ["…"],
 "brief": "", "format": "short|long|auto"}
```

`format: "auto"` (o caso normal) = **siga o aspect ratio da fonte** — meça com
ffprobe, informe numa frase, não pergunte. `brief` vazio = converse. **Quem
transcreve, corta e gradua é você** — faça o caminho normal da Fase 1 do
começo, e depois apague o arquivo. Sem sessão sua rodando, o projeto fica
criado e esperando.

**Enquanto você trabalha, a tela dele é um carregamento** — etapas, relógio e
uma linha de recado que sai do `message` do `state.json`. Essa linha é a única
coisa que ele tem para saber que a máquina não travou, então **atualize o
`message` a cada etapa** ("transcrevendo", "escolhendo as tomadas", "cortando os
silêncios", "corrigindo a cor"): o editor casa esse texto com a etapa que
destaca. A tela sai sozinha quando o vídeo do `state.json` existir.

**Não invente `awaitingStart`.** Quem o liga é o servidor, ao criar o projeto;
ele mesmo o desliga milissegundos depois, ao disparar a Fase 1. Escrevê-lo à
mão num projeto em andamento faz o servidor **recortar** o trabalho na próxima
vez que o projeto for aberto — é o flag que diz "nunca começou".

O estado do APLICATIVO (não do projeto) vive em `~/.avelin/`: `projects.json`
(os recentes) e `current.json` (o projeto aberto agora, que o watcher segue).

**`startedAt` (epoch em segundos) liga o RELÓGIO da tela de etapas.** Escreva-o
quando o trabalho da Fase 1 começar. Sem ele o usuário ainda vê as etapas — a
interface não depende mais só desse campo — mas perde o tempo decorrido, que é
o que distingue "lento" de "travado" numa espera de minutos.

**Keep state.json fresh** — bump `phase` and `message` at each milestone (cut rendered, cut approved, Phase 2 rendered…). The UI polls and hot-reloads by itself; waveform + filmstrip regenerate automatically when preview.mp4 changes.

**O `message` NÃO é decorativo: é o que a tela de carregamento destaca.** Entre
o drop e o primeiro render passam oito etapas e vários minutos em que o
usuário não tem vídeo nenhum para olhar — o único sinal de vida é essa linha, e
o editor casa o texto dela com a etapa que acende. **Atualize a cada etapa**, com
palavras que caiam nas faixas do `F1_STEPS` (app.js):

| etapa | escreva algo com |
|---|---|
| medir as fontes | "medindo as fontes" / "papel da fonte" |
| transcrever | "transcrevendo" |
| auditar | "conferindo a transcrição" |
| escolher tomadas | "escolhendo as tomadas" / "estratégia" / "EDL" |
| respiros | "medindo os respiros" / "ritmo" |
| cor | "correção de cor" / "graduação" |
| cortar | "cortando" / "renderizando" |
| conferir | "conferindo o corte" / "proxy" |

Uma mensagem fora dessas faixas deixa o destaque parado na etapa anterior, e um
indicador que não anda lê como travado.

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
- **Estilo de headline** — os onze clássicos (`outline`, `card`, `realce`,
  `misto`, `bloco`, `etiqueta`, `manuscrito`, `gigante`, `relevo`, `grifo`,
  `contorno_duplo`) mais os do motor `cartela`, banda e tela cheia (a tabela do
  catálogo tem a lista inteira). **N linhas**, corpo ajustado à largura segura
  (não mais "sempre duas"). A quebra é do autor: **" / " no texto quebra a
  linha ali**; sem barra, a divisão em duas é equilibrada pela largura MEDIDA —
  salvo nos layouts com `quebra: "encher"` (hoje o `noticia`), que enchem a
  largura em N linhas como manchete de verdade. Layouts com linha herói
  (`gigante`, `etiqueta`, `manuscrito`) têm corpo por linha, e o herói é medido
  sozinho contra a largura inteira.
- **As fontes do PRÓPRIO USUÁRIO entram no seletor** (`local_fonts.py` indexa
  as instaladas — 617 nesta máquina — e o servidor as publica em
  `/api/localfonts`). É o que permite usar a tipografia da MARCA, que o Google
  nunca vai ter. Funciona porque o render roda em Chrome na mesma máquina e o
  Chrome resolve a família pelo NOME; só a medição precisa do arquivo. **O
  preço está dito na interface**: projeto com fonte local não sai igual em
  outra máquina.
- **Cores e fontes vêm DEPOIS do layout**, na mesma camada — a tela desce. Duas
  cores (principal + destaque) e duas famílias (principal + destaque, do
  catálogo do Google Fonts). Cada layout declara em `paint` quem recebe qual, e
  **o degradê é regra do modelo**: onde existe, a cor escolhida é a parada de
  cima e a de baixo é DERIVADA dela. A segunda família só é desenhada pelos
  layouts que declaram `fontRole` (hoje o `manuscrito`) — a interface diz isso.
- **A marca do usuário mora fora do projeto** (`~/.avelin/brand.json`): cor e
  fonte são de QUEM faz, não do que está sendo feito, então um projeto novo já
  nasce com elas. O que o projeto gravou vence sempre — reabrir um vídeo
  entregue mostra as cores com que ele foi entregue. **Você também escreve
  nesse arquivo** quando descobrir a marca por outro caminho (um site, um
  material de referência, uma resposta no chat).
- **Estilo de legenda** — three animated (`karaoke`, `stacked`/"Empilhado",
  `scatter`/"Disperso"), three static (`simples`, `serifada`, `classica`), and
  the editorial pair (`editorial`, `dinamico`/"Dinâmico" — the accumulative,
  centre-anchored cousin).
- **Elementos da edição** — checkboxes: `tracking` (movimento de tracking),
  `zoomAuto` (automação de zoom in), `zoomCuts` (zoom in/out nos cortes),
  `flashCut` (flash na transição), `musicAI` (trilha sonora com IA), plus a
  free-text observation field.

**O servidor DISPARA a Fase 2 sozinho no salvar** (`--auto` é o padrão do
`preview_server.py`) — então quando o `watch_edits.py` te avisar de um estilo
salvo, **cheque `progress.json` antes de rodar qualquer coisa**: se a task
`fase2` já está `running`, o seu papel é acompanhar e atualizar o `state.json`,
não rodar de novo (dois `phase2.py` no mesmo projeto disputam os mesmos
arquivos). O pedido em TEXTO ("Alterações extras") continua sendo seu: o
servidor não interpreta linguagem — leia e execute o que ele descreve.

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

1. **PAPEL DE CADA FONTE — MEÇA, e meça ANTES de transcrever.** URL source?
   `ingest_url.py` first (`--section` when only a range of a longform video
   matters). Então **`source_roles.py <videos_dir>`**, que substitui o `ffprobe`
   fonte a fonte e responde o que ele não responde.

   Rode isto primeiro porque o resultado muda o passo seguinte: **multicam e
   duplicata não se transcrevem duas vezes.** Quatro arquivos do Fome de Poder
   são duas gravações; transcrever os quatro é pagar o dobro para receber o
   mesmo texto duas vezes e depois confundir ângulo com tomada ao escrever o
   EDL — o mesmo trecho entrando no corte duas vezes, com o rosto igual.

   Depois disso: `transcribe_batch.py` (ou `transcribe.py`) **só nas fontes de
   FALA** → `pack_transcripts.py` → leia `takes_packed.md`. Material que você
   não consegue imaginar pelo transcrito → `watch_video.py` para um
   levantamento visual de um Read só.
1b. **PERGUNTE O PAPEL DO QUE SOBROU — com `AskUserQuestion`, não em prosa.**
   Tudo que o `source_roles.py` listou em PERGUNTE é uma decisão do usuário, e
   a interface de opções existe para ele responder num clique em vez de
   escrever um parágrafo. Regras da pergunta:
   - **Uma pergunta por fonte ambígua** (o `AskUserQuestion` aceita até 4 por
     chamada; havendo mais, agrupe as parecidas numa pergunta só).
   - **Pergunte pelo USO, com as opções descritas pelo que o ESPECTADOR VÊ.**
     Nunca "qual o papel desta fonte?", nunca os nomes da tabela abaixo
     (insert, tela dividida, overlay, B-roll) — esse é o vocabulário desta
     skill, não o do usuário.
   - **Traga a evidência medida no enunciado**, não a suposição: duração,
     formato, e o que casou com o quê. É isso que deixa a escolha ser informada.
   - **Ofereça sempre "é só referência, não entra no vídeo"** — material de
     apoio que ninguém pretende usar é comum, e sem essa saída o usuário é
     forçado a inventar um papel para ele.

   Uma pergunta boa, com os números do projeto 29 dentro:

   > **Header:** `Gravação de tela` · **Pergunta:** "A gravação de tela de 55s
   > casa com a câmera no mesmo momento (correlação 0,86), mas está em 994×1594
   > a 45fps — não é um segundo ângulo. Como ela entra no vídeo?"
   > **Opções:** (a) toma a tela inteira por alguns segundos · (b) fica numa
   > faixa com você embaixo (tela dividida) · (c) aparece pequena por cima sem
   > tapar você · (d) é só referência, não entra

   **O que ocupa tempo de tela vira RESERVADO no `edit-data.json` agora**, com
   `planned: true` e sem `src` (ver "Papel de cada fonte" adiante). Sem isso o
   usuário aprova, no portão da Fase 1, uma montagem com buracos que ele não
   consegue ver.

   **Multicam confirmada:** o deslocamento que o helper mediu é o sync. Ranges
   do ângulo secundário usam a mesma janela de áudio com a fonte trocada e o
   tempo corrigido por ele — não uma segunda passada de transcrição.
2a. **VARRA O ÁUDIO DA FONTE — `verify_takes.py --fonte` — antes de escolher qualquer tomada.**

   ```bash
   uv run python helpers/verify_takes.py <edit> --fonte <fonte.MP4>
   ```

   É a etapa que faz o "aha moment" do corte funcionar, e a razão é um defeito
   de instrumento, não de atenção: **o Whisper apaga a repetição do texto sem
   apagá-la do áudio.** Medido três vezes neste projeto — "isso explica muito"
   dito duas vezes virou uma no transcrito; "que muitos chamam" retomado sumiu;
   e re-transcrever o corte INTEIRO devolve a versão limpa de novo, porque com
   contexto o modelo suaviza. Nenhum detector de texto pega o que o texto não
   tem.

   A varredura transcreve janelas curtas e ISOLADAS (2,4/4,0/6,0s, local via
   mlx-whisper, grátis) onde a segunda passada reaparece, confirma cada achado
   numa janela deslocada (janela isolada também alucina — medido), e grava
   `defeitos_audio.json`: o mapa das janelas da fonte que o EDL deve DESVIAR.
   O `portao_fase1.py` confere se desviou — range que contém uma repetição
   confirmada do mapa é FALHA, antes mesmo de renderizar.

   O ciclo inteiro, e onde cada peça age:

   | quando | quem | pega |
   |---|---|---|
   | na transcrição | prompt de disfluência (Groq, pt) | viés a favor de manter gaguejo no texto |
   | antes do EDL | `verify_takes --fonte` | repetição que o texto NÃO tem (áudio) |
   | antes do EDL | `detect_restarts` | repetição que o texto TEM |
   | antes do EDL | `transcript_audit` | fala sem texto (densidade) |
   | no EDL | `portao` × `defeitos_audio.json` | range em cima de defeito conhecido |
   | no render | `portao` → `verify_takes` no corte | o que ainda assim passou |

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
6b. **PASSE PELO PORTÃO antes de mostrar qualquer corte.** Não é sugestão:

   ```bash
   uv run python helpers/portao_fase1.py <edit> --pular-render   # antes de renderizar
   uv run python helpers/portao_fase1.py <edit>                  # depois, com verify_cut
   ```

   Exit 1 significa que o corte **não vai para aprovação** — volta como lista de
   defeitos com timestamp e conserto. Isto existe porque `transcript_audit.py`,
   `propose_breaths.py` e `verify_cut.py` já estavam todos documentados como
   "rode antes do EDL" no dia em que um corte de 51s saiu para o usuário com dez
   defeitos de fala: `edit/verify/` não existia, o `edl.json` não tinha
   `breaths[]`, e o `verify_cut.py` — que sonda exatamente a palavra cortada na
   emenda — teria reprovado aquele corte sozinho. Recomendação que se pode pular
   é recomendação que se pula.

   Depois do portão, `perguntar.py` decide o que ainda merece uma pergunta ao
   usuário e o que a preferência dele já responde.

   **DUAS REGRAS QUE NASCERAM DE UM CORTE ENTREGUE COM QUATRO REPETIÇÕES:**

   1. **O portão com render OUVE o corte** (`verify_takes.py`, chamado por dentro).
      Todas as outras checagens leem texto, e o texto é justamente onde a
      repetição não está — o Whisper a apaga do transcrito sem apagá-la do áudio.
      Nunca mostre um corte que não passou por essa passada.

   2. **Um reinício SEMÂNTICO nunca é descartado pelo modelo.** O
      `detect_restarts.py` marcou "com um sistema impecável" / "Um sistema
      eficiente"; o modelo julgou anáfora deliberada, descartou calado, e o autor
      da frase ouviu o vídeo e disse que era repetição. **Ninguém sabe a intenção
      de quem falou além de quem falou.** Recomende — "isto me parece anáfora, e
      cortá-la estragaria o texto" — e deixe a decisão com ele. Descartar sem
      mostrar é a única saída que não existe. (O espelho também aconteceu: no
      mesmo material, outra sessão julgou DUPLICATA e cortou a anáfora calada —
      "com um sistema impecável, perfeito e de excelência" sumiu do corte. A
      regra vale nos dois sentidos: nem manter nem cortar sem mostrar.)

   **MAIS QUATRO, DO CORTE QUE MUTILOU A ANÁFORA (Fome de Poder v2):**

   3. **Duplicata mínima.** Quando uma repetição confirmada precisa sair,
      remove-se a MENOR janela que a contém — uma ocorrência do n-grama, emenda
      em silêncio medido. Nunca se resolve duplicata cortando oração vizinha que
      só existe uma vez: o corte que motivou esta regra removeu a oração inteira
      "com um sistema impecável, perfeito e de excelência" para evitar um eco de
      1s que sairia sozinho.

   4. **Fronteira é medida; carimbo é palpite.** Onde o detector acústico e o
      transcrito discordam (fala engolida pelo Whisper), o carimbo da palavra
      vizinha NÃO posiciona corte — `silencedetect`/`speech_regions.py`
      posicionam. Dois cortes da mesma sessão entravam no meio de palavra: um em
      17.62s, dentro do "um sistema" engolido pelo carimbo de "eficiente"; outro
      em 51.35s, no meio do "E" de "E essa" (o Groq tinha carimbado esse "E" a
      0,7s de distância, colado na frase errada).

   5. **Retake engolido: procure o take B inteiro.** Quando o silêncio medido
      acusa FALA onde o transcrito mostra silêncio, suspeite de um retake
      completo invisível no texto. Re-transcreva o sub-clipe ISOLADO (via Groq)
      e, se o retake for completo, prefira-o INTEIRO a emendar take A + take B:
      "Aí chega Ray Kroc, que muitos chamam de vilão" existia contínuo na fonte
      enquanto o corte emendava dois takes para dizer o mesmo — com o "que"
      perdido na emenda. Conectivo órfão ("que", "e", "mas") pendurado no fim do
      grupo anterior do `takes_packed.md` é o sintoma clássico.

   6. **Diff de aceitação contra o roteiro-alvo.** Existindo um roteiro final
      (dado pelo usuário ou aprovado em conversa), transcreva o RENDER via Groq
      e compare palavra a palavra com ele. Toda oração ausente exige
      justificativa explícita DITA ao usuário — nunca só anotada no `reason` do
      EDL, que ninguém lê. Foi este diff que pegou as três mutilações que
      originaram as regras 3–5.

6c. **RENDERIZE O PROXY ASSIM QUE O PORTÃO ABRIR — antes do passo do ritmo.**

   ```bash
   uv run python helpers/render.py <edit>/edl.json -o <edit>/preview_proxy.mp4 --proxy --no-subtitles
   ```

   A ordem antiga punha os respiros (passo 7) ANTES do primeiro render, e isso
   pedia ao usuário que escolhesse o ritmo de um corte **que ele nunca viu nem
   ouviu**. Pior: entre escrever o EDL e ver alguma coisa passavam oito etapas
   com a tela em espera — foi exatamente a reclamação que originou esta linha
   ("por que ainda não vejo o resultado dos cortes?").

   Renderizar aqui custa pouco (720p/veryfast, ~3,2× mais barato por segmento
   que o final) e paga duas vezes: o usuário ganha o corte para julgar, e a
   pergunta do ritmo passa a ser feita com o material na tela dele. Depois dos
   respiros o proxy é refeito — é o mesmo comando.

7. **Encurte o ar morto — SEMPRE, antes do primeiro render, e PERGUNTANDO o ritmo.**
   Cortar no silêncio resolve o ar ENTRE tomadas; sobra o de DENTRO — a pausa no
   meio do próprio raciocínio, que nenhuma escolha de tomada remove porque está
   no meio da tomada escolhida. Num vídeo curto é o que mais custa retenção.

   **Nem todo silêncio é ar morto**, e é por isso que isto não é um limiar só. O
   helper classifica cada vão por três coisas — **pausa** (duração), **dB**
   (limiar calibrado na fonte, mais o pico dentro do vão como segunda opinião) e
   **contexto** (a pontuação da palavra anterior: `?!….` = retórica, `,;:` =
   respiração, nada = hesitação) — e cada classe tem seu próprio limiar em cada
   perfil. O contexto decide SE encurta; a **borda continua acústica**.

   ```bash
   uv run python helpers/propose_breaths.py <edit> --comparar    # mede os três
   uv run python helpers/propose_breaths.py <edit> --ritmo <perfil> --apply
   ```

   **Faça a pergunta com os números na mão** — `--comparar` devolve quantos
   respiros e quantos segundos cada perfil tira DESTE material. Use
   `AskUserQuestion`, uma pergunta só, header `Ritmo`:

   > *"Como você quer o ritmo deste corte?"*
   > · **Equilibrado** (recomendado) — tira hesitação, encurta respiração,
   >   preserva a pausa dramática · *11 respiros, −6,4s*
   > · **Conservador** — só o indefensável; pausa retórica intocada · *4, −2,1s*
   > · **Agressivo** — retenção acima de tudo, cada décimo conta · *19, −12,8s*

   Pergunte **uma vez por projeto** e registre a escolha no `state.json`
   (`"ritmo"`); nas rodadas seguintes reaplique sem perguntar de novo. Sem
   resposta do usuário, `equilibrado`.

   O gosto fino fica para os chips da aba Transcrição, que descem até 0,15s —
   **o usuário refina o que sobrou, não faz a limpeza inteira à mão.** Diga em
   uma linha quantos respiros e quantos segundos saíram, e cite as retóricas
   preservadas: um silêncio deliberado que sobrevive calado parece esquecimento.
8. **Render do PROXY.** `render.py edl.json -o preview_proxy.mp4 --proxy --no-subtitles` (+`--voice-master` if wanted; longform: `--keep-resolution`). **The J-cut runs by default** — see below; you do not ask for it and you do not configure it per project. It applies per junction, only where a breath exists.
9. **Self-eval (numeric first).** `verify_cut.py edl.json preview_proxy.mp4` (longform: `--min-silence 1.2`). Clean → done. Flags → `timeline_view` ONLY the flagged junctions, fix, re-render the proxy. Cap 3 loops, then surface remaining flags to the user.
10. **Corte pronto → ABRA A APLICAÇÃO, e só então fale.** Nesta ordem: garanta o
   servidor no ar (`preview_start`), aponte-o para ESTE projeto pela rota
   (`POST /api/open`, nunca escrevendo o `current.json`), confirme que
   `state.json.video` existe no disco — e mande a URL na mesma mensagem. O
   proxy é a primeira coisa que o usuário tem para julgar; mandá-lo procurar
   onde assistir desperdiça o único momento em que ele estava esperando para
   olhar. **Mostre o proxy e PEÇA A APROVAÇÃO, com todas as letras.** É o portão, e ele tem de ser dito — *"aprova a Fase 1?"* — não subentendido. **Nada depois disto começa sem um sim**: nem estilo, nem legenda, nem trilha. Itere sempre no proxy: cada rodada de correção o refaz, e a 720p/veryfast isso é 3,2× mais barato por segmento que o final. Diga que é proxy ao mostrar, para ninguém revisar a COMPRESSÃO em vez do corte.
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
| Legendas | `karaoke` `simples` `serifada` `classica` `disperso` `empilhado` `pop` `popLinha` `popBloco` `revelar` `editorial` `dinamico` |
| Legendas · motor `palavra` | `marcador` `marcadorDuplo` `marcaTexto` `sublinhado` `progressivo` · `foco` `focoBlur` `contorno` `neon` · `chapa` `chips` `vidro` · `onda` `rotativo` `maquina` `rolagem` · `cinema` `manchete` `barra` |
| Headlines | `outline` `card` `realce` `misto` `bloco` `etiqueta` `manuscrito` `gigante` `relevo` `grifo` `contorno_duplo` |
| Headlines · motor `cartela` (banda) | `fita` `jornal` `terminal` `alerta` `placar` `sombra_longa` `neon` `balao` `filete` `adesivo` `noticia` |
| Headlines · motor `cartela` (TELA CHEIA) | `capa` `capa_blur` `cortina` `meia_tela` `moldura` `contagem` `knockout` `poster` `aspas` `ficha` |
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

**A aba Estilo mostra o QUADRO, e escolher aplica no vídeo** (pedido do
usuário, 2026-08-19). Duas coisas que valem para qualquer estilo novo:

- **O cartão é o quadro do projeto**, na orientação do vídeo DECODIFICADO — a
  mesma fonte que decide `body.portrait`, para os dois nunca discordarem
  (`--quadro-w/h`). Era uma tira de 64px com o texto centrado nela: dava para
  comparar as letras e não para ver como fica. Cada estilo aparece onde vai
  aparecer — a legenda a 22% do fundo, o cinema mais embaixo, o rotativo no
  centro, a headline no `top` dela, a cartela cheia tomando tudo. E a escala das
  prévias é `largura em tela / largura do QUADRO`, nunca `/1080` fixo: num
  projeto horizontal o fixo faria a legenda sair quase do dobro do tamanho.
- **Clicar aplica no vídeo, na hora.** A legenda já vinha ao vivo sobre o
  player; a headline agora também, em caixa própria (`#liveHook`) — irmã da
  legenda, porque o overlay da legenda é refeito a cada troca de deixa e a
  headline não pode nascer e morrer junto com ela. Fora da janela do gancho ela
  continua desenhada, apagada: sumir faria o usuário achar que a escolha não
  pegou. E escolher um layout com o ponteiro além da janela LEVA o ponteiro para
  dentro dela — escolher sem ver a escolha é o mesmo que não ter escolhido.

**Vinte headlines, um motor — e dez delas tomam a tela.** Tudo que a tabela
lista sob `cartela` roda em `assets/styles/cartela.css` + `cartela.js`. A
estrutura é uma só: sobrancelha, algarismo, linhas, grade de rótulos e
assinatura, mais as peças que o layout declarar (`pecas`: faixa, cartão,
painel, listras, balão, réguas, vinheta, aspa, svg). Um layout novo é uma
entrada no `variants.json`.

**De onde sai o texto de cinco lugares se o usuário digita um só.** Pela barra
que ele já usa para quebrar linha — a convenção que a `etiqueta` estreou lendo
a primeira linha como rótulo, agora explícita em `slots`: `primeira` (a
sobrancelha), `numero` (o algarismo que vira figura), `traco` (a assinatura da
citação), `chave:valor` (as fileiras da ficha técnica). Sem barra nenhuma, todo
layout cai no bloco de linhas comum. Pedir cinco campos mataria o gancho
rápido, que é a coisa que o gancho tem de ser.

**A saída da cartela de tela cheia é a entrega do vídeo.** `cortina` sobe a
chapa, `corte` a apaga num quadro, `desfoca` dissolve o borrão, `abre` afasta a
moldura, `sobeFora` empurra a meia-tela para cima. Não é enfeite de saída: é a
transição do gancho para a primeira fala, e é ela que o espectador lê como
"começou". Três coisas que essa família obriga, e que valem para qualquer
cartela nova:

- **Quem encolhe é a vinheta, nunca o a-roll.** A `moldura` parece encolher o
  vídeo; o que se anima é uma BORDA que vai a zero. Mexer no `#a-roll` faria a
  cartela e a câmera disputarem o mesmo transform.
- **O recorte do `knockout` é máscara SVG, não `background-clip: text`.** O furo
  tem de ser no FUNDO — a chapa é que fica com buracos em forma de letra. Clip
  de texto faz o contrário (preenche a letra) e o efeito não existe.
- **A cartela cheia não mede o vídeo para escolher o accent.** O fundo dela é a
  chapa da marca, de cor conhecida; medir a luminância do que está ATRÁS de uma
  chapa opaca escolheria a cor pelo que ninguém vê.

**Dezenove estilos, um motor.** Tudo que a tabela lista sob `palavra` roda em
`assets/styles/palavra.css` + `palavra.js`: a deixa nasce diagramada, cada
palavra carrega o seu instante de fala (`data-at`) e tem TRÊS estados — antes de
ser dita, ativa, já dita. O que separa um estilo do outro é só o que cada estado
pinta, e isso é DADO: `variants.styles.<id>.pal` (cor, fundo, escala, blur,
halo, tarja que corre, traço que cresce) mais `.motion` (duração e easing). Um
estilo novo é uma entrada no `variants.json` e, quando muda o desenho parado,
um bloco de CSS — nunca um par de arquivos novo nem um ramo no compositor.

Duas regras que o motor carrega e que valem para qualquer estilo novo:

- **Transição de CSS não sobrevive ao seek.** O renderer salta para um quadro
  qualquer sem tempo de parede passar, e a transição sai congelada no meio. O
  que carrega significado passa por tween de GSAP em tempo ABSOLUTO. O mesmo
  vale para `@keyframes`: animação de CSS VENCE estilo inline, e foi ela que
  acendia todos os cursores da máquina de escrever de uma vez.
- **O accent viaja duas vezes:** `--cap-accent` (hex, para preencher) e
  `--cap-accent-rgb` (trio separado por ESPAÇO, para `rgb(... / alpha)`). Sem o
  trio, halo e chapa translúcida caem calados — a cor não resolve e o CSS
  descarta a regra inteira sem erro nenhum.

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

**Entregue o vídeo e depois pergunte pelo acervo.** Com o `final.mp4` na mão,
rode `biblioteca.py --candidatos <edit>` e, se sobrar algo, faça UMA pergunta
sobre guardar o que o usuário trouxe (logo, trilha, efeito, LUT) — e um `--usar`
para cada item do acervo que entrou neste vídeo. Veja a seção da biblioteca de
assets.


## Papel de cada fonte — e o tempo RESERVADO

Nem toda fonte é fala. Antes de escrever o EDL, decida o que cada arquivo É, porque
isso muda o que entra na Fase 1 e o que o usuário aprova.

**A parte MEDÍVEL disto não se decide no olho: rode `source_roles.py`** (passo 1
da Fase 1). Ele resolve sozinho o que é multicam, o que é duplicata e o que não
tem voz nenhuma, e entrega o deslocamento de sync entre as câmeras. O que ele
não decide — e não deve — é o papel do que sobrou: isso vai para o
`AskUserQuestion` do passo 1b.

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
qual. Junte a evidência primeiro (`source_roles.py` mede duração, formato, áudio e
com quem cada fonte casa; `watch_video.py` mostra o que aparece) e faça a pergunta
pelo `AskUserQuestion`, com as opções descritas pelo que o espectador vê. Em prosa,
a mesma pergunta seria:

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

- **Vertical / Reels / TikTok / Shorts → read `references/shortform.md`.** Karaoke captions, hook headline (band or full-screen cartela), dynamic camera, inserts, behind-the-subject, SFX, soundtrack.
- **Horizontal / YouTube / tutorial / vlog → read `references/longform.md`.** Retention cut is there too (read it BEFORE Phase 1 on longform jobs), B-roll, lower-thirds, chapter cards, callouts, .srt + chapters, soundtrack.

Both tracks: `helpers/phase2.py <edit>` faz tudo — aplica a escolha da aba Estilo, monta o projeto, compõe, roda o `check`, renderiza, normaliza a loudness e devolve os caminhos ao editor. A edição inteira é o `edit-data.json`; nada de código por sessão fora dos gráficos sob medida em `compositions/`. **Não carregue a skill `remotion-best-practices`.** Não é o motor desta skill.

## A biblioteca de assets — o acervo é de QUEM EDITA, não do projeto

O logo, a trilha, o riser, a LUT, a vinheta e a fonte da marca não pertencem ao
vídeo: pertencem à pessoa. Quando eles ficam só dentro de `<edit>/`, o próximo
projeto começa perguntando de novo o que já foi respondido — e a pergunta
repetida é o jeito mais barato de uma ferramenta parecer que não presta atenção.
Por isso o acervo mora ao lado do `brand.json` e do `preferencias.json`:

    ~/.avelin/biblioteca.json       o índice (o que é, para que serve, quantas vezes entrou)
    ~/.avelin/biblioteca/<tipo>/    os arquivos guardados por cópia

`helpers/biblioteca.py` é o mecanismo. O que vem abaixo é **quando falar**.

### Ofereça no momento em que o asset aparece — e uma vez só

Toda vez que o usuário TROUXER um arquivo que não é a filmagem — arrasta um
logo, aponta uma trilha, manda um pacote de efeitos, entrega um `.cube`, pede a
fonte da marca — **use o arquivo primeiro e ofereça guardá-lo depois**, numa
pergunta só, com `AskUserQuestion`. Nunca antes: quem acabou de mandar um logo
quer ver o logo no vídeo, não responder um formulário de catalogação.

E **ao entregar** (depois do `final.mp4`), rode
`biblioteca.py --candidatos <edit>` e agrupe o que sobrou numa ÚNICA pergunta.
O que veio de busca (`pexels/`, `web/`) o helper já descarta sozinho — guardar
uma foto do Pexels no acervo pessoal é guardar um atalho para um catálogo que já
é público.

**Isto não contradiz a regra da aba Estilo.** Lá a pergunta é sobre um LOOK que
o usuário precisa VER para escolher, e uma lista de nomes no chat o faz escolher
às cegas. Aqui é um sim/não sobre um arquivo que ele acabou de entregar e já
está vendo aplicado no vídeo.

### Pergunte o que só ele sabe; meça o resto

Duração, pico, ataque, dimensão, alfa, tamanho da LUT: tudo isso o
`biblioteca.py` lê do arquivo no registro. **Não pergunte nada disso.** Restam
duas coisas que nenhuma medição devolve, e são as únicas que valem uma pergunta:

- **o papel** — para QUE serve (`riser`, `reveal`, `abertura`, `marca-dagua`,
  `trilha-vlog`). É o que permite ao `--resolver` achá-lo por função, meses
  depois, sem o usuário lembrar o nome do arquivo.
- **a condição de uso** (`--nota`) — "só sobre fundo escuro", "a versão
  horizontal é a do cliente", "esta trilha é só da série de vendas". É a
  informação que se perde primeiro e custa mais caro.

Como toda pergunta desta skill, ela mostra a CONSEQUÊNCIA, nunca o instrumento:
*"guardo esse riser como o seu padrão de gancho? nos próximos vídeos ele entra
sozinho na virada"* — não *"registrar asset tipo=sfx papel=riser?"*.

### Acervo grande entra como PASTA, não como 300 perguntas

Quem já tem biblioteca de efeitos tem PASTA de biblioteca. `--pasta <dir>
--tipo sfx --papel riser` guarda o diretório inteiro com um papel, e o
`--resolver` procura lá dentro quando nenhum item registrado serve. Use `--link`
no lugar de cópia quando o acervo for grande ou vivo (uma pasta que o usuário
alimenta por fora): o índice guarda o caminho e o arquivo fica onde está.

### Uso é o que vira padrão — e o que faz a ferramenta calar

`--usar <id> --projeto <edit>` **em toda entrega que usou um item do acervo**.
Sem isso a régua nunca sobe e a skill fica perguntando para sempre o que já foi
respondido três vezes. A régua é a do `preferencias.py`, pela mesma razão:

    0–1 uso    PERGUNTA qual usar
    2 usos     usa e INFORMA numa linha, desfazível
    3+ usos    é o padrão daquele papel — entra calado, aparece só no resumo

Antes de gerar trilha com IA, de buscar imagem de marca ou de escolher um efeito
para uma deixa, **consulte o acervo primeiro**
(`--resolver --tipo trilha`, `--resolver --tipo sfx --papel riser`): pagar um
token por algo que já está no disco da pessoa, e que ela já escolheu duas vezes,
é a definição de trabalho desperdiçado.

### O que NÃO fazer com o acervo

Guardar sem oferecer (o acervo é uma cópia no disco de alguém — `--esquecer`
apaga), escrever qualquer coisa dele dentro de `<videos_dir>` ou do clone, e
transformar um gosto pessoal em `kind` do repositório compartilhado: o catálogo
de `assets/sfx/` é o vocabulário comum de todo mundo, o riser favorito de uma
pessoa é dela — a deixa aceita o arquivo do usuário justamente para isso.

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

- Pedir de novo um asset que a pessoa já entregou. Logo, trilha e efeito
  favorito são da PESSOA, não do projeto: consulte `biblioteca.py --resolver`
  antes de perguntar, gerar ou buscar.
- Catalogar antes de aplicar. Quem acabou de mandar um logo quer VER o logo no
  vídeo; a oferta de guardá-lo vem depois de ele estar aplicado, e numa pergunta
  só.
- Perguntar o que o arquivo responde. Duração, pico, ataque, dimensão e alfa são
  medidos no registro — a pergunta é sobre o PAPEL e a CONDIÇÃO de uso.
- Registrar o uso de um item do acervo e esquecer o `--usar`. A régua de
  autonomia é contada em entregas; sem ela a skill continua perguntando o que já
  foi respondido três vezes.
- Starting Phase 2 before cut approval (the gate is a Hard Rule).
- Asking the style questions in chat, or starting Phase 2 before the pick lands.
  The gate screen exists so the user SEES what each style does — a chat list of
  names asks them to choose blind. Set `awaitingStyle` and wait for
  `preview_style.json`.
- Treating an unchecked element as "não pediu". It is an explicit NO: the user
  looked at "Movimento de tracking" and left it off. `watch_edits.py` prints the
  `fora:` line for exactly this reason.
- Pôr a caixa alta no CSS (`text-transform`) em vez de no código. Ela aplica
  DEPOIS da medição: mede-se a minúscula, desenha-se a maiúscula (mais larga), e
  a headline estoura o quadro sem erro nenhum. Use `upper`/`upperLines` no dado.
- Pedir ao Google Fonts um peso que a família não tem. A API v2 devolve ERRO —
  sem CSS nenhum — e a headline sai na fonte de sistema com a largura toda
  errada. Os pesos disponíveis são dado (`gfonts[].w`) e o peso pedido é grudado
  no mais próximo.
- Pedir uma família EMPACOTADA (`gfonts[].file`, hoje a Bebas Neue) ou LOCAL
  (`k == "local"`) na folha do Google: elas não existem por lá e o erro derruba
  a folha INTEIRA, levando junto a família que existe — medido, pedir a Gotham
  junto da Caveat matava também a Caveat. Empacotada entra por `@font-face`;
  local o Chrome resolve pelo nome. E consulta vazia não vira `&` solto no fim
  da URL: isso derruba a folha do mesmo jeito, junto com a fonte da LEGENDA.
- Manter uma segunda cópia dos números/catálogos no `app.js`. Já aconteceu com
  os layouts de headline e com a lista de quem usa destaque — ao entrarem sete
  layouts, a cópia teria nascido desatualizada. Leia do `variants.json`.
- Hardcoding `#ff3b30` (or any accent) in the template. The Estilo tab lets the
  user pick it, so a literal makes the preview show their colour and the render
  show orange — worse than not offering the choice. Feed `accent` into
  `hook.accent` + `captions.accent`.
- Changing a caption's look in the template without changing its preview in
  `app.js` (`buildKaraokeDemo` / `buildStackedDemo`). The gate's previews render
  the real faces, sizes and motion, scaled from 1080-wide — that is the whole
  reason the user can choose by looking. A preview that lies about the style is
  worse than no preview.
- Adicionar um estilo de legenda sem pôr a folha dele no `CAP_CSS` do `app.js`.
  Faltar ali NÃO dá erro: `liveCss(undefined)` sai calado, a legenda AO VIVO
  cai no ramo genérico de estilo estático e — sem a folha carregada — o texto
  é desenhado cru, branco, encostado no TOPO do quadro. O usuário vê "a legenda
  não aparece", e nada no console diz por quê.
- Esquecer que a folha de um estilo pode nascer INVISÍVEL de propósito. O
  `revelar` começa com `--rev-w: 0` porque quem revela é o render; na prévia ao
  vivo, sem forçar 1, a legenda some inteira — e um estilo que some lê como
  quebrado, não como "ainda não animou". O mesmo vale para o `opacity: 0` do
  empilhado e do disperso.
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
- Arming `watch_edits.py` with a path when the editor is the thing you are
  watching. Pinned to one folder it fica surdo assim que o usuário troca de
  projeto na tela inicial — sem argumento ele segue o editor.
- Launching the preview without arming `watch_edits.py` in the same turn. This
  is the one failure mode where the user reasonably believes they handed you a
  decision and you never got it — the toast says saved, the file is written, and
  no one is reading it.
- Building a per-session preview UI — launch the standard interface and feed it `state.json`. (Improving `assets/preview/` itself IS allowed when the user asks for a UI change; it is shared, so the improvement lands for every project.)
- Applying `preview_edits.json` blindly — validate new edges against `speech_regions.py` first (flag clipped words to the user).
- Decidir no olho o que é multicam, o que é B-roll e o que é duplicata. É
  medível (`source_roles.py`), e errar custa o corte inteiro: dois ângulos
  tratados como duas tomadas põem o MESMO trecho duas vezes no vídeo.
- Transcrever todas as fontes antes de saber o papel delas. Multicam e
  duplicata devolvem o mesmo texto — é pagar duas vezes pela mesma transcrição
  e ainda ficar com dois nomes para o mesmo momento na hora de escrever o EDL.
- Tratar "correlação 1,00, deslocamento 0" como multicam. Duas câmeras de
  verdade NUNCA começam a gravar no mesmo instante — isso é o mesmo arquivo
  duas vezes (export com e sem timecode). Oferecer uma troca de ângulo ali
  mostra ao usuário um corte que não muda um pixel.
- Perguntar o papel das fontes em prosa quando o `AskUserQuestion` existe, ou
  perguntar "qual o papel desta fonte?" — o vocabulário da tabela é desta
  skill, não do usuário. Pergunte pelo que o espectador VÊ.
- Confundir `áudio ativo` com fala. O helper mede energia acima do piso de
  ruído; um clipe de estoque com um whoosh marcou 29%. Separar voz de música
  pela modulação silábica já foi tentado e MEDIDO aqui: não separa.
- Assuming what kind of video it is. Look first, ask second, edit last.
