# Avelin — diagnóstico e plano de execução (2026-11-06)

## Estado da execução (2026-11-06, branch `rapido-e-preciso`)

Executado e medido nesta máquina (M3, fonte de teste "conselho ou mentoria", 180 s):

| Passo | Estado | Evidência |
|---|---|---|
| B0 fixture + regressão | feito | `tests/fala_limpa_regressao.py` passa (3 repetições, silêncios limpos, 0 falsos positivos) |
| B1 transcrição local VAD-first | feito | `transcribe_local.py`; `transcribe.py --backend auto` → local; 57 s por 180 s |
| B2 detector + EDL proposto + roteiro | feito | `fala_limpa.py`: 6 cortes automáticos, 4 perguntas, `roteiro.md`, `triagem.json`; proxy renderiza; portão passa após as respostas |
| B3 esperas e caches | feito | `verify_takes` VAD-first: render 45 s (era ~4 min), fonte 55 s (era ~15 min); caches derivado (silencedetect, rms, signalstats, detect_restarts); `AVE_OFFLINE` |
| B4 bugs 1–12 | feito | ver commit "B4"; bug 9 resolvido alinhando o SKILL ao servidor (aprovar sempre aprova, parecer em `gate_report.json`) |
| B5 instalação | feito | `install.sh`/`install.ps1`, `doctor.py`, `ffbin.py` (static-ffmpeg com zscale); instalação limpa testada em 31 s com cache quente; `install.md` e README reescritos |
| B6 `fase1.py` + SKILL.md | feito, parcial | drop → proxy em 1 min 30 s (3 min de fonte); 2ª rodada com respostas em 27 s; SKILL.md 159 KB → 147 KB (a meta de ≤ 50 KB NÃO foi atingida: só a Fase 1 e o Setup foram reescritos) |

| B7 seleção guiada pela tese (`selecao.py`, `fase1 --alvo/--tese`) | feito | 'conselho ou mentoria' alvo 65 s: 66% da seleção humana sem revisão, 90% com uma linha de revisão; proxy de 70 s em 26 s |
| B8 retake dentro do fôlego vira pergunta | feito | fixture `oriento16`; apontado pelo usuário no proxy de 70 s |

Pendências conhecidas: o caminho faster-whisper (Windows/Linux/Mac Intel) foi
testado SÓ neste M3 com `AVE_MOTOR=faster` (2026-11-06): doctor ✓, os dois
fixtures ✓, Fase 1 inteira ✓ em 4m31 para a fonte 4K de 4m15 (≈1× tempo real
em CPU; esperar 2× em Intel) — mas o conjunto de defeitos difere do mlx (3 itens
a menos, 2 a mais, sobre 18), então a régua real em máquina sem Apple Silicon
segue pendente; `install.ps1` não foi executado (sem PowerShell aqui — só
revisado); SKILL.md ainda carrega as narrativas de incidentes
das outras seções; o portão com render ainda acusa riso/ruído sem texto como
"ar morto" (caso legítimo de inspeção, não bug).

Documento para um modelo executor. Cada passo diz O QUE fazer, ONDE, COMO
conferir, e o que NÃO fazer. Execute na ordem. Não pule os testes de aceite.
Os números citados foram medidos nesta máquina (Apple M3, 24 GB) no projeto
`/Users/apple/Movies/Shorts/conselho ou mentoria` (fonte DJI de 4m15s).

---

## PARTE A — DIAGNÓSTICO

### A1. Resumo em três causas

1. **A transcrição é "limpadora" e roda o arquivo inteiro.** O Whisper (via Groq)
   apaga do texto repetições, falsos começos e retomadas que existem no áudio.
   O pipeline sabe disso e compensa com SEIS remendos (`verify_takes --fonte`,
   `detect_restarts`, `transcript_audit`, `propose_breaths.isolate_check`,
   `portao_fase1` × `defeitos_audio.json`, `verify_takes` no render). O remendo
   mais caro (`verify_takes --fonte`) leva ~15 min para 2 min de áudio e, medido
   aqui, **confirma falsos positivos** (ver A3).
2. **O modelo faz trabalho de script.** Nenhum helper propõe o EDL: o modelo lê
   `takes_packed.md`, escolhe tomadas, remove muletas à mão, calcula bordas com
   `speech_regions.py` e escreve `edl.json` na mão. Para isso carrega o
   `SKILL.md` de 159 KB a cada sessão. Um modelo mais simples não consegue
   executar esse protocolo com confiabilidade.
3. **A instalação depende de brew + chave Groq + 8–12 aprovações.** `ffmpeg-full`
   com `unlink/link --force`, `uv`, `node`, chave Groq colada no chat, curl de
   sanidade, venv de 1,5 GB (torch entra pelo `escuta`, mesmo que o usuário
   nunca peça matting).

### A2. Medições (fonte de 180 s, pt-BR)

| O que | Tempo | Resultado |
|---|---|---|
| mlx-whisper large-v3-turbo, arquivo inteiro, sem prompt | 21 s (8,5× tempo real) | perdeu o retake da abertura e "uma dúvida ×2" |
| mlx-whisper large-v3-turbo, arquivo inteiro, com prompt de disfluência | 21 s | manteve o retake da abertura; ainda perdeu "uma dúvida ×2" |
| mlx-whisper large-v3 (não turbo), arquivo inteiro | 41 s | igual ao turbo em acerto; só mais lento |
| Groq whisper-large-v3 (transcrito salvo do projeto) | rede | perdeu "uma dúvida ×2"; mesma cegueira do local |
| Silero VAD (onnx, CPU) | **0,6 s** | 21 regiões de fala; 17,8–21,7 s é silêncio |
| **VAD → pedaços ≤12 s → turbo isolado com prompt** | **55 s** (um load de modelo por pedaço; cai para ~30 s com load único) | achou "uma dúvida ×2" (47,8 s), "passo a ×2" (164,7 s), "que não estava ×2" (82,3 s) e o retake da abertura — **em uma passada, sem `verify_takes`** |
| janela isolada de 4,2 s sobre SILÊNCIO (17,4–21,6 s) | 12 s | Whisper alucinou ~200 tokens "h h h" |

Conclusão: a cegueira para retakes vem do **contexto** (o decoder suaviza quando
vê a frase inteira), não do motor nem da nuvem. Transcrever por região de fala
isolada resolve na origem. O `verify_takes` já faz isso, mas como remendo
posterior, em ~300 janelas sobrepostas, e sem VAD — por isso é lento e alucina.

### A3. Falso positivo confirmado no fluxo atual

`defeitos_audio.json` do projeto "conselho ou mentoria" marca `"tchau" ×2` em
19,2–20,1 s como `confirmado: true`. Silero VAD e `silencedetect` (−35 dB) dizem
que 17,8–21,7 s é silêncio. A janela isolada nesse trecho alucina. O
`portao_fase1` trata esse "defeito" como range proibido. Ou seja: o remendo
cria defeitos que não existem e o portão os protege.

### A4. Onde o tempo de uma rodada vai (vídeo curto, 1 fonte)

- ~9–10 decodes completos da fonte antes do primeiro proxy (`source_roles`,
  mp3 para Groq, `verify_takes`, `transcript_audit`, `voice_levels`,
  `hook_finder` ×2, `detect_color`, `speech_regions` CLI sem cache).
- `verify_takes --fonte`: ~15–20 min em fonte de 3 min (documentado no próprio
  docstring). `verify_takes` no render: ~4 min (~170 janelas).
- `propose_breaths --comparar` roda 3 perfis + `--apply` = 4× o mesmo trabalho,
  com uma chamada Groq por hesitação, sem cache.
- `portao_fase1` roda `detect_restarts` duas vezes; `perguntar.py` roda mais
  duas; `transcript_audit` roda no portão de novo.
- Até 3 loops de `verify_cut` + re-render; cada salvamento do editor dispara
  render em 1080p + `verify_cut`.
- 5 ou mais esperas obrigatórias do usuário antes do proxy (objetivo/tese,
  estratégia, ritmo, perguntas do detector, aprovação).

### A5. Bugs concretos encontrados (corrigir na Parte B, passo B4)

1. `transcript_audit --fix-times` grava `<stem>.raw.json` em `transcripts/`;
   `pack_transcripts` e `detect_restarts` leem esse backup como se fosse outra
   fonte → take duplicado no `takes_packed.md` e reinícios falsos.
2. `transcript_audit.map_through_edl` lê `tl[i]["start"]` (chave inexistente) e
   cai no somatório de durações → deriva cumulativa sob J-cut.
3. `cut_words.build` soma durações e ignora `jcut_timeline` → tempos do painel
   derivam.
4. `apply_edits.py` ignora `cutWords`/`cutBreaths` e apaga `preview_edits.json`;
   o servidor roda `apply_edits` em todo save → palavras riscadas pelo usuário
   podem sumir.
5. Depois de edição no editor, o portão e o `verify_takes` conferem o
   `preview_proxy.mp4` antigo contra o EDL novo.
6. `render.py` grava os respiros expandidos de volta no `edl.json` → a intenção
   `breaths[]` some após o primeiro render.
7. `propose_breaths`: `piso` reaproveitado entre fontes; `CTX_TOL` 0,45 pega a
   palavra seguinte; `speech_regions` roda `silencedetect` no arquivo inteiro
   por range.
8. `verify_cut` em render com J-cut (padrão) **não sonda** pop/hot nas emendas.
9. SKILL.md diz que o portão bloqueia a aprovação; o código (`_gate_then_approve`,
   2026-09-18) aprova sempre e roda o portão em background.
10. `transcribe_batch.py` usa `--language None` → o prompt de disfluência pt
    nunca entra pelo caminho recomendado.
11. `preview_server` não vê o `yt-dlp` instalado no venv; docs dizem cache
    HyperFrames de 365 MB (medido: 997 MB + 1,3 GB npx).
12. `install.md`/`README` mandam `uv sync` puro após atualizar — isso desinstala
    os extras (`instalar.py` explica; o certo é `--inexact`).

### A6. Ferramentas avaliadas

| Ferramenta | Veredito |
|---|---|
| **mlx-whisper large-v3-turbo** (já instalado) | **Motor padrão** em Apple Silicon. 8,5× tempo real, grátis, offline. |
| **Silero VAD v5** (pip `silero-vad` + `onnxruntime`, ~12 MB) | **Entra.** 0,6 s por 3 min. Define regiões de fala, mata alucinação em silêncio, dá borda acústica. |
| **faster-whisper** (CTranslate2) | Motor padrão **fora** de Apple Silicon (CPU int8, large-v3-turbo). No Mac roda só em CPU (sem Metal) — não usar aqui. |
| WhisperX (alinhamento wav2vec2) | Não entra agora: CTranslate2 sem Metal, modelo pt de ~1,2 GB a mais. Reavaliar só se a borda por VAD+energia não bastar. |
| CrisperWhisper (verbatim, fillers) | **Não.** Pesos com licença não-comercial; benchmark multilíngue sem confirmação de pt-BR. |
| Groq / ElevenLabs | Viram **opcionais** (fallback em máquina fraca ou sem Apple Silicon). Nenhuma chave obrigatória. |
| `static-ffmpeg` (pip) | **Entra.** Testado: ffmpeg 7.0 arm64 com `zscale`, `deesser`, `loudnorm`, `silencedetect`, `videotoolbox`. Elimina brew + `ffmpeg-full` + relink. |
| Node + `npx hyperframes@0.7.109` | Continua (Fase 2 depende). Única dependência de sistema que sobra além do `uv`. |

---

## PARTE B — PLANO DE EXECUÇÃO

Regras gerais para o executor:
- Trabalhe em branch: `git -C ~/.claude/skills/ave checkout -b rapido-e-preciso`.
- Rode helpers sempre com `uv run python helpers/<nome>.py` dentro de
  `~/.claude/skills/ave`.
- Nunca apague `transcripts/` nem `edit/` de projetos do usuário. Teste em
  cópias dentro de `/tmp` ou no scratchpad.
- Cada passo termina com "Aceite". Só avance com o aceite verde.
- Não reescreva `SKILL.md` antes do passo B6. Até lá, só adicione helpers.

### B0. Fixture de regressão (antes de tocar em qualquer código)

1. Copie 180 s do áudio da fonte de teste:
   ```bash
   mkdir -p ~/.claude/skills/ave/tests/fixtures/audio
   ffmpeg -y -v error -i "/Users/apple/Movies/Shorts/conselho ou mentoria/DJI_20261027144155_0025_D.MP4" \
     -t 180 -vn -ac 1 -ar 16000 ~/.claude/skills/ave/tests/fixtures/audio/conselho180.wav
   ```
2. Crie `tests/fixtures/conselho180.esperado.json` com a verdade medida:
   ```json
   {
     "repeticoes": [
       {"t": 0.0,   "ngrama": "você quer um conselho ou uma mentoria essa frase me mostrou como eu estava dedicando", "tipo": "retake"},
       {"t": 47.8,  "ngrama": "uma dúvida", "tipo": "gaguejo"},
       {"t": 164.7, "ngrama": "passo a",    "tipo": "gaguejo"}
     ],
     "silencios_obrigatorios": [[17.8, 21.7]],
     "falsos_positivos_proibidos": [{"t": 19.2, "ngrama": "tchau"}]
   }
   ```
3. Crie `tests/fala_limpa_regressao.py` que roda o novo motor (B1+B2) sobre a
   fixture e falha se faltar qualquer repetição esperada, se detectar palavra
   dentro de `silencios_obrigatorios`, ou se aparecer um falso positivo
   proibido.

**Aceite:** o teste existe, roda, e FALHA (ainda não há motor novo).

### B1. Novo motor de transcrição local: `helpers/transcribe_local.py`

Objetivo: substituir Groq como padrão, com saída **no mesmo schema** que o
`transcribe.py` grava hoje (`{language_code, language, text, words[], _transcription_backend, _spacing_source}`,
palavras `{text,start,end,type:"word"|"spacing",speaker_id:"speaker_0"}`),
para que todo o resto do pipeline continue lendo o mesmo arquivo.

1. Dependências em `pyproject.toml`, no bloco base (não em extra):
   ```toml
   "silero-vad>=5.1", "onnxruntime>=1.17", "soundfile>=0.12",
   "mlx-whisper>=0.4; sys_platform == 'darwin' and platform_machine == 'arm64'",
   "faster-whisper>=1.1; not (sys_platform == 'darwin' and platform_machine == 'arm64')",
   ```
   Depois `uv sync --inexact`. (mlx-whisper puxa torch; aceite isso por ora —
   o passo B5 trata o tamanho do venv.)
2. Estrutura do script (funções, nesta ordem):
   - `extrair_wav(fonte) -> wav 16 kHz mono` via ffmpeg (reaproveite a função
     de `transcribe.py`, trocando mp3 por wav PCM; o VAD precisa de PCM).
   - `regioes_de_fala(wav) -> [(start,end)]`: Silero VAD onnx,
     `min_silence_duration_ms=300`, `speech_pad_ms=120`. Carregue o áudio com
     `soundfile` e passe `torch.from_numpy(mono)` (o `read_audio` do pacote
     exige torchaudio; não use).
   - `fatiar(regioes, max_s=12.0) -> pedaços`: regiões maiores que 12 s são
     cortadas no ponto de menor energia RMS (janela de 50 ms) dentro de
     ±1,5 s do múltiplo de 12 s. Nunca corte no meio de uma região curta.
   - `transcrever_pedaco(mono, s, e)`: mlx-whisper `large-v3-turbo` com
     `language="pt"`, `word_timestamps=True`, `condition_on_previous_text=False`,
     `no_speech_threshold=0.5`, `initial_prompt=PROMPT_DISFLUENCIA` onde
     `PROMPT_DISFLUENCIA = "Ahn, é, tipo, né, então... eu, eu acho que... quer dizer, hum."`.
     **Carregue o modelo UMA vez** (use `mlx_whisper.load_models.load_model`
     ou mantenha o repo em cache) — o protótipo que carregava por pedaço
     levou 55 s; com load único a meta é ≤ 30 s para 180 s.
     Fora de Apple Silicon: `faster_whisper.WhisperModel("large-v3-turbo",
     compute_type="int8")` com os mesmos parâmetros.
   - `guarda_alucinacao(palavras, regiao)`: descarte palavras cujo `start`
     caia fora da região ±0,15 s; descarte sequências de ≥6 tokens iguais de
     1–2 letras ("h h h"); descarte pedaço cuja razão tokens/segundo > 8.
   - `montar_saida(...)`: some `s` do pedaço aos tempos; gere `spacing` entre
     palavras a partir dos gaps do VAD (não dos carimbos do Whisper); marque
     `_transcription_backend: "local-mlx-turbo"` e
     `_spacing_source: "measured/silero-vad"`; grave também
     `transcripts/<stem>.vad.json` com as regiões (o B2 usa).
3. Integração em `transcribe.py`: adicione backend `local` e faça `auto`
   escolher `local` quando `transcribe_local.disponivel()` for verdadeiro;
   `groq` e `elevenlabs` continuam existindo como fallback explícito.
   Em `transcribe_batch.py`, troque o padrão `--language None` por `pt`
   quando o backend for local (o prompt de disfluência só entra com `pt`).
4. `portao_fase1.py` passo 1 ("spacing provenance"): aceite
   `measured/silero-vad` como proveniência válida.

**Aceite:**
- `uv run python helpers/transcribe_local.py tests/fixtures/audio/conselho180.wav -o /tmp/t.json`
  termina em ≤ 30 s nesta máquina e o JSON tem o schema acima.
- O texto contém "uma dúvida... uma dúvida" e "passo a passo a" e as duas
  ocorrências de "Você quer um conselho ou uma mentoria".
- Nenhuma palavra com `start` entre 17,8 e 21,7 s.
- `pack_transcripts.py` e `detect_restarts.py` rodam sobre o JSON sem erro.

### B2. Detector unificado + EDL proposto: `helpers/fala_limpa.py`

Objetivo: UMA passada determinística que entrega `defeitos.json` (o que cortar,
com borda acústica já calculada) e `edl_proposto.json` (EDL inicial). O modelo
revisa; não escreve do zero.

1. Entrada: `<edit>` com `transcripts/<stem>.json` (B1) e `<stem>.vad.json`.
2. Detectores (reaproveite código existente, não reescreva):
   - **Gaguejo/repetição adjacente**: n-grama de 1–4 palavras repetido
     imediatamente, normalização NFD/minúsculas (copie de `verify_takes.py:74-97`
     e `cortes/fala.py:87-108`, incluindo `GAGUEJO_1` e `REDUPLICACAO_OK`).
   - **Reinício/retake**: chame `detect_restarts` como biblioteca (classes
     `identica`, `truncada` → cortar a primeira ocorrência; `semantica` → só
     marcar, decisão do usuário — regra 18 do SKILL continua valendo).
   - **Muletas**: lista `cortes/fala.py:43` (`ne, tipo, ahn, hum, hmm, uh, eh, ee, eee, "é..."`).
     Só corte muleta isolada entre dois gaps de VAD ≥ 0,08 s (nunca no meio de
     fala contínua).
   - **Respiros/ar morto**: use as classes e perfis de `propose_breaths.py`
     (`RITMOS`), mas calcule os gaps a partir do `.vad.json`, sem chamar
     `speech_regions` por range e sem chamadas Groq (`isolate_check` deixa de
     existir — a transcrição isolada já foi feita no B1).
3. Borda de cada corte: ponto de menor energia RMS (janela 10 ms) dentro de
   ±50 ms da borda VAD; respeite mínimo de 80 ms entre cortes; arredonde a
   DURAÇÃO para frame (como `render.py` já faz).
4. Saída `defeitos.json`:
   ```json
   {"fonte": "...", "itens": [
     {"id": 1, "t": 47.72, "fim": 48.30, "tipo": "gaguejo", "texto": "uma dúvida",
      "acao": "cortar", "confianca": 0.95, "borda": [47.70, 48.31]},
     {"id": 2, "t": 0.0, "fim": 6.2, "tipo": "retake", "acao": "cortar_primeira", "confianca": 0.9},
     {"id": 3, "t": 82.3, "tipo": "semantica", "acao": "perguntar", "confianca": 0.5}
   ]}
   ```
5. `edl_proposto.json`: todas as regiões VAD da fonte, na ordem, menos os
   itens com `acao: cortar*` e `confianca ≥ 0.8`; respiros já aplicados no
   perfil `equilibrado`. Mesmo schema do `edl.json` atual, com `reason` em
   cada range apontando o `id` do defeito.
6. Também gere `roteiro.md`: o texto final linha a linha, com `~~riscado~~` no
   que saiu e `[?]` nos itens `perguntar`. Esse é o artefato que o modelo e o
   usuário leem (é a "Fase 0" proposta em 2026-08-18: aprovar o texto antes de
   renderizar).

**Aceite:**
- `tests/fala_limpa_regressao.py` passa (B0).
- `fala_limpa.py` roda em ≤ 5 s sobre a fixture (sem contar B1).
- `render.py edl_proposto.json --proxy` renderiza sem erro.
- `portao_fase1.py --pular-render` passa sobre o `edl_proposto.json`.

### B3. Reduzir o trabalho e as esperas

1. **Substitua `verify_takes --fonte` por B1+B2.** Mantenha `verify_takes` só
   no modo "ouvir o render" do portão, mas: alimente-o com as regiões VAD do
   render (gere `.vad.json` do proxy) em vez de ~170 janelas fixas; pule
   janelas sem fala. Meta: de ~4 min para < 40 s.
2. **`propose_breaths`:** leia gaps do `.vad.json`; `--comparar` calcula os 3
   perfis numa passada só; remova `isolate_check`.
3. **Cache por fonte em `~/.avelin/derivados`** (já existe `derivado.py`): ligue
   `speech_regions` CLI, `voice_levels` CLI, `hook_finder` e `detect_color` ao
   cache (chave size+mtime). Hoje rodam decode completo a cada chamada.
4. **Portão:** rode `detect_restarts` uma vez e passe o resultado para
   `checar_triagem`; `perguntar.py` deve ler o mesmo resultado em vez de rodar
   mais duas vezes.
5. **Perguntas ao usuário na Fase 1:** reduza para DUAS esperas obrigatórias:
   (a) uma única `AskUserQuestion` combinando objetivo/tese do gancho + ritmo
   (com os números de `--comparar` no enunciado); (b) a aprovação do proxy. A
   estratégia de corte vai no mesmo texto que acompanha o `roteiro.md`, sem
   espera própria. Itens `perguntar` do `defeitos.json` entram na pergunta (a)
   como opções quando houver ≤ 3; se houver mais, vão como lista no roteiro.
6. **Proxy antes de tudo:** mantenha a regra 6c (renderizar o proxy assim que o
   portão abre), agora sobre o `edl_proposto.json`.

**Aceite (medir e registrar em `tests/bench/fase1_tempo.md`):**
- Fonte de 3 min, do drop ao primeiro proxy: ≤ 3 min de relógio sem contar
  espera do usuário (hoje: 20+ min por causa do `verify_takes --fonte`).
- Nenhuma chamada de rede quando `AVE_OFFLINE=1` está no ambiente (adicione a
  variável e faça `transcribe.py`, `atualizacoes.py`, `propose_breaths.py`
  respeitá-la).

### B4. Corrigir os bugs da lista A5

Para cada item, um commit pequeno com teste quando couber:

1. `transcript_audit.py:304-306` → gravar backup em `transcripts/.backups/`.
   `pack_transcripts.py:314-318` e `detect_restarts.py:137-150` → ignorar
   `*.raw.json` e tudo em `.backups/`.
2. `transcript_audit.map_through_edl` → usar `jcut_timeline` de `render.py`
   (mesma correção já feita em `cut_transcript.py:134-145`).
3. `cut_words.build` → idem, usar `jcut_timeline`.
4. `apply_edits.py` → processar `cutWords`/`cutBreaths` (transformar em ranges
   via `fala_limpa.borda()`) ANTES de apagar `preview_edits.json`; o servidor
   só apaga depois de `apply_edits` retornar 0.
5. `apply_edits.py` → re-renderizar o proxy (não só `preview.mp4`) e passar o
   caminho do proxy novo ao portão.
6. `render.py:1782-1796` → gravar respiros expandidos em `edl.render.json`,
   nunca de volta no `edl.json`.
7. `propose_breaths.py` → `piso` por fonte; `CTX_TOL` só olha a palavra
   ANTERIOR ao gap.
8. `verify_cut.py` → em render J-cut, sondar pop/hot no ponto de emenda do
   VÍDEO (lead) e no fim do áudio anterior (tail), não pular.
9. Decidir uma regra (recomendado: o portão reprova → botão "Aprovar mesmo
   assim", como o SKILL descreve) e alinhar `preview_server._gate_then_approve`
   a ela, gravando `state.gate.forced`.
10. `transcribe_batch.py` → `--language pt` padrão quando backend local/groq e
    idioma não informado.
11. `preview_server.py:184` → detectar `yt-dlp` também no venv
    (`.venv/bin/yt-dlp`); corrigir tamanhos no `install.md`/`README`.
12. `install.md:345`, `README.md:155` → `uv sync --inexact`.

**Aceite:** `uv run python tests/regressao.py` e os testes em `tests/` passam;
`ruff check helpers` sem erros novos.

### B5. Instalação em um comando, sem chaves, com menos prompts

Objetivo final: o usuário roda UM comando (ou o modelo roda UM comando), sem
brew, sem sudo, sem chave de API, e sai com Fase 1 funcionando. Node fica como
único pré-requisito de sistema para a Fase 2, verificado e explicado, não
instalado às escondidas.

1. **ffmpeg pelo pip.** Em `pyproject.toml` base: `"static-ffmpeg>=2.7"`.
   Crie `helpers/ffbin.py` com `caminho_ffmpeg()`/`caminho_ffprobe()`:
   prefira o binário do `static_ffmpeg` (chame `static_ffmpeg.add_paths()` e
   resolva com `shutil.which`); se o usuário tiver ffmpeg ≥ 5.1 com `zscale` no
   PATH, pode usar o dele. Troque todas as chamadas `"ffmpeg"`/`"ffprobe"` dos
   helpers por essas funções (grep: `grep -rn '"ffmpeg"\|"ffprobe"' helpers`).
   Testado aqui: static-ffmpeg entrega ffmpeg 7.0 arm64 com `zscale`,
   `deesser`, `loudnorm`, `silencedetect` e `videotoolbox`.
   Ajuste `atualizacoes.py:95-106` para só avisar abaixo de 5.1 (hoje avisa
   abaixo de 9).
2. **Modelos baixados no instalador, não no primeiro uso:** whisper turbo
   (1,5 GB) e Silero (dentro do pacote). Ofereça `--leve` para pular o modelo e
   cair no Groq se o usuário tiver chave.
3. **`install.sh` idempotente** na raiz do repo (e `install.ps1` espelho):
   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   AVE="${AVE_DIR:-$HOME/.claude/skills/ave}"
   # 1. uv (sem sudo, instala em ~/.local/bin)
   command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
   export PATH="$HOME/.local/bin:$PATH"
   # 2. repo
   [ -d "$AVE/.git" ] && git -C "$AVE" pull --ff-only || git clone https://github.com/mpleandro/ave "$AVE"
   # 3. deps python (inclui ffmpeg estático, VAD, whisper local)
   uv sync --directory "$AVE" --inexact
   # 4. modelos
   uv run --directory "$AVE" python helpers/instalar.py base   # baixa whisper turbo + ffmpeg estático
   # 5. verificação real (sem rede)
   uv run --directory "$AVE" python helpers/doctor.py
   ```
   `helpers/doctor.py` imprime ✓/✗ de: ffmpeg (versão, zscale), VAD, whisper
   local (roda 2 s de áudio sintético), node ≥ 18 (só avisa: "Fase 2 precisa
   do Node — instale em nodejs.org"), e NUNCA pede chave.
4. **Menos prompts no Claude Code.** O instalador imprime (e o modelo oferece
   aplicar, com consentimento explícito) um bloco para `~/.claude/settings.json`:
   ```json
   {"permissions": {"allow": [
     "Bash(uv run --directory ~/.claude/skills/ave python helpers/*)",
     "Bash(uv run python helpers/*)",
     "Bash(ffprobe *)", "Bash(ffmpeg *)",
     "Bash(git -C ~/.claude/skills/ave pull --ff-only)"
   ]}}
   ```
   Com isso a instalação cai de 8–12 aprovações + chave para: 1 aprovação do
   `install.sh` (+1 se o modelo aplicar o allowlist). O skill
   `fewer-permission-prompts` do Claude Code gera essa lista a partir do
   histórico, se preferir.
5. **`install.md` reescrito** em 8 linhas: o comando, o que ele faz, o que o
   usuário vê, e "chaves são opcionais: Groq/ElevenLabs só se o computador
   não tiver Apple Silicon ou se você preferir nuvem; Pexels/Treblo só para
   imagens e trilha por IA".
6. **Venv mais leve (opcional, depois):** `mlx-whisper` puxa torch (414 MB).
   Se quiser cortar, trocar por `lightning-whisper-mlx` ou chamar o CLI
   `mlx_whisper` de um `uv tool` isolado. Não bloqueia o resto.

**Aceite:**
- Em uma pasta limpa (`AVE_DIR=/tmp/ave-teste bash install.sh`) com rede, sem
  brew e sem `.env`, o `doctor.py` fica todo verde exceto Node se faltar.
- `uv run python helpers/transcribe.py tests/fixtures/audio/conselho180.wav
  --backend auto` usa `local-mlx-turbo` e NÃO toca a rede (`AVE_OFFLINE=1`).
- Um vídeo HLG de iPhone renderiza com o ffmpeg estático (tone-map via zscale).

### B6. SKILL.md menor e executável por modelo simples

Só depois de B1–B5 passarem.

1. Crie `helpers/fase1.py` que encadeia, com um comando:
   `source_roles → transcribe (local) → fala_limpa → detect_color → portao --pular-render → render --proxy → verify_cut`
   e imprime um **resumo de ≤ 40 linhas**: roteiro.md (texto), lista de itens
   `perguntar`, números dos 3 ritmos, e a URL do editor. Exit 0 = proxy pronto;
   exit 2 = precisa de decisão do usuário (lista o quê).
2. Reescreva a seção "PHASE 1" do SKILL.md (linhas 633–936) para:
   "rode `fase1.py`; mostre o roteiro; faça UMA pergunta (objetivo/tese +
   ritmo + itens marcados); aplique a resposta com `fala_limpa.py --aplicar
   respostas.json`; renderize; peça aprovação". As regras 1–6 do bloco 6b
   continuam, mas como comportamento do `fala_limpa.py`, não do modelo.
3. Mova histórias de incidentes ("Fome de Poder v2", "projeto #29", etc.) para
   `references/historico.md`. O SKILL.md fica com regras, comandos e critérios.
   Meta: SKILL.md ≤ 50 KB.
4. Marque em `references/premiere-mcp.md` e nos anti-patterns os restos do
   Remotion como obsoletos.

**Aceite:** um modelo pequeno (ex.: Haiku), recebendo apenas o SKILL.md novo e
uma pasta com um vídeo de 3 min, chega ao proxy aprovável com no máximo 2
perguntas ao usuário e sem editar `edl.json` à mão.

---

## PARTE C — ORDEM E ESTIMATIVA

| Passo | Dependência | Esforço (modelo executor) |
|---|---|---|
| B0 fixture + teste | — | 1 h |
| B1 transcrição local VAD-first | B0 | 1 dia |
| B2 fala_limpa + edl_proposto + roteiro.md | B1 | 1–2 dias |
| B3 reduzir esperas/caches | B2 | 1 dia |
| B4 bugs | — (paralelo) | 1 dia |
| B5 instalação | B1 (ffmpeg estático pode ir antes) | 0,5–1 dia |
| B6 SKILL.md + fase1.py | B1–B5 | 1 dia |

Ganhos esperados, com base nas medições: Fase 1 de ~20 min para ≤ 3 min em
vídeo de 3 min; zero chaves obrigatórias; instalação de 8–12 aprovações para
1–2; repetições que hoje passam (as que o Whisper apaga com contexto) passam a
ser detectadas na própria transcrição; falsos positivos em silêncio deixam de
existir porque nenhuma janela é transcrita fora de região de fala.
