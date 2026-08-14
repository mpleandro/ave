# Avelin — identidade visual sobre o edvid

Isto **não** fica dentro de `~/.claude/skills/edvid/`. Aquele diretório é um clone git
com upstream em `github.com/fillrochaa/edvid`, e tudo que a gente editar lá vira
conflito no próximo `git pull`. Medido em 2026-08-09: o upstream estava 10 commits à
frente e mexia justamente em `assets/preview/app.js` e `references/shortform.md` —
os dois arquivos que a identidade precisaria tocar.

## Por que funciona

A Fase 2 do edvid **copia** o template Remotion para dentro do projeto. Então o
overlay corrige a cópia, nunca o template. O repo continua limpo e o pull passa.

A única coisa que não dá para resolver por cópia é o app do preview, porque o
servidor o serve no lugar. Ali a pegada é de **2 linhas guardadas**:

```
assets/preview/app.js      /* AVELIN-OVERLAY */ if (window.EDVID_LOCAL) …install({…})
assets/preview/index.html  <script src="/assets/styles.local.js"></script>
```

Ambas idempotentes. `styles.local.js` é **untracked** — `git pull` não encosta nele.

## Uso

```bash
O=~/.claude/edvid-avelin

python3 $O/overlay.py pull                            # ATUALIZAR O EDVID É POR AQUI
python3 $O/overlay.py apply-project <edit>/remotion   # depois do scaffold da Fase 2
python3 $O/overlay.py check                           # relatório de deriva
```

**Não rode `git pull` puro no edvid.** Com as 2 linhas no lugar o git não conflita —
ele **aborta**: *"your local changes to the following files would be overwritten by
merge"*. Medido contra o upstream real, não suposto. `overlay.py pull` resolve
tirando os hooks, puxando e recolocando; testado subindo de `eea7453` até `d914b64`,
10 commits, com as âncoras sobrevivendo ao código novo.

Se um dia a âncora sumir (o upstream reescreveu aquele trecho), `apply-skill` diz
qual e para de mexer, em vez de inserir no lugar errado.

## O que tem aqui

| pasta | o quê | destino |
|---|---|---|
| `brand/avelin.json` | paleta, fontes, papéis, vocabulário de movimento | `public/brand.json` do projeto |
| `shortform/src/` | `EditorialCaptions.tsx` | `src/` do projeto |
| `helpers/` | `caption_style_editorial.py` (o diretor) | roda de fora |
| `preview/` | `styles.local.js` (aba Estilo) | `assets/preview/` (untracked) |
| `fixes/` | correções de BUG do template | `src/` do projeto |
| `docs/` | as adições que eu tinha feito nos docs do skill, salvas como diff | — |

**`fixes/` é separado de `brand/` de propósito.** Aquilo são bugs do template, não
identidade: o estilo empilhado ignorando `captions.windows`, e `SplitInsert` sem
honrar `focusY`/`zoom`. O lugar certo deles é um PR para o upstream — aqui é
compasso de espera. `overlay.py check` guarda o sha do arquivo original de onde cada
fix saiu e avisa quando o upstream mexe nele, que é quando o fix ficou velho.

## A marca — `brand/avelin.json`

Vem do **design kit do site** (SiteKit v3.1: `index.html`, `styles/Style.css`,
`js/index.js`), com os nomes dos tokens preservados de propósito. A ideia inteira do
arquivo é ser *o mesmo vocabulário dos dois lados*; renomear quebra isso.

- **Fontes:** `Open Sans` (400/600/700) e `Libre Baskerville` itálico 400. As duas
  estão no Google Fonts, então não há substituta nem fonte licenciada versionada.
  A serif é **sempre** 400 — o itálico dela é o recurso expressivo, não uma variante.
- **Accent:** `--laranja #FF6B1A`. `--laranja-suave #FFAD7A` é o acento-sobre-escuro
  do site, guardado para uma tomada escura demais para o #FF6B1A.
- **Sobre vídeo os papéis do site invertem:** `--offwhite #F5F2EE` vira a cor de
  leitura e `--azul-claro #7A95AA` a esmaecida.
- **Sombra:** a assinatura do site é Y grande, blur grande, **spread negativo**, e
  tingida de `rgba(13,33,55,.x)` — azul-noite, não preto. Sombra preta lê como outra
  marca de perto.
- **Easing-mãe:** `cubic-bezier(.2,.8,.2,1)`. É o padrão de qualquer coisa Avelin.

### O estilo Editorial

É o padrão `.amber` do site movido para vídeo: serif itálico laranja no destaque,
conectivos esmaecidos em volta. Seis papéis por palavra, e o contraste entre eles
**é** o estilo:

| papel | face | cor | tamanho | entrada |
|---|---|---|---|---|
| `ctx` | Open Sans 400 | `--azul-claro #7A95AA` | 0.62em | fade |
| `stress` | Open Sans 700 | `--offwhite #F5F2EE` | 1.0em | fade |
| `serif` | Baskerville itálico | `--offwhite` | 1.12em | serifIn |
| `serifAcc` | Baskerville itálico | **`--laranja`** | 1.12em | serifIn |
| `punch` | Open Sans 700 | **`--laranja`** | 1.0em | glow |
| `num` | Baskerville itálico | **`--laranja`** | 2.0em | pop |

Um acento por cue, escolhido pelo diretor. Achatar os papéis e vira legenda comum.

```bash
python3 $O/helpers/caption_style_editorial.py \
  --transcript <edit>/transcripts/cut.json \
  -o <edit>/remotion/public/caption-editorial.json
```

Depois é só `"captions": {"style": "editorial"}` no `edit-data.json`. O accent do
vídeo (`captions.accent`, o que a aba Estilo grava) sobrepõe o da marca; o resto
continua vindo da marca.

### Coisas medidas em render, não supostas

- **`lineHeight: 1.0` sozinho quebra.** A caixa da linha fica exatamente do tamanho
  da fonte e as ascendentes/descendentes da serif itálica invadem a linha de baixo —
  num render de teste "ferramenta" ficou por cima de "gratuita". A entrelinha vem de
  um `marginTop` escalado pelo maior papel *daquela* linha, não de uma constante: um
  `num` de 2.0em precisa do dobro do espaço de uma palavra de 1em.
- **A Baskerville aguenta vídeo melhor que uma Garamond.** Comparado lado a lado no
  mesmo frame: a haste mais grossa sobrevive à compressão e ao fundo movimentado.
  Foi por isso que a fonte certa da marca também é a escolha técnica certa aqui.
- **A ordem das palavras precisa ser forçada monotônica.** No emendo de um J-cut o
  Whisper carimba a primeira palavra do take que entra ANTES do fim da anterior, e
  a linha se revela fora de ordem.
- **`ctx` cinza sobre imagem clara quase some.** Na tela dividida, use
  `captions.windows` para estacionar a legenda sobre a metade escura.
- **`editorialOffsetY` padrão 0.2** põe o bloco acima da cabeça do apresentador em
  vertical — testado, cai em fundo limpo. É por vídeo, não é lei.

## Vocabulário de movimento para gráficos e b-roll

O site tem um contrato de animação declarado por atributo (`data-split`,
`data-reveal`, `data-clip`) — é a "API" da camada de animação dele. Esses padrões
estão em `motion._graphics` do brand kit, para que um gráfico feito para vídeo se
mova como o site se move:

| entrada | o quê | duração |
|---|---|---|
| `reveal` | `y: 28 → 0` + fade | 0.9s |
| `clip` | `inset(0 0 100% 0) → inset(0)`, revela de cima | 1.1s |
| `splitLines` | linhas sobem `yPercent 110 → 0`, stagger 0.12 | 1.0s |
| `splitWords` | palavras sobem `yPercent 60 → 0`, stagger 0.012 | 0.6s |
| `parallax` | `y: -50` ao longo da cena | — |
| `ringSpin` | anéis 60s / 45s reverso | loop |

Em `graphics` estão os raios (pill 999, imagem 22, topo-de-folha 20), as três
sombras do site e a moldura de mockup (borda 6px azul-noite, radius 26) — o
suficiente para um card de vídeo sair igual a um card do site.

**Atenção ao portar:** no site esse contrato é CSS transition + GSAP. Em Remotion
**transição CSS não renderiza** — tudo vira `useCurrentFrame()` + `interpolate()`.
As durações e easings acima já estão nessa forma.

## Pendente

- Levar `fixes/` para um PR no upstream, em vez de carregar cópia.
- Nenhum SVG foi entregue junto do kit — quando houver, `graphics` é onde os
  tokens dele encaixam.
- O cursor customizado e o smooth-scroll (Lenis) são decisões de marca **do site**
  e não têm equivalente em vídeo. Ficaram de fora de propósito.
