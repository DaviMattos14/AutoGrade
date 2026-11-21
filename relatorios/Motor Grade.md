# Motor Grade

## 1. Objetivo

O Motor Grade transforma três fontes de dados em uma combinação de matérias e turmas adequada para o próximo período:

1. O BOA, com a situação acadêmica do estudante;
2. o currículo vigente do curso, com disciplinas, créditos, períodos e pré-requisitos;
3. a planilha de ofertas, com turmas, docentes e horários.

A implementação principal está em `motor_grade.py`, principalmente na função `gerar_grade()`. A interface Streamlit em `app.py` coleta os parâmetros do usuário e entrega os dados ao motor. O objetivo do algoritmo não é simplesmente preencher o maior número possível de disciplinas. Ele busca a combinação válida com a maior pontuação conforme a prioridade escolhida pelo usuário.

## 2. Entradas do motor

A função `gerar_grade()` recebe os seguintes dados:

| Parâmetro | Função |
| --- | --- |
| `dados_do_boa` | Lista de matérias cumpridas e pendentes, situação no BOA e resumo curricular |
| `curriculo` | Disciplinas, créditos, períodos, pré-requisitos e áreas de interesse |
| `ofertas` | Turmas disponíveis, situação da turma e aulas |
| `limite_de_creditos` | Quantidade máxima de créditos na grade |
| `cursando_como_cumpridas` | Lista de matérias que estão em curso e o usuário deseja considerar concluídas |
| `incluir_optativas` | Controla a inclusão de optativas condicionadas e humanidades |
| `prioridade` | Estratégia de pontuação: `periodos`, `equilibrado` ou `prerequisitos` |
| `credito_extra_de_optativas` | Folga adicional ao orçamento de créditos de optativas |
| `area_de_interesse` | Área que recebe bônus ao escolher optativas condicionadas |

Antes de calcular a grade, o motor verifica se o BOA pertence ao mesmo curso e à mesma versão curricular carregada no currículo. Uma incompatibilidade gera `ErroDoMotor`.

## 3. Processamento do BOA

Para cada matéria pendente, o BOA fornece pelo menos:

- código;
- nome;
- categoria ou seção curricular;
- período;
- créditos;
- situação atual.

As situações relevantes são:

- `Facultada`: a matéria está liberada.
- `Cursando`: a matéria não é considerada cumprida por padrão.
- `Vedada`: os pré-requisitos ainda impedem a matrícula.

O motor sempre parte das matérias já cumpridas informadas pelo BOA. As matérias marcadas pelo usuário como `Cursando` podem ser adicionadas ao conjunto de matérias feitas, mas continuam presentes na relação de pendências se não forem retiradas da grade.

Uma matéria marcada como cumprida é removida da lista de pendentes e passa a valer como pré-requisito concluído. Essa alteração pode liberar matérias que estavam `Vedada`.

## 4. Pré-requisitos e equivalências

O motor não compara os pré-requisitos somente pelo texto exibido no BOA. Ele utiliza os dados estruturados do currículo e conhece dois mecanismos de equivalência:

- **Alias de código**: um pré-requisito pode ser representado por um código equivalente.
- **Equivalências extras**: um requisito pode ser satisfeito por uma combinação alternativa de matérias.

A função `requisito_satisfeito()` considera o requisito completo quando:

- o código consta diretamente nas matérias feitas;
- um código equivalente consta nas matérias feitas;
- uma das combinações alternativas do currículo consta integralmente nas matérias feitas.

Uma matéria `Vedada` continua bloqueada quando ainda falta pelo menos um dos seus pré-requisitos. Ela é liberada somente após todas as condições serem satisfeitas pelas matérias originais mais as marcações feitas pelo usuário.

## 5. Marcação de matérias em curso

Na etapa de conferência, o usuário pode indicar quais matérias `Cursando` deseja considerar como concluídas.

Antes da seleção, o motor calcula quais outras matérias podem ser liberadas por cada marcação. Esse efeito considera:

- a matéria já constava como cumprida antes da marcação;
- o usuário marcou uma matéria válida que realmente estava como `Cursando`;
- algum requisito passa a estar completo;
- a matéria liberada possui turma disponível no período.

Ao gerar a grade, todas as marcações válidas são aplicadas ao conjunto de matérias feitas. Marcações para matérias que não estão como `Cursando` são ignoradas e registradas como aviso.

## 6. Elegibilidade das disciplinas

Depois de resolver os pré-requisitos, o motor separa as matérias pendentes em elegíveis e bloqueadas.

Uma matéria elegível pode ser candidata à grade quando:

- está como `Facultada`;
- está como `Cursando` e não foi marcada como cumprida;
- estava `Vedada`, mas foi liberada pelas matérias marcadas;
- pertence ao currículo carregado;
- possui pelo menos uma turma utilizável.

Uma matéria que não possui turma confirmada com horário completo não entra na busca. Materias liberadas sem turma podem aparecer separadamente na explicação do resultado.

## 7. Critérios para considerar uma turma

A planilha é filtrada antes da busca. Uma turma pode ser utilizada somente quando:

- possui código associado ao currículo;
- a situação é `confirmada` ou `externa`;
- o horário está marcado como completo.

Turmas de uma outra unidade podem ser consideradas externas. Se a planilha informa aulas que não somam todas as horas esperadas, o motor registra um alerta sem retirar a turma automaticamente da busca.

## 8. Pontuação das matérias

Cada matéria elegível recebe uma pontuação antes da busca combinatória.

### Obrigatórias

A pontuação começa em `1000` pontos. São aplicados os seguintes bônus:

- bônus pelo período: quanto menor o período curricular, maior o bônus;
- bônus por desbloquear outras matérias pendentes.

A fórmula é baseada em:

```text
1000
+ peso_do_período × (período máximo - período da matéria)
+ peso_do_pré-requisito × quantidade de matérias que a matéria destrava
```

### Optativas

As optativas começam em `100` pontos. Elas recebem:

- bônus pelo número de créditos da matéria;
- bônus por desbloquear outras matérias pendentes;
- bônus de `100` pontos quando estão na área de interesse escolhida.

Ainda assim, uma optativa nunca supera uma disciplina obrigatória em pontuação base.

## 9. Modos de prioridade

O parâmetro de prioridade controla os pesos dos componentes da pontuação:

| Modo | Peso do período | Peso por destravar pré-requisitos |
| --- | ---: | ---: |
| `periodos` | 20 | 5 |
| `equilibrado` | 10 | 10 |
| `prerequisitos` | 5 | 20 |

O modo `periodos` favorece disciplinas curriculares iniciais. O modo `prerequisitos` favorece matérias que desbloqueiam o maior número possível de dependentes, inclusive em cadeia. O modo `equilibrado` distribui igualmente os dois pesos.

Além disso, a área de interesse aumenta em 100 pontos optativas condicionadas pertencentes à área selecionada.

## 10. Desbloqueio de matérias

O motor calcula quantas matérias pendentes cada disciplina pode destravar.

O cálculo começa em uma matéria e percorre as dependências:

1. encontra as matérias que têm essa disciplina como pré-requisito;
2. adiciona essas matérias ao conjunto de dependentes;
3. repete o processo pelos dependentes encontrados;
4. conta quantas matérias pendentes diferentes foram alcançadas.

Esse valor cria um incentivo para escolher disciplinas que possibilitam o progresso acadêmico mais amplo.

## 11. Limite de créditos

O resultado não pode ultrapassar o limite de créditos informado pelo usuário.

Durante a busca, o total de créditos é acumulado. Quando uma matéria faria o total exceder o limite, essa escolha é descartada.

Na edição manual da grade, o usuário pode ultrapassar esse limite deliberadamente. Nesse caso, a interface exibe um aviso, mas não impede a escolha.

## 12. Orçamento de optativas

As optativas não são somadas indiscriminadamente ao limite geral.

Para cada categoria de optativa, o motor obtém no resumo do BOA quantos créditos ainda faltam. Também considera optativas marcadas pelo usuário como cumpridas.

O orçamento usado na busca é:

```text
créditos que faltam
- créditos de optativas já marcadas como cumpridas
+ folga configurada
```

A folga é aplicada somente quando ainda existe crédito de optativa a cumprir. Ela permite que uma matéria inteira seja considerada mesmo quando o último crédito não completa exatamente o saldo do BOA.

Se a inclusão de optativas estiver desativada, o orçamento dessas categorias é definido como zero.

O motor trata separadamente:

- optativas condicionadas;
- optativas restritas a humanidades.

## 13. Detecção de choque de horários

Cada turma possui uma ou mais aulas, representadas por:

- dia da semana;
- minuto inicial;
- minuto final.

Duas aulas colidem quando:

- o dia é o mesmo;
- o intervalo inicial termina depois do início da outra aula;
- o intervalo final inicia antes do término da outra aula.

A função considera intervalos fechados logicamente, mas permite que uma aula termine exatamente no início da outra:

```text
10:00–12:00 e 12:00–14:00 não possuem choque
10:00–12:30 e 12:00–14:00 possuem choque
```

Ao buscar uma combinação, o algoritmo mantém uma estrutura com todas as aulas já escolhidas e rejeita qualquer turma cujo horário sobreponha uma delas.

## 14. Busca combinatória

O núcleo da busca está em `buscar_melhor_combinacao()`. Ele não faz uma escolha gulosa, ou seja, não apenas aceita a matéria com maior pontuação e prossegue. Em vez disso, ele explora combinações completas.

Para cada matéria candidata, o algoritmo decide entre:

- testar cada turma da matéria;
- não incluir a matéria nesta versão da grade.

Cada ramo da busca acumula:

- pontuação;
- créditos;
- aulas ocupadas;
- créditos por categoria;
- pares de matéria e turma escolhidos.

Uma combinação só pode atualizar a melhor solução quando respeita simultaneamente:

- limite de créditos;
- orçamento por categoria;
- ausência de choque;
- diferença mínima exigida das versões anteriores.

### Poda da busca

A busca usa uma estimativa de limite superior para reduzir o número de combinações examinadas.

Essa estimativa considera o melhor caso teórico, ignorando choques e orçamentos. O ramo é descartado quando o limite superior não consegue superar a melhor grade já encontrada.

A busca possui um limite de segurança de dois milhões de nós. Quando esse limite é atingido, o resultado contém a melhor combinação encontrada até o momento, mas o campo `busca_completa` indica que a busca foi interrompida.

## 15. Geração das três versões

A função `gerar_versoes_da_grade()` solicita até três soluções ao motor.

- a versão 1 é a melhor solução encontrada;
- a versão 2 deve diferir da versão 1 em pelo menos duas matérias;
- a versão 3 deve diferir da versão 1 e da versão 2 em pelo menos duas matérias.

Internamente, o conjunto de códigos da grade anterior é enviado ao motor como conjunto a evitar. A condição de diferença usa a diferença simétrica entre os conjuntos:

```text
quantidade de matérias que existem em apenas uma das duas grades
```

Além disso, a alternativa deve possuir pelo menos uma matéria nova em relação à grade anterior. Isso impede que uma grade seja considerada alternativa apenas por incluir menos matérias.

Se não existir uma terceira alternativa suficientemente diferente, o motor devolve menos versões.

## 16. Construção do resultado

Após encontrar a melhor combinação, o motor reconstrói os dados completos de cada item da grade.

Cada matéria inclui:

- código e nome;
- categoria curricular;
- créditos e período;
- turma escolhida;
- docentes;
- situação da turma;
- lista de aulas;
- motivo da pontuação;
- indicação de matéria em curso;
- alertas da planilha.

As matérias são ordenadas para apresentação com obrigatórias primeiro e, depois, pelo período e código.

O resultado também contém:

- créditos totais;
- pontuação;
- período das ofertas;
- parâmetros utilizados;
- orçamento de optativas;
- estatísticas da busca;
- avisos;
- matérias que ficaram de fora.

## 17. Explicação das matérias excluídas

Para cada matéria candidata que não entrou na grade, o motor tenta explicar o motivo.

A prioridade da explicação é:

1. todas as turmas têm choque com a grade;
2. a matéria faria a grade exceder o limite de créditos;
3. os créditos de optativas já atenderiam a necessidade calculada;
4. a matéria pertence a uma combinação diferente exigida pelas versões alternativas;
5. a pontuação da matéria é menor que a das selecionadas.

Também são registradas separadamente:

- matérias vedadas por pré-requisitos;
- matérias liberadas sem turma ofertada;
- períodos sem oferta disponível de optativas.

Essas explicações não alteram a grade. Elas ajudam o usuário a entender por que uma disciplina não foi incluída.

## 18. Busca manual na interface

Depois da geração automática, o usuário pode editar a grade na aba `Editar grade`.

Essa edição utiliza `listar_materias_disponiveis()`, que aplica as mesmas regras de elegibilidade do motor, mas não impõe limite de créditos nem orçamento de optativas.

A função oferece quatro grupos:

- `disponiveis`: matérias liberadas com turma utilizável;
- `bloqueadas`: matérias vedadas por pré-requisito;
- `sem_turma`: matérias liberadas sem turma confirmada;
- `cumpridas`: conjunto final de matérias consideradas cumpridas.

Para cada turma disponível, a interface informa se ela colide com a grade atual. Ao trocar uma turma da mesma matéria, a turma anterior não é considerada choque.

Depois que o usuário modifica a seleção:

- a pontuação da sugestão automática deixa de representar a grade editada;
- os créditos são recalculados;
- a lista de matérias excluídas deixa de ser exibida como resultado automático;
- o usuário pode restaurar a versão sugerida pelo motor.

A função `montar_grade_da_selecao()` transforma o mapa escolhido pelo usuário em itens no mesmo formato da resposta do motor.

## 19. Uso pela linha de comando

Além da interface, o motor pode ser executado diretamente:

```bash
python motor_grade.py \
  --boa caminho/do/boa.json \
  --curriculo caminho/do/curriculo.json \
  --ofertas caminho/do/ofertas.json \
  --limite 24 \
  --prioridade equilibrado \
  --saida grade.json
```

Para considerar todas as matérias em curso como cumpridas:

```bash
python motor_grade.py \
  --boa caminho/do/boa.json \
  --curriculo caminho/do/curriculo.json \
  --ofertas caminho/do/ofertas.json \
  --cursando-cumpridas todas
```

Para desativar optativas:

```bash
python motor_grade.py \
  --boa caminho/do/boa.json \
  --curriculo caminho/do/curriculo.json \
  --ofertas caminho/do/ofertas.json \
  --sem-optativas
```

## 20. Estrutura resumida do fluxo

```text
BOA + currículo + ofertas
          |
          v
Marcar matérias Cursando como cumpridas
          |
          v
Resolver pré-requisitos e equivalências
          |
          v
Separar matérias elegíveis e bloqueadas
          |
          v
Filtrar turmas confirmadas com horário completo
          |
          v
Calcular pontuação das candidatas
          |
          v
Aplicar limite de créditos e orçamento de optativas
          |
          v
Buscar combinações sem choque
          |
          v
Gerar alternativa 1, alternativa 2 e alternativa 3
          |
          v
Permitir edição manual na interface
```

## 21. Limitações conhecidas

- O resultado depende da qualidade e atualidade do PDF do BOA.
- O currículo e as ofertas precisam estar compatíveis com a versão acadêmica do estudante.
- A planilha pode conter horários provisórios ou incompletos.
- O motor considera as turmas confirmadas e externas como utilizáveis.
- Turmas sem horário completo não participam da busca automática.
- A busca possui uma trava de segurança que pode interromper a solução exata em bases muito grandes.
- A grade manual não é revalidada quanto ao limite de créditos, mas choques são identificados na interface.
- A nota final da grade é uma pontuação interna que representa prioridades curriculares, não uma garantia oficial de matrícula.
