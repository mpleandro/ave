# Efeitos sonoros

Solte arquivos `.mp3` aqui. Não precisa gerar nada com IA — qualquer pacote de
SFX serve, desde que passe nas duas conferências abaixo.

**Confira antes de usar:**

```bash
uv run python helpers/sfx.py assets/sfx/*.mp3
```

## As duas regras, e por que elas existem

Ambas foram aprendidas ouvindo, não olhando. Nos dois casos a mixagem parece
correta e não se escuta nada.

### 1. Nível

Abaixo de **−12 dB** de pico o efeito some sob a fala. Medido neste pacote:

| arquivo | pico | veredito |
|---|---|---|
| `caption-scratch.mp3` | −0.5 dB | ok |
| `caption-click.mp3` | −0.8 dB | ok |
| `riser.mp3` | −1.0 dB | ok |
| `cut-click.mp3` | −2.0 dB | ok — é o clique que lê |
| `whoosh.mp3` | −2.3 dB | ok |
| `pop.mp3` | −4.1 dB | ok |
| `click.mp3` | −4.9 dB | ok |
| `click1.mp3` | −11.3 dB | no limite |
| `tictac.mp3` | −13.7 dB | **some sob a fala** |
| `click2.mp3` | −25.0 dB | **inaudível** |

Um arquivo baixo não é "um efeito discreto" — é um efeito que não existe. Subir
o volume na mixagem para compensar sobe o ruído junto.

### 2. Onde está o ataque DENTRO do arquivo

Muitos arquivos têm silêncio antes da batida. Medido aqui: `caption-scratch`
233ms, `pop` 140ms, `caption-click` 158ms, `riser` 465ms.

Isso importa porque um efeito agendado no instante do evento chegaria atrasado
por essa margem — no caso do `caption-click`, 158ms depois, quando um efeito de
230ms já teria acabado.

**Você não precisa aparar o silêncio.** O compositor mede e compensa sozinho,
começando o arquivo antes para o ataque cair no lugar certo. A medição acontece
em tempo de composição, de propósito: assim trocar um arquivo por outro nunca
reintroduz atraso silencioso.

## Para registrar um efeito novo num evento

Os eventos e seus arquivos vivem em `assets/styles/variants.json`, na chave
`sfx`. Cada entrada tem `file` e `volume`. Eventos existentes:

`hook` · `flash` · `soloWord` · `circled` · `callout` · `chapter` · `broll`

Trocar o arquivo de um evento é editar essa entrada — o resto se ajusta sozinho.

## Papéis novos — a biblioteca pessoal

Dez efeitos além do pacote base, declarados em
`assets/styles/variants.json`. Vão versionados junto com o repositório.

> **Se você for adicionar os seus:** confira a licença antes. Pacotes como o
> Envato Elements permitem usar nos seus vídeos e **não** permitem
> redistribuir o arquivo — num repositório público isso é redistribuição.
> Quando for o caso, deixe-os fora com uma regra no `.gitignore` e descreva o
> papel aqui, para quem clonar saber o que falta.

| papel | arquivo | pico | quando |
|---|---|---|---|
| `tension` | `riser-tension.mp3` | −0.0 dB | riser de 9,1s — tensão que resolve na virada; é o riser do gancho |
| `intro` | `riser-short.mp3` | −10.4 dB | riser de 2,3s para abertura, quando o de 9s não cabe |
| `transition` | `glitch.mp3` | −3.9 dB | corte de imagem com quebra — a transição padrão |
| `transitionCut` | `glitch-short.mp3` | −4.1 dB | o mesmo em 0,57s, para cortes secos em sequência |
| `transitionSoft` | `film-burn.mp3` | −7.9 dB | queima de filme; transição quente, menos agressiva |
| `element` | `whoosh-soft.mp3` | −0.0 dB | elemento ENTRANDO (cartão, gráfico, legenda) |
| `elementOut` | `whoosh-long.mp3` | −10.2 dB | elemento SAINDO — cauda mais longa |
| `tick` | `click-tick.mp3` | −1.4 dB | marcação seca: item de lista, número, contagem |
| `impact` | `impact.mp3` | −3.0 dB | ênfase numa palavra ou numa revelação |
| `camera` | `camera.mp3` | −6.8 dB | obturador; corte que finge foto, zoom duro |

**O volume sai do pico medido**, não do gosto: arquivo mais quente pede número
menor. É a mesma convenção dos sete que já existiam — `whoosh.mp3` mede −2,3 dB
e vale `0.10`. Um efeito a −10 dB no mesmo `0.10` simplesmente não é ouvido.

Dois deles pedem cuidado: `riser-tension` e `whoosh-soft` medem **0,0 dB** —
estão no teto, e é por isso que ficaram com volume baixo. Subir esses dois é o
caminho mais curto para a mixagem final clipar.
