HIGIENIZADOR 1.9.14.6.7 — TESTE DE COMUNICAÇÃO (EXPERIMENTAL)

BASE: Interface 0.14, adaptador read-only com seletores de pesquisa e identidade do MGC1.0.6.7.
NÃO É AUTOMATIZAÇÃO DE CADASTROS. NÃO PREENCHE NEM SALVA.

1. Execute INSTALAR.bat (somente primeira execução). Execute INICIAR.bat.
2. Selecione UBS, escolha CSV, clique Iniciar ambiente e faça login no PEC.
3. Menu Teste MGC > Identificar página PEC para diagnóstico sem alteração.
4. Menu Teste MGC > Pesquisar e abrir cidadão; selecione um cidadão do CSV.
5. O adaptador abre a listagem, pesquisa, verifica um único resultado por CPF/CNS, abre a edição e confere CPF/CNS. Não toca nos campos.
6. Confira as mensagens no log; envie as mensagens sem dados pessoais completos.

Se um seletor não for identificado de forma única, o teste interrompe sem atualizar cadastro.
Os indicadores não representam cadastros processados e os botões de lote continuam desativados.
O navegador permanece integrado com a cobertura que evita a piscada.
Os motores estáveis originais não estão incluídos como executáveis nem foram modificados.
Não use esta versão para executar lotes.
