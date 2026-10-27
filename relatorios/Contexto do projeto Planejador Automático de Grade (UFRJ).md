# Contexto do projeto: Planejador Automático de Grade (UFRJ)

*Documento para retomar o projeto em um novo chat · atualizado em 15/10/2026*

## 1. Resumo do projeto

- **Disciplina:** Computação em Nuvem (curso AWS Cloud Foundations). O trabalho final é um projeto real, com tempo curto.
- **Tema escolhido:** planejador automático de grade. O aluno envia o BOA (Boletim de Orientação Acadêmica, PDF oficial da UFRJ) e o sistema monta a grade do próximo período, usando o currículo do curso (dado estático) e a planilha de ofertas divulgada a cada período.
- **Curso e currículo de referência:** 85783 Ciência da Computação, versão curricular 2022/2.
- **Estratégia:** implementar localmente para a apresentação, com interface em Streamlit, mas já desenhado para migrar para a AWS. Como a matéria é de nuvem, a nota provavelmente depende de mostrar serviços AWS funcionando, então a nuvem não deve ficar como "se der tempo".

## 2. Como conduzir o trabalho com o aluno (Davi)

- Responder em português do Brasil.
- Conceito antes do código; instruções passo a passo; assumir zero conhecimento prévio quando for tutoria.
- Código com nomes descritivos e comentado.
- **Neste projeto**, o aluno pediu que o assistente analise a viabilidade e gere os arquivos (ele não vai escrever o código por enquanto).
- Antes de gerar algo grande, alinhar as decisões e confirmar com ele.

## 3. Arquitetura geral

O trabalho se divide em **extratores** (leem arquivos brutos e salvam dados limpos), o **motor** (só consome dados limpos) e a **interface**.

1. Extrator do currículo (feito, validado pelo aluno).
2. Extrator da planilha de ofertas (feito, em script reutilizável).
3. Extrator do BOA (feito, versão beta).
4. Motor de geração da grade (feito, versão beta).
5. Interface em Streamlit (protótipo visual feito; falta integrar os módulos).
6. Versão AWS, diagrama, estimativa de custos e relatório (a fazer).

### Decisões já tomadas

- **"Cursando" no BOA = não cumprida, por padrão.** Depois, o usuário poderá indicar quais matérias "Cursando" contam como cumpridas (todas ou só algumas). Ao marcar, o motor recalcula a elegibilidade com o grafo de pré-requisitos.
- **Prioridade da grade:** períodos mais baixos primeiro e matérias que são pré-requisito de outras (quantas matérias cada uma destrava). Listar alternativas de grade é uma implementação futura plausível.
- **O motor confia no status do BOA** (Facultada/Vedada) e não recalcula equivalências, porque o BOA já as resolveu. Os pré-requisitos servem para a pontuação e para recalcular quando o usuário marca "Cursando" como cumprida.
- **Turmas de código antigo** existem na planilha por causa da atualização do currículo; o foco são alunos do currículo atual.
- **Armazenamento:** currículo em JSON versionado por curso e versão (`85783_2022-2.json`); ofertas em um JSON por período; o BOA é dado pessoal e temporário (sem nome nem matrícula salvos).

### Propostas ainda não confirmadas

- **Limite de créditos por período:** padrão de 24, ajustável pelo usuário (já é um parâmetro do motor).
- **Pesos da pontuação:** obrigatória vale 1000 mais um bônus por período baixo e por matérias que ela destrava; há três perfis de prioridade (períodos, equilibrado e pré-requisitos), com "equilibrado" como padrão. Ainda não foi testado com alunos de períodos iniciais.
- **Optativas só até o que ainda falta cumprir**, com folga de 3 créditos para fechar matérias inteiras. Por isso as grades de exemplo têm 12 a 16 créditos, e não 24. Precisa de confirmação do aluno.
- **Alvo na AWS:** S3 (site, uploads e JSONs), Lambda (extração e motor), API Gateway, DynamoDB com TTL para escolhas e resultados temporários. Bucket privado e BOA apagado após o processamento, o que dá argumentos de segurança, LGPD e modelo de responsabilidade compartilhada para o relatório. O curso também costuma pedir diagrama de arquitetura e estimativa de custos (AWS Pricing Calculator).

## 4. As três entradas de dados

### 4.1 BOA (PDF do aluno)

- PDF oficial com **texto selecionável** (não precisa de OCR nem de Textract). Cerca de 8 páginas, com cabeçalho repetido em cada uma.
- **Layout em duas colunas:** à esquerda, o elenco recomendado do currículo (código canônico, nome, créditos, carga horária e período); à direita, as atividades aprovadas (ou equivalentes) com o grau. **A última coluna traz o status das não cumpridas:** "Inscrição Facultada", "Inscrição Vedada" ou "Cursando". Quando a matéria foi cumprida, o status fica vazio.
- **Seções:** Obrigatórias; Optativas; Optativas de Escolha Restrita (grupo Humanidades); Cursadas e Não Explicitadas (livre escolha); Observações finais e Resumo; Relatório de Extensão.
- **Regras de leitura validadas:**
  - a matéria é identificada pelo código da coluna esquerda;
  - pendente = linha que termina com um dos três status;
  - cumprida = linha da coluna esquerda que termina com o grau;
  - uma matéria pode ocupar duas linhas (duas equivalências aprovadas);
  - o BOA contém nome e matrícula, que não devem ser salvos.
- **Validações já feitas:** a soma das obrigatórias do currículo (139 créditos, 2540 h) é igual ao total do BOA. Prevendo Facultada/Vedada só pelos pré-requisitos, 106 de 107 casos coincidem com o BOA; a exceção é ICP038, provavelmente por uma equivalência que o sistema da universidade não aplicou. Isso confirma que *Vedada* significa pré-requisito não cumprido.
- **Status:** extrator\_boa.py pronto (versão beta). Lê as palavras do PDF com sua posição (pdfplumber) e gera um JSON com curso, versão curricular, data de emissão, cumpridas (com a equivalência que as cumpriu), pendentes com status, livre escolha e o Resumo do BOA. Não extrai nome, matrícula nem notas. Os créditos lidos batem com a tabela Resumo do próprio BOA, e a leitura foi testada em um único BOA.

### 4.2 Currículo 2022/2 (dado estático)

- **Fonte oficial:** página do SIGA da UFRJ para Ciência da Computação 2022/2 a 9999/9 (https://siga.ufrj.br/sira/repositorio-curriculo/distribuicoes/402FED54-92A4-F79C-3ACF-54A4EA89ED35.html).
- **Arquivo:** `curriculo_85783_2022-2.json` (validado pelo aluno).
- **Estrutura:** `_meta`; `estrutura_por_periodo`; `totais_para_integralizacao_fonte`; `disciplinas` (150 no total: 38 obrigatórias, 83 optativas de escolha condicionada e 29 do grupo Humanidades, cada uma com nome, tipo, período, créditos, carga horária, horas teórica/prática/extensão e lista de `requisitos`); `equivalencias` (71 equações em que um lado pode ter 2 códigos que valem em conjunto); `alias_codigo` (93 códigos antigos ou de outras unidades que equivalem 1 para 1 a um código do currículo); `equivalencias_extras_de_requisito`.
- **Pegadinhas:**
  - alguns requisitos apontam para códigos fora do currículo: MAE121 e MAC128 resolvem para MAE992, MAC118 resolve para MAE111 e ICP231 resolve por equivalência (inclui ICP238 + ICP248);
  - os nomes seguem a grafia da fonte, inclusive "Teconologia" em ICP081 a ICP085, para casar com o BOA;
  - equivalências podem ser de 2 para 1 (por exemplo, CMT012 + ICP121 valendo ICP131), então um simples mapa código a código não basta.

### 4.3 Planilha de ofertas (varia a cada período)

- **Arquivo do período 2026-2:** "Planejado-2026-2 - Visualização" (duas versões .xlsx idênticas e os CSVs das abas Turmas e Grades). Usar só a aba **Turmas**. A planilha traz o aviso de que as informações são provisórias.
- **Organização:** cada turma é um bloco de linhas que começa onde **Disciplina e Docente** estão preenchidos. Há duas listas independentes lado a lado: TURMA (cursos com vagas, "Abrir?", número no SIGA, restrição) e AULAS (dia, horário, tipo, sala, lotação).
- **Ponto crítico:** uma linha com Disciplina preenchida e **sem Docente** é a mesma turma listada sob outro código (código antigo ou disciplina da pós-graduação), e os encontros ficam espalhados entre essas linhas. Exemplos: Segurança da Informação (ICP473) tem quarta no ICP473 e sexta no ICP719, somando 4 h; Redes I (ICP362) tem quarta e sexta, das 10h às 12h, esta última listada sob ICP510.
- **Significados:** coluna "Horas" = horas de aula por semana (às vezes inconsistente); "Abrir?" SIM = turma confirmada, N/A = turma de outra unidade (ex.: MAE111, MAE992, MAD243), vazio = pendente; tipo de oferta "N T#" = período recomendado e número da turma, além de Elet, SVÇ, PPGI, ProfComp e Out; BCC1/BCC2 são as vagas do curso.
- **Resultado para 2026-2:** 108 turmas reais; 57 abertas a BCC (54 confirmadas e 3 externas). ICP101 (código antigo equivalente a ICP359) é a única oferta de Introdução ao Suporte à Decisão. ICPZ55 (extensão) não tem horário fixo. Restam 2 avisos de horas (ICP115, turma 2, e ICP082), que são erros da coluna Horas e não dos horários.

## 5. Arquivos produzidos

- `curriculo_85783_2022-2.json`: currículo validado.
- `extrator_ofertas.py`: script reutilizável a cada período. Uso: `python extrator_ofertas.py planilha.xlsx --curriculo curriculo_85783_2022-2.json`. Aceita .xlsx ou .csv; opções `--periodo`, `--curso` (padrão BCC), `--todas`, `--saida` e `--aba`. Valida o layout da planilha e para com mensagem clara se ele mudar. Só usa a biblioteca padrão, mais `openpyxl` para ler .xlsx.
- `ofertas_2026-2.json`: saída do extrator, com `_meta`, `turmas` e `avisos`. Cada turma tem: `id`, `codigo`, `nome`, `codigos_cruzados`, `docentes`, `tipo_de_oferta`, `categoria`, `periodo_recomendado`, `numero_da_turma`, `horas_semanais`, `numeros_siga`, `abrir`, `situacao` (confirmada, externa, pendente ou cancelada), `restrita_aos_cursos`, `vagas_por_curso`, `aulas` (dia, `inicio_min` e `fim_min` em minutos, tipo, sala, `listada_em`), `horario_completo` e `codigo_no_curriculo`.
- `extrator_boa.py` e `boa_extraido.json`: leitura do BOA em PDF, em Python puro (`pdfplumber`). Uso: `python extrator_boa.py boa.pdf --curriculo curriculo_85783_2022-2.json`; como função, `extrair_boa(arquivo)`. A saída tem `curso`, `versao_curricular`, `emitido_em`, `cumpridas` (com `cursada_como`), `pendentes` (código, nome, seção, período, créditos, status), `livre_escolha_cursadas`, `resumo`, `conferencias` e `avisos`.
- `motor_grade.py`, `grade_padrao.json` e `grade_redes_cumprida.json`: o motor e dois resultados de exemplo. Uso: `python motor_grade.py --boa boa_extraido.json --curriculo curriculo_85783_2022-2.json --ofertas ofertas_2026-2.json --limite 24`. Opções: `--cursando-cumpridas ICP362` (ou `todas`), `--sem-optativas`, `--prioridade periodos|equilibrado|prerequisitos` e `--credito-extra-optativas`. Como função, `gerar_grade(...)`.
- `prototipo_streamlit.py` e as cinco imagens `prototipo_1_envio_do_boa.png` a `prototipo_5_resultado_com_conflito.png`.
- Em um novo chat, estes arquivos precisam ser anexados de novo, junto com um BOA anonimizado (sem nome e matrícula) para testes.

## 6. Regras do motor (versão beta pronta)

1. **Entradas:** `boa_extraido.json`, currículo, ofertas e parâmetros (limite de créditos, quais "Cursando" contam como cumpridas, incluir optativas, prioridade).
2. **Candidatas:** matérias pendentes liberadas (Facultada ou Cursando) com turma `confirmada` ou `externa`, com `horario_completo` verdadeiro, identificadas por `codigo_no_curriculo`. As *Vedada* ficam de fora, a menos que a marcação do usuário complete seus pré-requisitos; fora isso, vale sempre o status do BOA.
3. **Restrições:** uma turma por matéria; nenhum choque de horário (dois encontros colidem se estão no mesmo dia e `inicio_a < fim_b` e `inicio_b < fim_a`; encostar não colide); limite de créditos.
4. **Pontuação:** obrigatória = 1000 + peso do período × (10 − período) + peso de "destrava" × número de matérias pendentes que dependem dela, direta ou em cadeia; optativa = 100 + peso de "destrava" × destrava + créditos. Pesos (período, destrava): períodos (20, 5), equilibrado (10, 10), pré-requisitos (5, 20).
5. **Optativas:** entram só até o que falta cumprir (créditos do Resumo do BOA menos os das matérias marcadas), mais uma folga de 3 créditos.
6. **Busca:** exata, por ramificação e poda (acha a melhor combinação, e não uma aproximação).
7. **O que o usuário vê além da grade:** as matérias que ficaram de fora, cada uma com o motivo (choque de horário com qual matéria, em quais dias e horários; limite de créditos; optativas já cobrindo o necessário; bloqueada por pré-requisito pendente), as atividades sem horário fixo (ICPZ55, ICPX06) e avisos (por exemplo, Humanidades sem turma ofertada).

**Resultados com dados reais (2026-2):**

- **Nada marcado:** Redes I (ICP362), ICP005 e ICP016, somando 12 créditos. Metodologia da Pesquisa (ICP472) fica de fora por choque com Redes I na quarta e na sexta, das 10h às 12h.
- **Redes I marcada como cumprida:** ICP472, Segurança da Informação (ICP473, liberada pela marcação), ICP005 e ICP016, somando 16 créditos. O TCC (ICPK01) continua bloqueado por falta de Metodologia.
- **Humanidades:** faltam 4 créditos e nenhuma turma é ofertada neste período.
- **Testes:** em 600 casos aleatórios, a busca deu o mesmo resultado que uma força bruta que testa todas as combinações. As grades geradas não têm choque, matéria repetida nem excesso de créditos, e o resultado é o mesmo em execuções repetidas.

## 7. Interface em Streamlit (telas planejadas)

1. **Upload e período:** enviar o BOA e escolher o período das ofertas.
2. **Conferência:** resumo do que foi lido (curso, versão, cumpridas e pendentes) e lista das matérias "Cursando" com uma caixa "conta como cumprida" em cada uma.
3. **Parâmetros:** limite de créditos, incluir ou não optativas e prioridades.
4. **Resultado:** grade semanal (dias x horários), lista de turmas escolhidas (docente e sala), créditos totais, conflitos e avisos, com exportação.

Protótipos: cinco imagens (`prototipo_1_envio_do_boa.png` a `prototipo_5_resultado_com_conflito.png`) tiradas de um app Streamlit real (`prototipo_streamlit.py`, aberto com `?tela=1` até `?tela=5`) e alimentadas com as saídas reais do motor.

## 8. Próximos passos

1. Integrar os módulos no app Streamlit local: upload do BOA, extrator, conferência com as caixas "Cursando", motor e grade, usando o protótipo visual como base.
2. Testar com BOAs anonimizados de perfis diferentes (principalmente alunos de períodos iniciais) para validar a leitura do BOA e os pesos da prioridade.
3. Deixar o usuário escolher as optativas (hoje o desempate entre optativas equivalentes é pela ordem do código) e, depois, mostrar alternativas de grade.
4. Versão AWS (Lambda, S3, API Gateway, DynamoDB com TTL), diagrama, estimativa de custos, segurança e relatório.

## 9. Pontos em aberto

- Confirmar a regra de optativas só até o que falta (com folga de 3 créditos), em vez de preencher o limite de créditos.
- Limite de créditos padrão (24) e como o usuário o altera.
- Pesos da pontuação: as três prioridades deram a mesma grade para o BOA de teste, então falta testar com outros perfis.
- Humanidades: faltam 4 créditos e nenhuma turma é ofertada em 2026-2; definir como a interface mostra isso.
- Horários possivelmente incompletos na planilha provisória e escopo mínimo da migração para a AWS dentro do prazo.

## 10. Como retomar em um novo chat

Anexe este documento, os arquivos da seção 5 e, se possível, um BOA anonimizado. Peça: "continuar do passo 1 dos próximos passos: integrar os módulos no app Streamlit".
