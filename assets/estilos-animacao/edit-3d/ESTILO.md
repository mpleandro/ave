# Estilo "Animação em 3D" (Edit 3D)

Quadros e vídeo de referência (privados, fora do repositório): `~/.avelin/estilos/edit-3d/` quando existirem nesta máquina.

## O que é — e o que NÃO é

**É uma LINGUAGEM, não um conteúdo.** Elementos em volume, em perspectiva, que
nascem no instante em que a pessoa diz a palavra que eles representam e ilustram
o ASSUNTO DO VÍDEO que está sendo editado.

**Erro já cometido (2026-10-13), e a razão desta página existir:** a primeira
versão copiou o vídeo de referência peça por peça — mapa de profundidade, nuvem
de pontos, esqueleto das mãos, selo "EDITANDO AO VIVO", capítulos com nomes de
técnica. Na referência esses efeitos funcionam porque o assunto DELE é "como a IA
enxerga um vídeo": o efeito é a fala ilustrada. Aplicados num vídeo sobre
"5 conteúdos para ter autoridade", não diziam nada. O usuário reprovou.

Da referência se aproveita SÓ:
- elementos que entram SINCRONIZADOS com a palavra que os nomeia;
- volume e perspectiva de verdade (objeto 3D, texto/ícone extrudado, câmera
  virtual girando o elemento), não recorte chapado;
- acabamento: brilho suave, vidro, a paleta da marca;
- legenda curta, frases de impacto com riscado, quando o texto pedir.

**Fica de fora por padrão** (só entra se o ASSUNTO do vídeo for tecnologia, IA,
edição ou visão computacional, ou se o usuário pedir pelo nome): mapa de
profundidade, nuvem de pontos, esqueleto de mãos, rótulos de confiança
("ROSTO 0,99"), selo "EDITANDO AO VIVO", vídeo virando painel de vidro. As
ferramentas existem (`helpers/anim3d_fx.py`), mas são vocabulário de um assunto,
não do estilo.

## O processo

1. **Ler o assunto.** Do transcrito aprovado (`cut_mapped.json`) tirar os
   momentos que carregam o vídeo: conceitos nomeados, números, listas, viradas,
   a chamada final. Não é toda frase: é onde uma imagem ajuda a entender ou a
   lembrar.
2. **Roteiro visual: 4 a 6 momentos** num vídeo de ~1min20 (proporcional à
   duração: ~1 a cada 15–20 s). Para cada um: instante (a palavra-gatilho), a
   frase, o elemento, por que ele ilustra aquilo, duração (2–4 s).
3. **Elemento por momento — literal OU abstrato, escolhido caso a caso:**
   - *literal* quando o objeto explica sozinho: gráfico 3D que sobe para
     "resultado", celular flutuando para "react", caminho com marcos para
     "história/trajeto", troféu, calendário, lupa;
   - *abstrato da marca* quando o conceito não tem objeto: "autoridade",
     "conexão", "valor", "opinião" → texto/ícone extrudado, linhas de luz,
     formas na identidade do usuário.
   Ícones e textos em volume servem aos dois.
4. **Aprovação do roteiro:** na PRIMEIRA vez que o usuário usa o estilo, o
   roteiro vai para ele (lista curta, uma linha por momento, `AskUserQuestion`
   ou mensagem) ANTES de qualquer render. Depois disso, decidir e informar em
   uma linha por momento — preferência registrada do usuário (2026-10-13). O
   registro de que a primeira vez já aconteceu mora em
   `~/.avelin/preferencias.json` → `anim3d.roteiroAprovado`.
5. **Montar e renderizar.**

## Regras de composição

- **Só na FRENTE.** Os elementos flutuam por cima do vídeo; nada atrás da
  pessoa (decisão do usuário, 2026-10-13 — mais rápido, sem camada de recorte).
- **Nunca sobre o rosto.** O rosto ocupa o terço de cima em talking head
  vertical: elementos na faixa do peito (y ≈ 860–1340 em 1080×1920) ou nas
  laterais, sempre ACIMA da faixa da legenda com ≥ 60 px de folga (karaokê:
  `paddingBottom` ~435 → legenda em y ≈ 1400–1480).
- **Margem lateral de 190 px** quando o elemento estiver gravado no vídeo base:
  a câmera dinâmica aproxima até ~1,2× e corta ~100 px de cada lado. Elementos
  na composição (por cima da câmera) não sofrem isso.
- **Entra na palavra, sai antes da próxima ideia.** Entrada 0,3–0,5 s com
  volume/rotação, permanência curta, saída rápida. Um elemento por vez.
- **Som:** cada entrada com um efeito discreto (`element`/`callout`), o
  momento de maior peso com `impact`.
- **Paleta e fontes da marca** (`~/.avelin/brand.json`; se houver `identidade`,
  ler o arquivo apontado — regras de fogo do kit Ignis valem: só abertura,
  virada e fechamento, ≤ 25% da área, nunca atrás de texto).

## Como implementar (HyperFrames)

- Cada momento é um gráfico sob medida em `compositions/<id>.html`, listado em
  `edit-data.json → brollGraphics[]` com o `start`/`end` do roteiro.
- Volume de verdade: **Three.js** dentro da composição (geometria extrudada de
  SVG/texto, luz, câmera girando), com a cena dirigida por um tween GSAP em
  tempo absoluto — determinístico e à prova de seek. CSS 3D (`perspective` +
  `rotateY`) serve para cartões e textos simples.
- Objetos literais: modelar com primitivas/extrusão de SVG (ícones) ou glTF de
  licença livre (CC0) copiados para o projeto — nunca puxar de URL no render.
- Fontes locais declaradas com `@font-face { src: local(...) }` — o `check` do
  HyperFrames bloqueia família sem declaração.
