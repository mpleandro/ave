# Fontes empacotadas

O catálogo de headline resolve as famílias pelo cache do HyperFrames, que as
baixa do Google Fonts sob demanda. **Nem toda família do catálogo do Google é
servida por esse caminho** — a Bebas Neue não é, e o sintoma era um
`FileNotFoundError` no meio da composição, depois de o usuário já ter escolhido
a fonte na tela e visto a prévia funcionar (o navegador a carrega direto do
Google; só a MEDIÇÃO, que é local, falha).

O que estiver aqui é usado como reserva pela medição (`text_measure.font_files`)
e ganha um `@font-face` na composição, então o render não depende de a fonte
estar instalada na máquina de quem renderiza.

Nome do arquivo: `<slug-da-familia>-<peso>-<estilo>.ttf`, o mesmo padrão do
cache — é o que deixa a reserva ser encontrada sem uma tabela à parte.

Esta pasta viaja junto com as folhas de estilo para dentro do projeto
(`phase2.py` copia `assets/styles/` inteiro), então o caminho no HTML é
`styles/fonts/<arquivo>`.

| arquivo | família | licença |
|---|---|---|
| `bebas-neue-400-normal.ttf` | Bebas Neue | SIL Open Font License 1.1 |
