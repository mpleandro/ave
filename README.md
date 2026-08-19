# A.V.E. — Avelin Video Edit

Editor de vídeo por conversa. Você joga o material bruto numa pasta, abre seu
agente ali dentro e diz *"edita isso num vídeo de lançamento"*. Ele transcreve,
escolhe as melhores tomadas, corta os silêncios, aplica a correção de cor e te
mostra o resultado para aprovação — depois disso entram legendas, gráficos e
trilha.

Funciona em **short-form vertical** (Reels/TikTok/Shorts) e **longform
horizontal** (YouTube).

> **Estado atual.** A Fase 2 renderiza em **HyperFrames** (Apache 2.0) — sem a
> restrição de licença comercial do motor anterior. Portados: seis estilos de
> legenda, quatro headlines, três tipos de edição, a câmera dinâmica e as quatro
> camadas de longform. Ainda falta a camada *atrás do sujeito* — a skill recusa
> pelo nome em vez de substituir por algo parecido.

---

## Checklist da instalação

São **três passos** — instalar os programas, baixar a skill, colar a chave do
Groq — e depois o primeiro vídeo. O passo a passo com os comandos está logo
abaixo; use esta lista para conferir onde você está.

**Obrigatório — sem isto nada roda:**

- [ ] **Git**, **uv**, **ffmpeg** e **Node.js 18+** instalados *(passo 1)*
- [ ] Os quatro respondendo no terminal — `git --version` e companhia *(passo 2)*
- [ ] A skill baixada em `.claude/skills/ave` *(passo 3)*
- [ ] `uv sync` rodado dentro dela *(passo 4)*
- [ ] A **chave do Groq** gravada no `.env` *(passo 5)*

O ffmpeg traz o `ffprobe` junto — é um item só. O Node.js só é usado da Fase 2
em diante (legendas, gráficos), mas instale junto: é o mesmo comando, e ele
para de ser opcional no dia em que você aprovar o primeiro corte.

**Opcional — dá para trabalhar sem, hoje e sempre:**

| Item | Sem ele | Vale a pena quando |
|---|---|---|
| `yt-dlp` | não dá para puxar material de uma URL | você edita coisa que está no YouTube/Drive |
| `ELEVENLABS_API_KEY` | fontes longas transcrevem no Groq, em pedaços | você edita aulas e vídeos de mais de 5 min |
| `PEXELS_API_KEY` | as imagens vêm só da Wikimedia | você usa muito B-roll e imagem ilustrativa |
| `TREBLO_API_KEY` | a trilha tem de ser um arquivo seu | você quer trilha gerada por IA |
| `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` | marcas e pessoas vêm da Wikimedia | a Wikimedia não achou a marca que você precisa |

Nenhuma chave opcional é pedida na instalação: a IA pede cada uma **na primeira
vez que o recurso for usado**, e você decide na hora. O editor também mostra
essa mesma checklist na tela inicial, com ✓ e ✗ do que esta máquina tem.

---

## Instalação

> **A instalação é feita por você, no seu terminal.** Não peça para o agente
> instalar a partir do link do GitHub — ele vai recusar, e com razão: nenhum
> agente deve baixar e executar código de um repositório desconhecido por conta
> própria. Cole os comandos abaixo você mesmo. Leva uns 5 minutos.

Depois de instalada, o agente ajuda com o resto (chave de API, verificação,
problemas de PATH) — aí é tudo local e não tem recusa nenhuma.

### Windows

Abra o **PowerShell** (não o Prompt de Comando antigo — os comandos abaixo não
funcionam nele).

**1. Instale os pré-requisitos:**

```powershell
winget install Git.Git astral-sh.uv Gyan.FFmpeg OpenJS.NodeJS.LTS
```

**2. Feche e reabra o PowerShell.** Isso não é opcional: o Windows só enxerga os
programas recém-instalados numa janela nova.

**Confira antes de seguir.** Este comando tem que responder as quatro versões:

```powershell
git --version; uv --version; ffmpeg -version | Select-Object -First 1; node --version
```

Se algum dos quatro disser *"não é reconhecido"*, o passo 1 não terminou ou você
não reabriu a janela. Resolva antes de continuar — os passos seguintes vão
falhar de um jeito bem menos claro.

**3. Baixe a skill:**

```powershell
git clone https://github.com/mpleandro/ave "$env:USERPROFILE\.claude\skills\ave"
```

**4. Instale as dependências Python:**

```powershell
uv sync --directory "$env:USERPROFILE\.claude\skills\ave"
```

Cole os comandos exatamente como estão. O `$env:USERPROFILE` é uma variável que
o PowerShell troca sozinho pelo caminho da sua pasta de usuário — não edite nada.

### macOS

Abra o **Terminal** (Aplicativos → Utilitários).

**1. Instale o Homebrew**, se você ainda não tem. O comando está em
[brew.sh](https://brew.sh).

**2. Instale os pré-requisitos:**

```bash
brew install git uv ffmpeg node
```

**Confira antes de seguir.** Este comando tem que responder as quatro versões:

```bash
git --version; uv --version; ffmpeg -version | head -1; node --version
```

Se algum disser *"command not found"*, resolva antes de continuar.

**3. Baixe a skill:**

```bash
git clone https://github.com/mpleandro/ave "$HOME/.claude/skills/ave"
```

**4. Instale as dependências Python:**

```bash
uv sync --directory "$HOME/.claude/skills/ave"
```

Cole os comandos exatamente como estão — o `$HOME` é uma variável que o Terminal
troca sozinho pelo caminho da sua pasta de usuário.

### Linux

Igual ao macOS, trocando o passo 2 pelo gerenciador da sua distro
(`apt install git ffmpeg nodejs`, `pacman -S git ffmpeg nodejs`) e instalando o
`uv` pelo instalador oficial em [astral.sh/uv](https://docs.astral.sh/uv/).

---

## Passo 5 — a chave do Groq (obrigatória)

A transcrição roda no Groq Whisper. Sem essa chave nada funciona, porque a
edição inteira parte do texto do que foi falado.

Pegue uma chave gratuita em
[console.groq.com/keys](https://console.groq.com/keys) e grave num arquivo
`.env` dentro da pasta da skill:

**Windows (PowerShell):**

```powershell
Set-Content -Path "$env:USERPROFILE\.claude\skills\ave\.env" -Value "GROQ_API_KEY=cole_sua_chave_aqui"
```

**macOS / Linux:**

```bash
echo "GROQ_API_KEY=cole_sua_chave_aqui" > "$HOME/.claude/skills/ave/.env"
```

Substitua `cole_sua_chave_aqui` pela chave de verdade — essa parte sim você
edita. Se preferir, abra o Claude Code e peça: *"coloca minha chave do Groq no
.env do Avelin"*.

### Chaves opcionais

Nenhuma é necessária para começar. O agente pede cada uma na primeira vez que o
recurso for usado, e você decide na hora:

| Chave | Para quê |
|---|---|
| `ELEVENLABS_API_KEY` | transcrever fontes longas (>5 min) com mais precisão |
| `PEXELS_API_KEY` | imagens e vídeos ilustrativos na Fase 2 |
| `TREBLO_API_KEY` | trilha sonora gerada por IA na Fase 3 |
| `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` | imagens de marcas/pessoas específicas |

Imagens funcionam sem chave nenhuma via Wikimedia Commons, e trilha funciona com
um arquivo de música local. Nada da Fase 2 ou 3 fica bloqueado por falta de
chave.

---

## Fase 2 — nada a instalar

A Fase 2 (legendas, gráficos, imagens) roda em **HyperFrames**, resolvido na hora
por `npx`. Não há segunda skill para clonar nem `node_modules` por projeto: o
motor fica num cache compartilhado (~365 MB em `~/.cache/hyperframes`, baixado
uma vez para todos os vídeos). A primeira Fase 2 da máquina leva alguns minutos
baixando isso; as seguintes começam na hora.

O Node.js 18+ dos pré-requisitos é o que o `npx` precisa — já instalado no passo
1 da instalação.

---

## Transcrição local, sem chave de API (opcional)

Por padrão a transcrição usa a API do Groq. Quem preferir rodar tudo na própria
máquina — sem chave, sem internet, sem cota — pode usar o
[whisper.cpp](https://github.com/ggml-org/whisper.cpp):

```bash
git clone https://github.com/ggml-org/whisper.cpp ~/whisper.cpp
cd ~/whisper.cpp && cmake -B build && cmake --build build -j --config Release
bash ./models/download-ggml-model.sh large-v3
```

Use o **large-v3** — os modelos menores erram muito em português. São ~3,1 GB, e
o download não avisa se for interrompido, então confira o tamanho no fim.

Depois é só pedir esse backend:

```bash
uv run python helpers/transcribe.py video.mp4 --backend whispercpp
```

O Avelin acha o binário e o modelo sozinho em `~/whisper.cpp`. Se você instalou
em outro lugar, aponte com `WHISPERCPP_BIN` e `WHISPERCPP_MODEL` no `.env`.

Instalar o whisper.cpp **não muda nada** por si só: o Groq continua o padrão até
você pedir `--backend whispercpp` explicitamente.

**O que esperar.** Medido num clipe de 16s em português, contra a detecção
acústica de fala da própria skill:

| | Groq | whisper.cpp |
|---|---|---|
| Texto | referência | 28 de 29 palavras idênticas |
| Palavras no tempo certo | 97% | 66% |
| Desvio típico | — | 240 ms (pior caso 2,5 s) |

Ou seja: **o texto é equivalente, os tempos não.** Para a Fase 1 isso não
atrapalha, porque o corte usa a detecção acústica para definir as bordas, não os
tempos do Whisper. Para as legendas karaokê da Fase 2, que leem o tempo de cada
palavra, o desvio aparece na tela — nesse caso prefira o Groq.

---

## Primeiro vídeo

1. Coloque seus vídeos brutos numa pasta.
2. Abra o Claude Code **dentro dessa pasta** e diga: *"abre o editor do
   Avelin"* — ou vá direto ao ponto: *"edita esses vídeos num Reels"*.
3. **Confira a checklist** na tela inicial do editor. Se estiver escrito "tudo
   pronto para editar", pode seguir; se faltar algo, a linha aberta diz o quê e
   o comando que resolve.
4. **Solte o vídeo** na área pontilhada (ou clique para escolher o arquivo).
   Isso monta o projeto e **já começa o corte**, no aspect ratio do seu vídeo —
   vertical vira short-form, horizontal vira longform. Quer outro formato ou
   tem um briefing? É só dizer no chat, a qualquer momento.
5. A tela vira um **carregamento** com as etapas — transcrever, escolher as
   tomadas, cortar os silêncios, corrigir a cor. Costuma levar de 2 a 10
   minutos. Pode deixar a aba aberta: a linha do tempo aparece sozinha quando o
   corte ficar pronto.
6. Assista, marque o que quiser mudar e **aprove a Fase 1**. Só depois disso
   entram legendas, gráficos e trilha.

Tudo o que for gerado vai para uma subpasta `edit/` — seus arquivos originais
não são tocados.

---

## O que dá para pedir — o mapa de capacidades

Use esta lista como cardápio **enquanto edita**: tudo aqui se pede em
português, no chat, sem decorar comando nenhum.

### Fase 1 — o corte limpo

- **Transcrição automática** de tudo que foi falado (Groq; fontes longas via
  ElevenLabs; 100% local via whisper.cpp se você preferir). Nada é transcrito
  duas vezes — fica em cache.
- **Papel de cada fonte medido, não chutado**: o Avelin descobre sozinho o que
  é segunda câmera (e o sync entre elas), o que é arquivo duplicado e o que não
  tem voz — e só pergunta o que não dá para medir.
- **Seleção das melhores tomadas** e corte nos silêncios — nunca no meio de uma
  palavra.
- **Caça aos defeitos que o texto esconde**: gaguejo e frase refeita que a
  transcrição engole, palavra trocada, trecho falado baixo demais para ouvir.
- **Ritmo sob controle**: pausas e respiros encurtados no perfil que você
  escolher (conservador, equilibrado ou agressivo), preservando a pausa
  dramática.
- **J-cut automático** — a voz da próxima tomada entra antes da imagem, como
  num editor profissional.
- **Correção de cor** com detecção automática de LOG/HDR (Apple Log, HLG, PQ) e
  comparação de looks lado a lado para você escolher.
- **Masterização de voz** opcional: EQ, compressão, de-esser, nivelamento de
  trecho falado baixo.
- **Editor visual no navegador**: linha do tempo com filmstrip e waveform,
  aparar e remover tomadas, marcar correções com anotação, aprovar a Fase 1.

### Fase 2 — legendas, gráficos e câmera (depois de aprovar o corte)

- **Legendas em dez estilos** (karaokê, empilhado, disperso e mais) e
  **headlines em onze layouts** — pintadas com as SUAS cores e fontes,
  inclusive as instaladas na sua máquina.
- **Câmera dinâmica**: zoom nos cortes, aproximação lenta, perseguição do
  olhar, flash de transição.
- **Short-form**: inserts que tomam a tela, tela dividida, palavras em
  destaque, gráficos sob medida.
- **Longform**: B-roll, lower-thirds, cards de capítulo, callouts — e de brinde
  os capítulos do YouTube e a legenda `.srt`.
- **Efeitos sonoros** por evento, com nível e ataque medidos para nunca sumirem
  sob a fala.
- **Imagens e vídeos ilustrativos** buscados no Pexels, na Wikimedia e no
  Google (marcas e pessoas específicas).

### Fase 3 — trilha sonora

- Música gerada por IA (Treblo) ou um arquivo seu — mixada com a voz e entregue
  a −14 LUFS, o padrão das plataformas.

### Material que está na internet (yt-dlp)

- **Editar direto de um link**: YouTube, Drive e afins viram fonte como
  qualquer outra — inclusive só um trecho (*"baixa do minuto 12 ao 25"*).
- **Extrair B-rolls de vídeos online**: peça *"preciso de B-rolls de X desse
  vídeo"* — o Avelin baixa, assiste, encontra os momentos certos e entrega os
  clipes cortados no formato do seu projeto. **Atenção aos direitos**: vídeo de
  terceiros geralmente não é licenciado para reuso; para material seguro, o
  caminho é o Pexels/Wikimedia, que já estão integrados.
- **Replicar um estilo de edição**: aponte um vídeo de referência e peça
  *"edita no estilo desse aqui"*. O Avelin desmonta a edição — ritmo de corte,
  estrutura do roteiro, padrão de legenda, zooms, relação som-corte — e aplica
  a receita no seu material bruto.

---

## Motion Kits — o gosto aprendido dos Broll Overlays

O formato de edição **Broll Overlay** (animações de ênfase por cima do vídeo)
veste um **Motion Kit**: paleta, papéis tipográficos, formas (raios, molduras,
pills, anéis), sombras e os NÚMEROS do movimento (staggers, durações, easings).
A divisão de camadas é a mesma de todo o resto do Avelin:

- **O repositório entrega o mecanismo e um kit default** —
  `assets/motion/default.json`, vermelho (`#ff3b30`) sobre preto, tipografia
  genérica. É o que você recebe ao clonar.
- **O SEU kit vive fora do clone**, em `~/.avelin/motion/kit.json` — como as
  preferências e a marca. Ele nasce de um **aprendizado**: aponte para a IA uma
  pasta de referências suas (landing pages, CSS, SVGs, screenshots, um
  designkit.md) e peça para destilar o kit. Cada usuário tem o seu; o kit não
  sobe em push nem morre em `git clean`.
- **As cores herdam da sua marca** (`~/.avelin/brand.json`): accent e cor
  profunda da marca vencem o que o kit declarar. O kit manda na FORMA e no
  MOVIMENTO; a marca, na COR. Sem marca salva, vale o que está no kit — e no
  default, isso é o vermelho/preto.

Para inspecionar o kit ativo já resolvido:

```bash
uv run python helpers/motion_kit.py --mostrar
```

## Atualizar

Para trazer a versão mais nova:

**Windows:**

```powershell
git -C "$env:USERPROFILE\.claude\skills\ave" pull --ff-only
```

**macOS / Linux:**

```bash
git -C "$HOME/.claude/skills/ave" pull --ff-only
```

`clone` baixa pela primeira vez; `pull` atualiza o que já existe. Rodar o
`clone` de novo não funciona — ele reclama que a pasta já existe.

Se o anúncio da versão disser que houve mudança de dependências, rode o
`uv sync` de novo depois do pull.

---

## Problemas comuns

**`uv` (ou `git`, ou `ffmpeg`) não é reconhecido como comando (Windows)** — são
as duas causas mais comuns, nessa ordem:

1. **Você pulou o passo 1.** Rode o `winget install` da instalação, reabra o
   PowerShell e tente de novo. Não precisa refazer o `git clone` se ele já
   funcionou.
2. **Você não reabriu o PowerShell** depois do `winget install`. O Windows só
   enxerga programas recém-instalados numa janela nova — feche essa e abra
   outra.

Se o `winget` não existir na sua máquina (Windows 10 mais antigo), instale o
`uv` pelo instalador oficial:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Uma janela pedindo para instalar as Ferramentas de Linha de Comando (macOS)**
— normal na primeira vez, o Mac não vem com `git` de fábrica. Aceite, espere
terminar e rode o `git clone` de novo.

**`destination path already exists and is not an empty directory`** — a skill já
está instalada. Você queria o comando de atualizar (`git pull`), não o de
instalar.

**`ModuleNotFoundError` ao usar a skill** — faltou o passo 4, o `uv sync`.

**O Claude não encontra a skill** — confirme que a pasta está exatamente em
`.claude/skills/ave` dentro da sua pasta de usuário, e reinicie o Claude Code.

---

## Para quem quer contribuir com código

O caminho acima coloca o repositório dentro de `.claude/skills/`, que é o mais
simples para quem só quer usar. Se você vai desenvolver a skill e prefere o repo
junto dos seus outros projetos, clone onde quiser e crie um symlink para a pasta
de skills — o `install.md` documenta esse formato.

---

## Licença

O **código** está sob MIT — veja [LICENSE](LICENSE). O motor de corte tem como base o projeto edvid (© 2026 Creator Factory); os avisos de copyright originais estão preservados no arquivo de licença.

**Uma exceção, e ela importa:** `assets/overlays/ig_follow.mov` e
`ig_follow_profile.mov` reproduzem a interface do Instagram, marca da Meta
Platforms, Inc. Este projeto não tem relação com a Meta nem é endossado por ela.
A MIT cobre o código e não pode conceder direito sobre marca de terceiro — esses
dois arquivos acompanham o pacote para **uso pessoal** (o CTA no fim dos seus
vídeos, o mesmo uso de quem grava a tela do app). Redistribuir ou empacotar em
produto seu é outra conversa, e a autorização vem da Meta, não daqui. Os
detalhes estão em [assets/overlays/README.md](assets/overlays/README.md).

Todo o resto de `assets/` — os 20 efeitos sonoros, as texturas, os estilos —
segue a MIT como o código.
