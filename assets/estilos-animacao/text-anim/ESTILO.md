# Estilo "Text Anim" — motion graphics de tipografia cinética
Quadros e vídeo de referência (privados, fora do repositório): `~/.avelin/estilos/text-anim/` quando existirem nesta máquina.

## O que é
Vídeo SEM rosto (ou trechos sem rosto): tela escura onde o TEXTO DA NARRAÇÃO é a imagem. Cada frase falada vira uma cena; o texto nasce no ritmo da voz, palavra a palavra.

## Padrões
1. **Fundo**: quase-preto (#0B0B0B) com grade fina (~40px, linha 4–6% branco) e vinheta. Às vezes um piso em perspectiva (grade 3D sumindo no horizonte).
2. **Revelação sincronizada à fala**: cada palavra aparece no instante em que é dita (carimbo da transcrição). Três modos:
   - *máquina de escrever* com cursor (`|`) — prompts e código, fonte mono;
   - *fade + blur → nítido* por palavra/letra, com rastro de brilho saindo da última letra ("What if I told you…");
   - *slam* — palavra gigante entra de uma vez (escala 1.08→1, 2–4 quadros).
3. **Hierarquia em 2 níveis**: frase de apoio pequena (sans 600, branco) em cima à esquerda + PALAVRA-CHAVE enorme (sans 900, caixa alta, 2 linhas: branco + accent). Ex.: "you can create / MOTION / GRAPHICS", "This is / CLAUDE / OPUS 5.5".
4. **Cor**: branco + UM accent laranja-vermelho; dentro de cada frase as palavras-chave mudam para o accent ("Claude doesn't **actually generate** an **MP4**"). Palavras ainda não ditas ficam em cinza 30% (sombra do texto que vem).
5. **Cartela cheia de batida**: fundo 100% accent, texto preto gigante, UMA palavra por corte rápido ("THIS / IS / GETS / CRAZY.") — o clímax. Ícone ↵ gigante como transição.
6. **Diagramas que explicam a fala**: caixas finas de UI (labels mono minúsculos: CLAUDE → MCP SERVER → AFTER EFFECTS) ligadas por linhas que se desenham; um ponto de luz/faísca corre pela linha; ✕ vermelho riscando o caminho errado; curva de easing num gráfico; código digitando ao lado de um preview; formas (quadrado, círculo) com coordenadas.
7. **HUD/metadados**: microtextos mono por toda parte (t = 2.28 s, coordenadas, contadores, "PROMPT 02", régua de frames) — dão textura técnica, nunca disputam leitura.
8. **Câmera virtual**: a cena é uma tela maior que o quadro; a câmera desliza/zoom entre blocos (texto sai pela borda enquanto o próximo entra). Fita de filme (frames lado a lado) para "frame by frame".
9. **Quebra de cenário**: troca para um cenário papel/creme (formulário técnico "FORM 2-B", caixas e setas desenhadas, risco vermelho à mão cortando o processo antigo) — contraste claro×escuro para virar o argumento.
10. **Ritmo**: uma ideia por frase, troca de cena a cada 1,5–3s, NUNCA texto parado sem movimento; partículas/faíscas no ponto de energia.

## Como aplicamos (Avelin / HyperFrames)
- Motor: HyperFrames + GSAP (já é o motor da Fase 2); cenas como gráficos sob medida em `compositions/` sincronizados pelos carimbos de `cut_mapped.json`.
- Paleta e fontes: as da marca do usuário (`~/.avelin/brand.json` — accent, fontMain/fontAccent; se houver `identidade`, leia o arquivo apontado). Sem marca: fundo #0B0B0B, accent da aba Estilo, sans 800–900 na palavra-chave, mono nos microtextos.
- Pode ser o vídeo inteiro (narração sem rosto) ou blocos inseridos entre falas de câmera.
