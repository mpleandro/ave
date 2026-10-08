# HOOKS — o estrategista de gancho do AVE

Leia isto em todo short-form, **na Fase 1, antes de propor a estratégia do
corte** (passo 3 do SKILL.md), e de novo na Fase 2 ao escrever `hook.lines`.
O gancho decide o corte: se a frase mais forte está no segundo 30, a
estratégia é um cold open, e isso se confirma antes do EDL e não depois do
portão.

## O que muda do roteiro para a edição

Este método nasceu como gerador de hooks *para gravar*: ele escreve a frase e
alguém a grava. No AVE o vídeo **já foi gravado**. Por isso:

| Peça do hook | Gerador de roteiro | No AVE |
|---|---|---|
| FALADO 0–3s | escreve | **garimpa** no material (`hook_finder.py`); só sugere regravar se nada servir |
| TEXTO NA TELA | escreve | escreve: é o `hook.lines` |
| FRAME ZERO / VISUAL | dirige a gravação | escolhe entre recursos de edição (tabela "Frame zero") |
| ÁUDIO ([GRITO], [sussurro]) | dirige a fala | vira **design de som**: riser, silêncio, impacto e a trilha. A energia da fala é medida, não pedida |
| LEGENDA com palavra em AMARELO NEON | cor fixa | palavra em destaque no **accent da marca** (`brand.json`, padrão `#FF522D`), nunca uma cor fixa do método |
| RETENÇÃO 3–25s | roteiro | conferência do corte: há um loop aberto que só fecha no fim? |
| CTA | escreve | escreve, com a palavra-chave do perfil |

## 1. Perfil do criador — pergunte UMA vez na vida, não a cada vídeo

Mora em `~/.avelin/hook_perfil.json`, fora do clone, pela mesma razão do
`brand.json`: é dado de uma pessoa, e pedir de novo gasta a paciência que a
pergunta seguinte vai precisar.

```json
{
  "versao": 1,
  "segmento": "marketing para infoprodutores",
  "publico": "experts que vendem curso e travam no conteúdo",
  "tom": "direto, provocador, sem formalidade",
  "mecanismo": "Método IGNIS",
  "cta_palavra": "IGNIS",
  "dores": ["…5 curtas…"],
  "desejos": ["…5 curtos…"],
  "historico": [
    {"projeto": "Mercado Saturado", "data": "2026-10-05", "anatomia": 5,
     "gatilho": "contrarian", "objetivo": "alcance", "frame_zero": "texto_gigante"}
  ]
}
```

**Arquivo ausente?** Antes de perguntar, rascunhe o que der para inferir do
material (o transcrito costuma dizer segmento, público e mecanismo) e pergunte
só o resto, numa mensagem: segmento, público, tom, mecanismo (o nome próprio
do método), 5 dores, 5 desejos e a palavra-chave de CTA. Grave o arquivo e
confirme em uma linha. **Nunca peça de novo o que está lá.** Se o usuário
corrigir um campo em qualquer momento, edite o JSON preservando o resto.

## 2. Por vídeo: objetivo e tese, numa pergunta só

O objetivo **não se infere**. Ele muda o CTA, a trilha e o funil. Junte as duas
coisas num único `AskUserQuestion` no passo 3 da Fase 1:

- **Objetivo** (header `Objetivo`): Vendas · Alcance · Engajamento · Salvamento.
- **Tese** (header `Tese`): duas teses curtas tiradas do TRANSCRITO, porque o
  que o vídeo defende já está gravado, e o usuário escolhe ou reescreve
  (Other). A tese escolhida é a régua do gancho: um gancho que não aponta para
  ela é clickbait que o vídeo não paga.

## 3. Garimpo: o gancho falado se ENCONTRA

```bash
uv run python helpers/hook_finder.py <edit> [--top 8]
```

Ele mede borda limpa (o trecho sai inteiro para virar cold open?), energia e
ritmo contra o próprio falante, se a frase depende do que veio antes, sinais
de anatomia no texto, retomada dentro do trecho e sobreposição com repetição
confirmada no `defeitos_audio.json`. **A nota só ordena a leitura.** Você lê o
top-N e julga o que o número não vê:

1. **Aponta para a tese escolhida?** Se não aponta, está fora, com qualquer nota.
2. **Fica de pé sozinha**, sem o contexto anterior?
3. **Abre uma dívida** (curiosidade, acusação, contraste) que o resto do vídeo paga?
4. **Melhor tomada**: o mesmo texto aparece em vários takes; fica a de energia
   maior e borda limpa.

Resultado: **um** gancho falado recomendado, mais um alternativo no máximo,
entrando na proposta do passo 5 em uma linha: *"abro com 'O mercado não está
saturado…' (que hoje está no segundo 30, puxo para a frente)"*.

**Cold open no EDL:** o range do gancho vai PRIMEIRO com `"beat": "HOOK"`, e
o mesmo trecho **sai da posição original**. Ouvir a frase duas vezes soa como
erro de edição. A exceção é o usuário pedir a repetição como callback. A
emenda gancho → começo real é a mais exposta do vídeo, então ela também passa
pelo portão e pelo `verify_cut.py`.

**Nada serve?** (todo candidato depende de contexto, tem gaguejo ou não aponta
para a tese.) Então o gancho fica a cargo do visual, com anatomia 6 e
`hook.lines` carregando a dívida. Diga isso em uma linha e ofereça um falado
para regravar, gerado pelo método abaixo. Ele leva menos de 3s para gravar e
entra como fonte nova.

## 4. Base de conhecimento

### As 6 anatomias (rotacione, nunca uma só)

| # | Anatomia | Estrutura | Exemplo | Quando | No AVE |
|---|---|---|---|---|---|
| 1 | **Clássica** | parada + dívida + recompensa | "Pare de buscar ideia. Transforme 1 tema em 30." | tutorial rápido | headline de banda sobre o rosto |
| 2 | **Identificação POV** | cena que só o avatar vive, sem promessa | "Você abre o bloco de notas, fica 20 min olhando e fecha." | furar bolha | falado no frame 0, headline curta ou nenhuma |
| 3 | **Loop aberto puro** | descobri X sobre Y, e não é o que você pensa | "Descobri por que seu Reels não retém, e não é o corte." | retenção alta | a recompensa fica no FIM do corte, nunca antes |
| 4 | **Contraste antes/depois** | estado deplorável específico → desejado específico | "De 3h editando pra 200 views, a 15 min pra 20k." | prova, autoridade | `contagem` ou tela dividida |
| 5 | **Erro invisível** | não é culpa sua por X, é por Y que você não vê | "Você não trava por falta de criatividade. Trava porque começa pelo tema." | vender tese/mecanismo | `aspas` ou headline com destaque na palavra Y |
| 6 | **Comando visual** | texto gigante + 1s de silêncio + ação | tela preta "SEU CONTEÚDO É CHATO" + papel rasgando | quebrar padrão | cartela TELA CHEIA cuja saída entrega o vídeo; ver "Som" |

### Dívida (A/B/C)
- **A:** como [resultado hiperespecífico] sem [objeção comum]
- **B:** por que você não [resultado] mesmo já sabendo [habilidade que tem]
- **C:** o que [grupo de elite] não te conta sobre [resultado]

### Gatilhos primários (escolha 1)
lacuna · erro fatal · contrarian · bastidor · prova específica (número ímpar ou
quebrado: 37, 1.243) · mecanismo com nome próprio (o do perfil) · dor com cena exata

### Vieses (combine 1 com o gatilho)
contradição/choque · segredo revelado · ameaça invisível · identificação POV ·
promessa ultraespecífica · desafio/provocação · humor ironicamente verdadeiro

### Estruturas
erro invisível · roubo de bastidor · quebra de senso comum · passo a passo
invertido · teste/provocação · cavalo de Troia (tema externo de alto interesse
que vira para o assunto nos 3 primeiros segundos, sem viés político)

### Pilares
promessa+tempo+resultado · erro fatal · antes e depois · lista objetiva ·
história pessoal · polêmico · pergunta retórica · segredo · autoridade ·
metáfora visual · urgência · curiosidade · inimigo comum · mito · atalho/mecanismo

### Substitutos para "em X segundos"
- **Esforço:** em 2 cliques · com 1 frase · sem abrir o ChatGPT
- **Sem dor:** sem aparecer · sem editar na mão · sem ideia nova
- **Especificidade:** com a mesma tese · usando só print · com 1 posicionamento

### Anti-padrões (invalidam o candidato)
"fala galera" · "3 dicas" · "você sabia" · formalidade · frase genérica que
serve para qualquer nicho · promessa que o corte não paga · travessão no texto.

## 5. O lote de headlines (`hook.lines`)

Gere **4 candidatos**, porque é o máximo que o `AskUserQuestion` mostra. O
"Other" deixa o usuário ditar o dele. O falado já foi decidido no garimpo; o
texto na tela **complementa o falado, não o repete**. Se a fala é POV, o texto
nomeia a dívida; se a fala é a tese, o texto é a acusação.

**Regra 3-2-1 adaptada ao lote de 4** (um candidato pode cumprir mais de uma):
- pelo menos **3 sem tempo** (nada de segundos, minutos, dias ou semanas; use os substitutos);
- pelo menos **1 POV ou pergunta direta**;
- **exatamente 1 de anatomia 6**: a cartela de tela cheia, com o falado entrando só depois dela.

**Diferenciação forçada:** no lote, nenhum par repete anatomia, gatilho, viés
ou frame zero. Dois candidatos que são o mesmo molde com palavras trocadas
invalidam um ao outro. **Entre vídeos:** não repita a anatomia dos 2 últimos
do `historico`, salvo se o usuário escolher repetir.

**Forma:** no máximo **6 palavras no total**, em CAIXA ALTA (exceto no estilo
`outline`, que é sentence-case). Use `/` para quebrar onde o sentido pede. Uma
palavra de destaque vai para o accent nos estilos que pintam (`realce`,
`misto`, `grifo`, `tarjas`). Marque qual é.

**Como perguntar:** cada opção do `AskUserQuestion` tem o TEXTO como `label` e
o cartão completo no `preview`. O chat continua curto (Principle 10), e o
detalhe fica onde o usuário compara:

```
HOOK 2 · ERRO INVISÍVEL · anatomia 5
gatilho contrarian + viés ameaça invisível · pilar mito · emoção alívio+culpa
tempo: não · objetivo: alcance

TELA:      O PROBLEMA NÃO É / O ALGORITMO   (destaque: ALGORITMO)
FALADO:    "O mercado não está saturado…" (cold open, 0:30)
FRAME 0:   aspas, tela cheia, sai com cortina
SOM:       riser resolvendo na saída da cartela + impact
CTA:       "Concorda? Comenta" (debate)
POR QUÊ:   alivia a culpa e acusa um inimigo comum; difere do #1 (POV)
```

Depois da escolha, uma prévia de design (um still), como já manda o
shortform.md, e grave a escolha no `historico` do perfil.

## 6. Frame zero (0–0,8s): nunca rosto parado

| Frame zero do método | Recurso do AVE |
|---|---|
| tela preta com texto gigante | cartela tela cheia: `knockout` · `poster` · `capa` · `aspas` (citação) · `contagem` (número) · `ficha` |
| você já em movimento | primeiro segmento começando no meio de um gesto (borda de corte no movimento, não no repouso) + `zoomCuts` forte no frame 0 |
| gravação de tela | insert de tela cheia no frame 0, se a fonte existir |
| jogando objeto / metáfora visual literal | insert Pexels ou `brollGraphics` sob medida nos primeiros 0,8s |
| texto sobre o rosto | headline de banda (`card` · `outline` · `realce` · `tarjas` · `alerta` · `placar` · `terminal` …) |

O que estiver disponível no material vence o que exigiria busca. Rotacione
entre vídeos pelo `historico`.

## 7. Som do gancho e trilha: decididos junto com o gancho

**Riser:** a regra de `shortform.md` → "Riser no gancho" continua valendo. Ela
consulta `preferencias.json → regras.shortform.hook_riser`. O que o gancho
decide é **onde fica a virada**:

| Anatomia | Virada do riser | Mais (deixas em `edit-data.json → sfxCues`) |
|---|---|---|
| 6 (comando visual) | **saída da cartela** | 1s de silêncio de voz sob a cartela; `sfxCues` `kind: "impact"` na virada |
| 3 (loop aberto) | fim da frase do gancho | nenhum impacto: a dívida tem de ficar soando |
| 4 (contraste) | o "para" do contraste | `kind: "hook"` (whoosh) na troca |
| 1, 2, 5 | primeiro corte dentro do gancho | — |

**Trilha (Fase 3):** o prompt do Treblo sai do objetivo e da emoção do gancho
escolhido, não só do tema. Ainda vale a regra de pedir *música* (gênero,
instrumentos, BPM e clima) e não textura:

| Objetivo / funil | Direção da trilha |
|---|---|
| Vendas / venda | cinematic pop pulsante, 100–115 BPM, build constante, sem drop antes do CTA |
| Alcance / autoridade | eletrônica moderna confiante, baixo marcado, 110–124 BPM |
| Engajamento / conexão | piano ou violão quentes, lo-fi suave, 80–95 BPM |
| Salvamento / educar | lo-fi keys limpo, batida leve, 85–100 BPM, sem melodia competindo com a fala |

Anatomia 6 pede a trilha **entrando na virada**, não no frame 0: o silêncio
da cartela é parte do gancho. Proponha a trilha em uma linha junto com o
gancho e mande gerar só na Fase 3, depois do acervo (`biblioteca.py
--resolver --tipo trilha`).

## 8. CTA por objetivo

| Objetivo | CTA |
|---|---|
| Vendas | convite VIP com palavra-chave: "Comenta {cta_palavra}" |
| Alcance | compartilhar ou debater: "Manda pra quem precisa ouvir isso" |
| Engajamento | opinião ou teste nos comentários |
| Salvamento | "Salva pra usar quando for gravar" |

O CTA entra no fim do corte (fala ou texto). Se a fala não tem CTA, ele vai
como texto na tela nos últimos ~2s.

## 9. Retenção: conferência do corte, não roteiro

Antes do portão da Fase 1, cheque três coisas:
- **o loop aberto pelo gancho só fecha perto do fim.** Se a recompensa vem no
  segundo 8, o resto do vídeo é bônus que ninguém espera. Reordene ou apare;
- **frases que terminam em "mas", "só que", "olha"** são micro-loops; não
  corte depois delas sem a continuação;
- **cadência visual de ~1,5s** na primeira metade, vinda da emenda, do
  `zoomCuts` ou de um insert. O ritmo do zoom continua sendo o da FALA
  (shortform.md).

## 10. Modo avaliador: "avalie esse gancho"

Quando o usuário mandar um gancho (texto ou um trecho do corte), devolva em
poucas linhas:

```
Nota 7/10 · anatomia 5 · dívida B + viés ameaça invisível
Parada: forte · Recompensa: substituto de esforço · Estrutura: erro invisível
CTA alinhado: sim · Diferencia dos últimos vídeos: não (repete a anatomia 5)
Intensidade: média · Risco de scroll: médio
Melhoraria: troca "estratégia" por uma cena que ele vive, tipo "seu post de ontem".
```

Para um trecho do corte, rode também o `hook_finder.py --fonte` e cite os
números (borda, energia), que são o que o texto não mostra.
