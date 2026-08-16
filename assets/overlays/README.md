# Overlays

Camadas que cobrem o quadro inteiro: grão, vazamento de luz, poeira, arranhão de
filme, vinheta, halação. Solte os arquivos aqui e referencie pelo NOME em
`edit-data.json`:

```json
"overlays": [
  {"file": "grao.png",  "start": 0, "end": 57.3, "blend": "screen", "opacity": 0.22},
  {"file": "luz.webm",  "start": 4.7, "end": 9.8, "blend": "screen"}
]
```

`.png` e `.jpg` entram como imagem parada; `.mp4`, `.webm` e `.mov` entram como
vídeo em laço. `start`/`end` são segundos na linha de tempo do CORTE.

## Textura cobre o quadro; peça de interface, não

Duas coisas diferentes moram nesta pasta, e a diferença é de TAMANHO:

- **textura** (grão, vazamento de luz, poeira, vinheta) vem do tamanho do quadro
  e cobre tudo — `inset:0` com `object-fit:cover`;
- **peça de interface** (o `ig_follow`, 544×272) tem tamanho próprio e um lugar
  no quadro.

O composer decide pelo arquivo: **abaixo de 70% da largura do quadro, entra no
tamanho nativo, centrado**, e avisa numa linha. Acima disso, cobre o quadro como
sempre. Isto existe porque o padrão de cobrir tudo inflava o `ig_follow` para
1080×1920, e ele virava uma tarja azul com "Seguir" gigante sobre o rosto.

Para mandar você mesmo — e declarar `width` sempre vence a decisão automática:

```json
{"file": "ig_follow.mov", "start": 55.4, "end": 57.2,
 "width": 60, "left": 50, "top": 70}
```

`width` em % da largura do quadro; `left` é o CENTRO da peça, em % da largura;
`top` é a borda de cima, em % da altura. A proporção vem do arquivo.

**Colisão se confere no render, não no papel.** A legenda ocupa uma faixa fixa e
não sai da frente sozinha: no #29 o botão a 58% caiu em cima dela e a 74% ficou
folgado — a legenda estava em 63,2%–68,2%, medido no quadro.

## Onde a camada fica

Acima do vídeo, das inserções e dos gráficos sob medida — e **abaixo da
legenda**. Grão por cima do texto suja a leitura, que é a única coisa da tela
que não pode ficar suja.

## `blend` e `opacity`: escolha um, e saiba por quê

| | quando serve |
|---|---|
| `"blend": "screen"` | arte **clara** sobre preto: grão branco, vazamento de luz, poeira, halação. O preto some sozinho, sem matte |
| `"blend": "multiply"` | arte **escura** sobre branco: vinheta, sujeira, sombra |
| sem `blend` | o arquivo já tem alfa de verdade (PNG/WebM `yuva420p`) |

**Com `blend`, o `opacity` NÃO é aplicado como opacidade** — e isso não é
capricho. Opacidade abaixo de 1 cria contexto de empilhamento e **mata a
mistura**: a camada reaparece como uma chapa opaca no exato quadro em que
deveria estar suave. O composer converte para `filter: brightness()`, que no
`screen` faz o mesmo trabalho (fonte mais escura contribui menos) sem quebrar o
blend. Regra registrada na Hard Rule 16 e aprendida na roleta do #29.

## Os overlays desta biblioteca, e para que serve cada um

Nomes fixos — o composer e o agente procuram por eles.

### Fecho de vídeo (CTA)

| arquivo | quando |
|---|---|
| `ig_follow` | CTA **"siga o perfil"** no Instagram. Overlay simples: entra no fim, sem preparo nenhum |
| `ig_follow_profile` | mesma função, versão em **chromakey** — mais rico, mas **exige a foto do usuário** para preencher o espaço do avatar |

O `ig_follow_profile` não é o `ig_follow` melhorado: é outro fluxo. Sem a foto
ele entra com um buraco no lugar do rosto, que lê como render quebrado. **Se a
foto não estiver no projeto, use o `ig_follow` e diga por quê** — nunca entregue
o chromakey vazio.

Sendo chromakey, ele precisa de key na composição, não de `blend`. O verde
não sai com `screen` nem com `multiply`: ou a matte vem pronta no arquivo
(alfa), ou o verde tem de ser removido antes — mesma decisão da Hard Rule 16,
e a resposta aqui é alfa.

### Profundidade

| arquivo | quando |
|---|---|
| `Element_shaddow_overlay 1` e `2` | sombra para dar **profundidade a elementos quadrados ou retangulares** — cartões, inserções, molduras |

São sombra, ou seja, arte **escura**: vão de `multiply`, nunca de `screen`.
Com `screen` a sombra simplesmente desaparece, que é o comportamento correto
do blend e o erro mais fácil de cometer aqui.

Posicione atrás do elemento, não sobre ele. Uma sombra por cima do cartão
escurece o próprio cartão em vez de assentá-lo no fundo.

### Legibilidade de texto

| arquivo | quando |
|---|---|
| `Black_Blur_overlay 1` e `2` | base para **elementos de tela: textos e legendas**. Escurece e borra o fundo atrás do texto para o texto sobreviver a qualquer cena |

Este é o único que quebra a regra de ficar abaixo da legenda: ele existe
**para** a legenda, então entra logo abaixo dela e acima de todo o resto.
Também é `multiply`, e a intensidade importa — forte demais vira uma tarja e
mata a imagem que a legenda deveria estar acompanhando.

Vale lembrar da medição que a série já fez: na parede clara deste projeto
**nenhum laranja passa a régua de contraste** (o melhor deu 1,74:1 contra 3,0).
Um `Black_Blur` sob a legenda é exatamente o que resolve isso sem trocar a cor
da marca.

## Conferir antes de usar

O erro que não aparece olhando o arquivo sozinho é **fundo que não é preto de
verdade**: cinza residual vira véu sobre o vídeo inteiro. Meça no próprio
quadro em vez de chutar:

```bash
uv run python -c "
from PIL import Image; import numpy as np, sys
a=np.array(Image.open('assets/overlays/grao.png').convert('RGB'))
print('canto mais claro:', a[:20,:20].reshape(-1,3).max(0))"
```

Acima de ~`[30,30,30]` o `screen` vai clarear a cena toda. Esmague com
`colorlevels` usando o máximo MEDIDO como piso.

## Seus arquivos não vão para o git

`assets/overlays/*` está no `.gitignore` (menos este README). O pacote é seu, e
binários grandes num fork que acompanha o upstream atrapalham os dois lados —
mesmo motivo pelo qual `templates/` já ficava de fora.
