# CTA de fechamento

A última aba das **Camadas do render** no editor. Um modelo por vídeo, gravado
em `edit-data.json → cta`; quem monta é `helpers/cta.py`, chamado pelo
`compose_shortform.py`.

```json
"cta": {"modelo": "instagram-card", "arroba": "@seuperfil"}
```

| modelo | o que o espectador vê | foto | duração |
|---|---|---|---|
| `siga-perfil` | cápsula escura no topo que abre a partir da foto: "Siga o perfil" + @, um cursor aperta "Seguir" → "Seguindo ✓". Botão e anel na cor de destaque | **sim** | 5,8 s |
| `instagram-card` | o ícone do Instagram vira um cartão com foto, @ e selo, "Seguir" → "Seguindo", e fecha | **sim** | 4,96 s |
| `instagram-simples` | só o botão "Seguir" → "Seguindo" (`assets/overlays/ig_follow.mov`), logo acima da legenda | não | 3 s |

O `siga-perfil` nasceu sob medida no "Mais viral, mais raso" (2026-10-13) e
virou modelo, com foto, @ e cor como variáveis.

## Quando entra

O **clique do botão cai no último "segue/siga/seguir"** da fala
(`cta.momento_clique`). Sem essa palavra, o CTA termina junto com o vídeo. E
**caber inteiro vence**: se o "segue" está tão perto do fim que o fechamento
seria cortado, o CTA adianta o que faltar.

Para mandar você mesmo: `start` (segundos do corte), `top`/`left`/`width` (%
do quadro; `left` é o centro), `verificado: false` (tira o selo do card),
`som: false`, `volume`.

No `siga-perfil` (desde 2026-10-16) `top` é a borda de cima VISÍVEL da
cápsula e `width` a largura dela (padrão 700px = 64,8%) — a escala nasce do
topo, então encolher não a tira do lugar. Sem os três, ela fica no topo como
sempre. **Na altura da legenda** (vídeo sem fala, pedido do usuário):
`"top": 77.5, "width": 55.1` — pé em 1590px (330 do fundo) e 595px de largura,
o que cabe centrado à esquerda da coluna de ícones (área segura). E `clique`
(segundos dentro do modelo, padrão 5,08) encurta a espera antes do clique:
num vídeo de 10s, `"clique": 2.6` faz o CTA durar 3,3s em vez de 5,8s.

## A foto

É do projeto, em `hyperframes/cta/perfil.png`, quadrada e recortada em volta
do rosto (Haar). Três caminhos no editor — **Subir foto**, **Usar quadro do
vídeo** (o quadro que está no player) e **Colar print** (ou Cmd+V com a aba
aberta) — e um pela linha de comando:

```bash
uv run python helpers/cta.py foto <edit> <imagem>
uv run python helpers/cta.py foto <edit> --quadro 12.4
```

Toda foto enviada também vai para `~/.avelin/cta/perfil.png`, e o projeto sem
foto herda essa — a foto do perfil é de quem faz, como a cor do brand. O @
segue a mesma ordem: o do projeto, senão `~/.avelin/brand.json → instagram`
(o editor grava lá o que for digitado).

**Sem foto, a Fase 2 recusa** `siga-perfil` e `instagram-card` pelo nome
(`phase2.check_cta`). Um cartão com buraco no lugar do rosto lê como render
quebrado.

## Como o card foi feito — e por que não é o .mov direto

O `ig_follow_profile.mov` é chromakey **com a foto e o @ do autor gravados**.
Usado como veio, ele tinha dois defeitos: o verde não sai com `blend`, e todo
usuário entregaria o rosto e o nome de outra pessoa. `cta.py preparar` resolve
os dois uma vez, no asset:

1. mede, quadro a quadro, o círculo da foto (cresce na entrada, pulsa no
   clique, desce no fechamento), a faixa do @ (entra digitado) e o miolo preto;
2. **pinta de preto** a foto e o @ gravados — o miolo já é preto, o buraco não
   aparece;
3. tira o verde → `instagram-card.webm` (VP9 com alfa, `yuva420p`);
4. grava o mapa em `instagram-card.json` e o som dos cliques em `.mp3`.

Na composição (`instagram-card.html`), a foto e o @ do usuário entram em HTML
por cima, nas posições do mapa, recortados pelo miolo. Nada é queimado no vídeo
do projeto (Hard Rule 10) — o que se processou foi o asset da biblioteca.

Para refazer a partir de outro .mov com o mesmo desenho:

```bash
uv run python helpers/cta.py preparar --card <mov> --simples <mov>
```

## Arquivos

| arquivo | o que é |
|---|---|
| `siga-perfil.html` | modelo da cápsula (`{{FOTO}}`, `{{ARROBA}}`, `{{ACCENT}}`, `{{CLIQUE}}`, `{{ID}}`) |
| `instagram-card.html` | modelo do card: vídeo + foto + @ seguindo o mapa |
| `instagram-card.webm` | o card sem verde, sem foto e sem @ — **gerado** |
| `instagram-card.json` | o mapa quadro a quadro — **gerado** |
| `instagram-card.mp3`, `instagram-simples.mp3` | o som dos cliques, dos .mov de origem — **gerado** |

As miniaturas da aba moram em `assets/preview/cta-card.png` e `cta-simples.png`.

## ⚠️ Marca de terceiro

Card e Simples reproduzem a interface do Instagram, que é marca da Meta
Platforms, Inc. — vale o mesmo aviso de `assets/overlays/README.md`: estão aqui
para **uso pessoal** nos seus vídeos; a licença MIT do repositório cobre o
código, não a marca.
