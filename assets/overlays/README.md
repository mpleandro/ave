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

`.png` e `.jpg` entram como imagem parada; `.mp4` e `.webm` entram como vídeo em
laço. `start`/`end` são segundos na linha de tempo do CORTE.

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
