# A.V.E. — Avelin Video Edit

Editor de vídeo por conversa. Você joga o material bruto numa pasta, abre seu
agente ali dentro e diz *"edita isso num vídeo de lançamento"*. Ele transcreve,
escolhe as melhores tomadas, corta os silêncios, aplica a correção de cor e te
mostra o resultado para aprovação — depois disso entram legendas, gráficos e
trilha.

Funciona em **short-form vertical** (Reels/TikTok/Shorts) e **longform
horizontal** (YouTube).

**Tem um vídeo longo — uma aula, uma live, um podcast?** Mande o vídeo inteiro:
o Avelin pergunta se você quer **cortes** ou a **edição** completa. Escolhendo
cortes, ele encontra os trechos com mais chance de viralizar e entrega uma
galeria com nota de 0 a 100, o porquê de cada nota e o download de cada corte
já em pé.

> **Estado atual.** A Fase 2 renderiza em **HyperFrames** (Apache 2.0) — sem a
> restrição de licença comercial do motor anterior. Portados: seis estilos de
> legenda, quatro headlines, três tipos de edição, a câmera dinâmica e as quatro
> camadas de longform. Ainda falta a camada *atrás do sujeito* — a skill recusa
> pelo nome em vez de substituir por algo parecido.

---

## Instalação — um comando

Sem Homebrew, sem senha de administrador, sem chave de API.

**macOS / Linux** — abra o Terminal e cole:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/mpleandro/ave/main/install.sh)
```

**Windows** — abra o PowerShell e cole:

```powershell
git clone https://github.com/mpleandro/ave "$env:USERPROFILE\.claude\skills\ave"; powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\skills\ave\install.ps1"
```

O instalador faz tudo e termina com uma conferência (✓/✗ por peça):

1. **uv** — o instalador de Python, só na sua pasta de usuário.
2. **Avelin** em `~/.claude/skills/ave` — a pasta já é a skill; nada a registrar.
3. **Dependências** — incluindo um **ffmpeg completo** (converte vídeo HDR do
   iPhone) e a **transcrição local** (detector de voz + Whisper), que é o que
   mantém no texto as repetições e os falsos começos que o corte precisa achar.
4. **Modelo de voz** (~1,6 GB, uma vez só).
5. **Conferência real** — transcreve um áudio de teste antes de dizer "pronto".

Se preferir que o agente faça: abra o Claude Code e peça *"instala o Avelin"*.
Ele roda o mesmo comando e explica cada passo.

**Node.js** é o único programa que o instalador não baixa: só a Fase 2
(legendas e gráficos) precisa dele. Se faltar, a conferência avisa; instale a
versão LTS em [nodejs.org](https://nodejs.org) quando quiser a Fase 2. A Fase 1
(corte limpo) funciona sem ele.

**Menos pedidos de aprovação no Claude Code:** a conferência sugere uma lista
para `~/.claude/settings.json` (`permissions.allow`). Com ela, uma edição
inteira roda sem interromper você a cada comando.

### Chaves de API — todas opcionais

Nenhuma é necessária para editar. O agente pede cada uma na primeira vez que o
recurso for usado, e você decide na hora:

| Chave | Para quê |
|---|---|
| `GROQ_API_KEY` / `ELEVENLABS_API_KEY` | transcrição em nuvem, só como reserva em máquina sem motor local |
| `PEXELS_API_KEY` | imagens e vídeos de banco na Fase 2 (sem ela, Wikimedia Commons) |
| `TREBLO_API_KEY` | trilha gerada por IA na Fase 3 (um arquivo de música local não precisa) |
| `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` | imagens de marcas e pessoas que a Wikimedia não tem |

`AVE_OFFLINE=1` no `.env` desliga toda chamada de rede.

---

## Primeiro vídeo

A Fase 1 é um comando (`helpers/fase1.py <pasta> --alvo 60 --tese "…"`): transcrição local, erros de fala, seleção pela tese e proxy. O agente faz uma pergunta no upload (entrega, tese, ritmo) e mostra o corte proposto; o que precisa de decisão sua (retake ou ênfase?) vem como pergunta antes da versão final.

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

### Cortes de vídeos longos (5 minutos ou mais)

Todo vídeo de 5 minutos ou mais começa com uma pergunta: **cortes** ou
**edição**? Escolhendo cortes:

- **Os melhores trechos, com nota.** O Avelin lê o vídeo inteiro, escolhe os
  momentos que se sustentam sozinhos — começando numa ideia e terminando
  nela — e dá a cada um uma nota de viralização de 0 a 100. Bastidor de live
  (chat, brinde, procurar algo na tela) fica de fora.
- **Uma galeria para escolher.** Cada corte com a capa, a nota, o porquê dela
  e um player para assistir antes de baixar. Só entram os cortes com nota 70
  ou mais.
- **O gancho avaliado.** Os 3 primeiros segundos de cada corte são julgados à
  parte: se já seguram, se a frase forte está mais adiante (o Avelin pode
  trazê-la para o começo com um clique) ou se vale gravar outra — com
  sugestões de frase.
- **Melhorias com um clique, cada uma com o score novo:** puxar o gancho, tirar
  os respiros e corrigir os erros de fala (frase repetida, gaguejo, "né",
  "tipo"). A transcrição mostra riscado o que saiu.
- **Legenda separada ou na tela.** Baixe o corte limpo, o arquivo de legenda
  para usar em outro editor, ou o vídeo com a legenda animada já aplicada.
- **Vídeo deitado sai em pé.** Num podcast ou entrevista gravado na
  horizontal, o corte vertical acompanha quem está falando.
- **Editar no Avelin.** Quer finalizar um corte com os efeitos do editor? Um
  botão leva o corte para o Avelin, sem duplicar o vídeo no seu computador.

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

## A sua biblioteca de assets — perguntado uma vez, lembrado sempre

Logo, trilha, efeito favorito, LUT, vinheta, fonte da marca: isso é **seu**, não
do vídeo. Quando você entrega um desses ao Avelin, ele aplica primeiro e depois
oferece guardar — e a partir daí o próximo projeto já nasce sabendo.

- **Onde fica**: `~/.avelin/biblioteca.json` (o índice) e
  `~/.avelin/biblioteca/<tipo>/` (os arquivos), fora do clone, como a marca e as
  preferências. Não sobe em push, não morre num `git clean`.
- **O que é medido no registro**, para o defeito não aparecer só no render: PNG
  sem canal alfa (que viraria um retângulo branco sobre o vídeo), efeito com
  pico baixo demais para ser ouvido sob a fala, efeito cujo ataque está
  centenas de milissegundos DENTRO do arquivo, trilha mais curta que o corte.
- **O que ele pergunta** é só o que nenhuma medição responde: para que aquilo
  serve (*riser*, *reveal*, *abertura*, *marca d'água*) e a condição de uso
  ("só sobre fundo escuro", "esta trilha é só da série de vendas").
- **Acervo grande entra como pasta**, não como 300 perguntas — e pode ficar onde
  está, sem cópia.
- **Uso vira padrão**: o que entrou em 3 vídeos passa a entrar sozinho no papel
  dele; com 2, o Avelin aplica e avisa numa linha; com 0 ou 1, ele pergunta.

```bash
uv run python helpers/biblioteca.py --listar
uv run python helpers/biblioteca.py --registrar ~/Marca/logo.png --tipo logo \
    --nome "Logo branco" --nota "só sobre fundo escuro"
uv run python helpers/biblioteca.py --pasta ~/Music/"Own SFX"/riser --tipo sfx --papel riser
uv run python helpers/biblioteca.py --esquecer <id>
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

Mais fácil ainda: peça no chat *"atualiza o Avelin"*. O Claude baixa a versão
nova, ajeita o que precisar e conta, em português simples, o que mudou para
você.

Você nem precisa lembrar: uma vez por semana o Avelin confere se saiu versão
nova e, se saiu, avisa no começo da edição — até você atualizar. Ele só avisa;
atualizar continua sendo decisão sua. Para conferir a cada edição, ou desligar
o aviso, ponha `AVE_ATUALIZACOES=rodada` (ou `nunca`) no `.env`.

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

**`ModuleNotFoundError` ao usar a skill** — faltou o passo 4, o `uv sync --inexact`.

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
