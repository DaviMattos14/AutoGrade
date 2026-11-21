# Contexto do projeto: Planejador Automático de Grade (UFRJ)

*Documento para auxiliar inteligência artificial a retomar ou alterar o projeto · atualizado em 21/11/2026*

## 1. Resumo

- **Disciplina:** Computação em Nuvem (curso AWS Cloud Foundations).
- **Produto:** Planejador Automático de Grade para o curso de Ciência da Computação da UFRJ.
- **Curso e currículo atual:** código 85783, versão curricular 2022/2.
- **Entrada principal:** BOA oficial da UFRJ em PDF.
- **Dados fixos:** currículo em JSON e ofertas em JSON por período.
- **Interface:** aplicação web em Streamlit.
- **Produto publicado:** https://auto-grade-sandbox.streamlit.app/
- **Estado atual:** módulos integrados e interface funcional.
- **Próximos trabalhos possíveis:** migração para AWS, diagrama de arquitetura, estimativa de custos, segurança e relatório.

O usuário envia o BOA, confere as disciplinas em curso, ajusta parâmetros e recebe grades sem choque de horário. O motor considera pré-requisitos, equivalências, créditos, optativas, prioridade, áreas de interesse e turmas disponíveis.

## 2. Como a inteligência artificial deve trabalhar neste projeto

- Responder em português do Brasil.
- Preservar a compatibilidade das estruturas JSON e dos formatos de retorno do motor.
- Ler o código atual antes de concluir que uma regra está ativa ou desativada.
- Não assumir que protótipos antigos representam a implementação atual.
- Não inventar dados acadêmicos, currículos, horários ou resultados de testes.
- Fazer mudanças pequenas e verificáveis antes de alterações amplas.
- Atualizar documentação diretamente relacionada à implementação.
- Executar o menor teste que cobre a alteração.
- Tratar PDF do BOA como dado pessoal sensível.
- Não extrair, salvar ou exibir nome, matrícula ou notas do BOA.
- Não copiar dados pessoais do BOA para relatórios ou exemplos.
- Em tutoria, explicar o problema primeiro e depois mostrar o código.
- Neste projeto, o assistente pode gerar e atualizar arquivos conforme solicitado pelo usuário.

## 3. Estado atual da implementação

### Concluído

- Extração do currículo e validação dos dados.
- Extrator da planilha de ofertas.
- Extrator do BOA em PDF.
- Motor automático de combinação de disciplinas e turmas.
- Geração de até três alternativas de grade.
- Conferência das matérias em curso no BOA.
- Configuração de limite de créditos e prioridade.
- Inclusão ou exclusão de optativas.
- Preferência por área de interesse.
- Detecção de choque de horários.
- Edição manual da grade.
- Visualização semanal da grade.
- Exportação em CSV e imagem.
- Consulta separada das ofertas.
- Interface completa em Streamlit.
- README atualizado com telas do produto.
- Documento técnico detalhado do motor em `relatorios/Motor Grade.md`.
- Testes do motor para área de interesse e alternativas.

### Ainda não implementado ou não solicitado

- Arquitetura AWS completa.
- API Gateway.
- Lambda em produção.
- S3 para receber BOAs.
- DynamoDB ou outro armazenamento temporário.
- Diagrama final de infraestrutura.
- Estimativa de custos AWS.
- Validação ampla com muitos BOAs anonimizados.

## 4. Arquitetura atual

```text
PDF do BOA
    |
    v
extrator_boa.py
    |
    v
dados do BOA em memória
    |
    +----------------+
    |                |
    v                v
currículo JSON  ofertas JSON
    |                |
    +--------+-------+
             v
       motor_grade.py
             |
             v
     resultado da grade
             |
             v
          app.py
       interface Streamlit
```

O BOA é lido em memória e não é gravado em disco pela interface. O currículo e as ofertas são dados locais em JSON.

## 5. Estrutura do repositório

- `app.py`: interface Streamlit, estado da sessão, quatro etapas e edição manual.
- `extrator_boa.py`: leitura do PDF do BOA com `pdfplumber`.
- `motor_grade.py`: elegibilidade, pontuação, busca combinatória e alternativas.
- `test_motor_grade.py`: testes automatizados do motor.
- `grades_curricular/curriculo_85783_2022-2.json`: currículo do curso.
- `ofertas/ofertas_2026-2.json`: ofertas do período atual da base.
- `relatorios/`: relatórios, apresentações e documentação técnica.
- `relatorios/Motor Grade.md`: explicação detalhada do motor.
- `assets/tela-inicial.png`: captura da tela inicial.
- `assets/ofertas.png`: captura da consulta de ofertas.
- `README.md`: documentação pública do projeto.
- `requirements.txt`: dependências Python.

Não existe mais um arquivo de currículo na raiz. Ele está dentro de `grades_curricular/`.

## 6. Dependências

O projeto usa:

- Python;
- Streamlit `>=1.50`;
- pdfplumber `>=0.11`;
- Matplotlib `>=3.9`.

Instalação:

```bash
python -m pip install -r requirements.txt
```

Execução:

```bash
streamlit run app.py
```

Testes:

```bash
python -m unittest test_motor_grade.py
```

## 7. Interface em Streamlit

A interface possui quatro etapas:

1. **Enviar BOA**
   - recebe um PDF;
   - identifica o curso e a versão curricular;
   - encontra o currículo correspondente;
   - não mantém o conteúdo do arquivo após a leitura.

2. **Conferir**
   - mostra curso, versão, data de emissão e resumo;
   - permite marcar matérias em curso como cumpridas;
   - informa quais matérias seriam liberadas pela marcação.

3. **Parâmetros**
   - limite de créditos;
   - inclusão ou exclusão de optativas;
   - área de interesse;
   - prioridade;
   - folga de optativas.

4. **Resultado**
   - apresenta até três versões;
   - permite trocar de alternativa;
   - mostra grade semanal;
   - permite editar matérias e turmas;
   - oferece exportação em CSV e imagem;
   - mostra matérias excluídas e motivos.

A aba **Todas as ofertas** permite consultar turmas por código, nome ou docente e visualizar resultados por período, obrigatórias e optativas.

## 8. BOA

O BOA é um PDF com texto selecionável. `extrator_boa.py` usa posições das palavras com `pdfplumber`.

O extrator deve identificar:

- curso;
- versão curricular;
- data de emissão;
- disciplinas cumpridas;
- disciplinas pendentes;
- status da inscrição;
- resumo curricular;
- seção curricular;
- créditos;
- períodos;
- livre escolha;
- extensões;
- equivalências entre matérias.

Principais status:

- `Facultada`: a matéria está disponível ao estudante;
- `Cursando`: não conta como cumprida por padrão;
- `Vedada`: não atende aos pré-requisitos conhecidos pelo BOA;
- estado vazio: a matéria aparece como cumprida.

A leitura deve ser validada contra o currículo sempre que houver arquivos suficientes. Se o PDF não puder ser interpretado, o erro deve ser mostrado claramente ao usuário.

Não persistir nome, matrícula, notas ou conteúdo integral do BOA.

## 9. Currículo

O arquivo atual é `grades_curricular/curriculo_85783_2022-2.json`.

Estrutura relevante:

- `_meta`: curso e versão curricular;
- `disciplinas`: nome, tipo, período, créditos e pré-requisitos;
- `areas_de_interesse`: áreas disponíveis no currículo atual;
- `alias_codigo`: equivalência direta de códigos;
- `equivalencias_extras_de_requisito`: combinações alternativas de requisitos.

A chave oficial atual usada pelo motor é `areas_de_interesse`.

Ao alterar o JSON curricular, atualizar também:

- `achar_curriculo()` em `app.py`;
- compatibilidade entre BOA e currículo;
- áreas de interesse;
- textos e categorias exibidos;
- testes afetados.

## 10. Ofertas

O período atual da base é 2026-2. Os dados estão em `ofertas/ofertas_2026-2.json`.

Cada turma pode conter:

- `id`;
- `codigo_no_curriculo`;
- `codigo`;
- `nome`;
- `situacao`;
- `horario_completo`;
- `docentes`;
- `aulas`;
- `dia_numero`;
- `inicio_min`;
- `fim_min`;
- `sala`;
- outras informações da planilha.

Situações utilizáveis pelo motor:

- `confirmada`;
- `externa`.

Uma turma só entra na busca automática quando:

- possui código associado ao currículo;
- está confirmada ou externa;
- possui horário completo.

As informações da planilha são provisórias e podem mudar. A interface deve orientar a confirmar os horários no SIGA.

## 11. Motor de grade

O motor está em `motor_grade.py`. A documentação detalhada está em `relatorios/Motor Grade.md`.

### Entradas de `gerar_grade()`

- dados do BOA;
- currículo;
- ofertas;
- limite de créditos;
- matérias em curso consideradas cumpridas;
- incluir optativas;
- prioridade;
- folga de créditos de optativas;
- área de interesse;
- conjuntos de grades a evitar;
- diferença mínima entre versões.

### Pré-requisitos

`requisito_satisfeito()` considera:

- requisito cumprido diretamente;
- alias do código;
- equivalência alternativa composta por vários códigos.

Uma matéria marcada como cumprida pode liberar matérias que estavam vedadas.

### Elegibilidade

Uma matéria pendente pode ser candidata quando:

- está facultada ou em curso;
- foi liberada por pré-requisitos marcados como cumpridos;
- pertence ao currículo;
- possui turma utilizável.

Uma matéria vedada permanece bloqueada se falta qualquer pré-requisito.

### Turmas utilizáveis

Confirmada ou externa, com código no currículo e horário completo.

### Pontuação

Obrigatória:

```text
1000
+ bônus pelo período
+ bônus pelas matérias pendentes que ela destrava
```

Optativa:

```text
100
+ bônus pelas matérias que destrava
+ créditos da matéria
+ 100 quando pertence à área de interesse
```

Pesos por prioridade:

| Prioridade | Período | Destrava |
| --- | ---: | ---: |
| `periodos` | 20 | 5 |
| `equilibrado` | 10 | 10 |
| `prerequisitos` | 5 | 20 |

### Limite e optativas

- o limite geral é configurado pelo usuário;
- optativas condicionadas e humanidades possuem orçamento separado;
- optativas só entram até a quantidade faltante mais uma folga;
- desativar optativas define o orçamento dessas categorias como zero.

### Choque de horários

Há choque quando duas aulas:

- estão no mesmo dia;
- possuem intervalos que se sobrepõem.

Uma turma que termina exatamente quando outra começa não colide.

### Busca

`buscar_melhor_combinacao()` usa ramificação e poda:

- tenta cada turma da matéria;
- tenta não incluir a matéria;
- mantém aulas ocupadas;
- acumula créditos;
- calcula limite superior;
- descarta ramos que não podem superar a melhor grade;
- possui limite de segurança de dois milhões de nós.

Se a busca atingir o limite, o resultado pode ser a melhor grade encontrada até o momento, não necessariamente a solução completa.

### Versões alternativas

`gerar_versoes_da_grade()` gera até três versões:

- versão 1: melhor grade;
- versão 2: melhor grade que difere da 1 em pelo menos duas matérias;
- versão 3: melhor grade que difere da 1 e da 2 em pelo menos duas matérias.

Uma alternativa não pode ser apenas um subconjunto da anterior.

### Edição manual

`listar_materias_disponiveis()` classifica matérias disponíveis, bloqueadas e sem turma.

`explicar_choque()` encontra conflitos entre uma turma candidata e a grade atual.

`montar_grade_da_selecao()` transforma as escolhas do usuário no formato utilizado pela interface.

Na grade editada, pontuação e matérias excluídas deixam de representar o resultado automático original.

## 12. Convenções de código

- Arquivos Python codificados em UTF-8.
- Strings e documentos do usuário em português.
- Funções com nomes em português e orientadas a uma responsabilidade clara.
- Nomes de parâmetros e chaves JSON devem ser mantidos por compatibilidade.
- Não alterar silenciosamente a estrutura de retorno de `gerar_grade()`.
- Campos `_meta`, `grade`, `nao_incluidas`, `sem_horario_fixo`, `estatisticas` e `avisos` fazem parte do formato atual.
- Utilizar `ErroDoMotor` para entradas incompatíveis ou inválidas.
- Utilizar `ErroDeBOA` para problemas específicos da leitura do BOA.
- Não marcar uma execução como concluída sem verificar resultado, testes ou comportamento visível.
- Não remover arquivos ou dados não relacionados à alteração.

## 13. Testes existentes

`test_motor_grade.py` cobre:

- efeito da área de interesse;
- preferência entre optativas em choque;
- ausência de preferência;
- área sem oferta;
- áreas não liberando matérias vedadas;
- desativação de optativas;
- limite de créditos;
- prioridade de obrigatórias;
- área inválida;
- aplicação da preferência nas três versões;
- correspondência das áreas com optativas condicionadas.

Comando:

```bash
python -m unittest test_motor_grade.py
```

Ao implementar comportamento novo no motor, adicionar casos focados ao mesmo arquivo ou criar um novo arquivo de testes existente no padrão.

## 14. Histórico de decisões

Decisões já consolidadas:

- Cursando não conta como cumprida por padrão.
- Facultada é elegível.
- Vedada é recalculada pela marcação de matérias em curso.
- Turmas confirmadas e externas são utilizáveis.
- Turmas sem horário completo não entram na busca automática.
- Encostar horários não é choque.
- A busca deve ser exata enquanto não atingir o limite de segurança.
- Optativas são limitadas pelo que falta e não apenas pelo limite geral.
- Até três alternativas podem ser exibidas.
- O PDF não é armazenado.
- A implementação AWS é uma evolução, não uma dependência da versão local.

Pontos que ainda podem mudar:

- validação em massa com BOAs de perfis diferentes;
- pesos das prioridades para perfis acadêmicos ainda não testados;
- seleção manual mais detalhada de optativas;
- apresentação oficial dos horários provisórios;
- arquitetura AWS final;
- persistência temporária de estado e TTL;
- adaptação para outros cursos e currículos.

## 15. Migração AWS planejada

Uma implementação futura pode usar:

- **S3:** hospedagem estática, dados públicos e, se necessário, uploads privados temporários;
- **Lambda:** extrair BOA e executar o motor;
- **API Gateway:** receber chamadas HTTP;
- **DynamoDB:** guardar resultados temporários com TTL;
- **CloudWatch:** logs e métricas;
- **KMS:** proteção de dados, se houver armazenamento;
- **WAF:** proteção da API pública.

Recomendações:

- não usar um bucket público para o BOA;
- remover o BOA imediatamente após o processamento;
- limitar tamanho e tipo do upload;
- aplicar timeout e memória adequados às Lambdas;
- preferir dados públicos do currículo e ofertas em objetos separados;
- usar TTL em dados temporários;
- registrar arquitetura, responsabilidades compartilhadas e custos;
- não expor logs ou payloads com dados pessoais.

## 16. Arquivos que uma IA deve consultar

Para continuidade geral:

1. este documento;
2. `README.md`;
3. `relatorios/Motor Grade.md`;
4. `app.py`;
5. `motor_grade.py`;
6. `extrator_boa.py`;
7. `test_motor_grade.py`;
8. currículo e oferta relevantes.

Para mudanças específicas:

- interface ou estado da sessão: `app.py`;
- busca ou pontuação: `motor_grade.py`;
- leitura do BOA: `extrator_boa.py`;
- dados curriculares: `grades_curricular/`;
- ofertas: `ofertas/`;
- testes: `test_motor_grade.py`;
- instruções públicas: `README.md`.

## 17. Como retomar o trabalho

Ao iniciar em um novo contexto, forneça este documento e o objetivo concreto da tarefa.

Exemplo:

```text
Continuar a partir deste contexto.
Melhore a página de conferência do BOA:
1. preservar a separação entre BOA, currículo e oferta;
2. mostrar o efeito das marcações Cursando;
3. adicionar testes visuais ou automatizados possíveis;
4. não alterar a pontuação do motor.
```

Antes de concluir uma tarefa, informar:

- arquivos alterados;
- comportamento implementado;
- testes executados;
- pontos pendentes ou limitações encontradas.
