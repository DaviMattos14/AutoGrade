#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
motor_grade.py  (versão beta)
=============================
Escolhe a melhor grade do próximo período a partir de três JSONs já limpos:
  * boa_extraido.json          (saída do extrator_boa.py)
  * curriculo_85783_2022-2.json
  * ofertas_2026-2.json        (saída do extrator_ofertas.py)

Uso:
    python motor_grade.py --boa boa_extraido.json --curriculo curriculo_85783_2022-2.json \
                          --ofertas ofertas_2026-2.json --limite 24 --saida grade.json
    # marcando matérias "Cursando" como já cumpridas:
    python motor_grade.py ... --cursando-cumpridas ICP362,ICP082      (ou "todas")

Como função (para o Streamlit ou para uma Lambda):
    from motor_grade import gerar_grade
    resultado = gerar_grade(boa, curriculo, ofertas, limite_de_creditos=24, cursando_como_cumpridas=["ICP362"])

Regras (as combinadas no projeto)
---------------------------------
1. Candidatas: matérias PENDENTES do BOA que estejam liberadas e tenham turma confirmada (ou de
   outra unidade) com horário completo na planilha de ofertas.
2. "Cursando" conta como NÃO cumprida, a menos que o usuário a marque como cumprida. Ao marcar,
   as matérias "Vedada" cujos pré-requisitos passam a estar completos ficam liberadas.
   Fora isso, vale sempre o status do BOA.
3. Restrições: uma turma por matéria; nenhum choque de horário; limite de créditos;
   optativas só até o que ainda falta cumprir (mais uma pequena folga para fechar matérias inteiras).
4. Objetivo: maximizar a pontuação. Obrigatórias valem muito mais que optativas; entre as
   obrigatórias, pesam o período mais baixo e quantas matérias pendentes cada uma destrava.
5. A busca é exata (ramifica e poda): acha a melhor combinação, e não uma aproximação.
"""

import argparse
import json
import sys
from datetime import datetime

VERSAO_DO_MOTOR = "0.1-beta"

# ----------------------------------------------------------------------------------------
# Parâmetros de pontuação
# ----------------------------------------------------------------------------------------
# (peso do período baixo, peso de "destrava outras matérias") por tipo de prioridade
PESOS_DA_PRIORIDADE = {"periodos": (20, 5), "equilibrado": (10, 10), "prerequisitos": (5, 20)}
PONTOS_BASE_OBRIGATORIA = 1000    # obrigatórias sempre vencem optativas
PONTOS_BASE_OPTATIVA = 100
BONUS_AREA_DE_INTERESSE = 100    # favorece a área escolhida, mantendo as demais optativas elegíveis
PERIODO_MAXIMO = 10               # o bônus de período é (PERIODO_MAXIMO - período)
CREDITO_EXTRA_PADRAO_DE_OPTATIVAS = 3   # folga para completar matérias inteiras (ex.: faltam 6, cabem 8)
LIMITE_DE_NOS_DA_BUSCA = 2_000_000       # trava de segurança; se estourar, devolve a melhor achada
SITUACOES_UTILIZAVEIS = ("confirmada", "externa")
CATEGORIAS_DE_OPTATIVA = ("optativa_condicionada", "optativa_restrita_humanidades")
ROTULO_DA_CATEGORIA = {"obrigatoria": "Obrigatória", "optativa_condicionada": "Optativa",
                       "optativa_restrita_humanidades": "Humanidades"}
CHAVE_DO_RESUMO = {"optativa_condicionada": "escolha_condicionada",
                   "optativa_restrita_humanidades": "escolha_restrita_humanidades"}
DIAS_DA_SEMANA = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]
EPSILON = 1e-9


class ErroDoMotor(Exception):
    """Entrada inválida (parâmetro ou arquivo incoerente)."""


# ========================================================================================
# PARTE 1: o núcleo de busca (não conhece BOA, currículo nem planilha: só números)
# ========================================================================================
def aulas_se_sobrepoem(aulas_a, aulas_b):
    """Duas listas de (dia, início, fim) colidem se há um dia em comum e os intervalos se cruzam.
    Encostar (um termina quando o outro começa) NÃO é choque."""
    return any(dia_a == dia_b and inicio_a < fim_b and inicio_b < fim_a
               for dia_a, inicio_a, fim_a in aulas_a for dia_b, inicio_b, fim_b in aulas_b)


def buscar_melhor_combinacao(assuntos, limite_de_creditos, orcamento_por_categoria, limite_de_nos=LIMITE_DE_NOS_DA_BUSCA,
                             conjuntos_a_evitar=(), diferenca_minima=2):
    """
    assuntos: lista de dicionários
        {"codigo", "pontuacao", "creditos", "categoria", "turmas": [{"id", "aulas": [(dia, início, fim), ...]}]}
    orcamento_por_categoria: créditos máximos por categoria (categoria ausente = sem limite)

    conjuntos_a_evitar: conjuntos de CÓDIGOS de matérias (grades já mostradas). Uma grade só vale se o seu
        conjunto de matérias diferir de cada um deles em pelo menos `diferenca_minima` matérias (uma troca
        "sai A, entra B" conta 2) e tiver pelo menos uma matéria que ele não tem. É assim que se acham as versões 2 e 3: a melhor grade que ainda é diferente.
        Sem esses conjuntos, o comportamento é exatamente o de sempre.

    Devolve (pontuação, [(código da matéria, id da turma), ...], busca_completa, nós visitados).
    Ramifica e poda: para cada matéria, tenta cada turma ou pula a matéria, e descarta o ramo
    quando nem o melhor caso possível (mochila fracionária, ignorando choques) supera a melhor
    grade já encontrada.
    """
    assuntos = sorted(assuntos, key=lambda a: (-a["pontuacao"], a["codigo"]))
    quantidade = len(assuntos)
    ordem_por_densidade = sorted(range(quantidade), key=lambda i: -(
        assuntos[i]["pontuacao"] / assuntos[i]["creditos"] if assuntos[i]["creditos"] > 0 else float("inf")))

    melhor = {"pontuacao": -1.0, "escolha": []}
    nos_visitados, interrompida = [0], [False]
    escolha_atual, aulas_ocupadas = [], []
    creditos_por_categoria = {}

    def limite_superior(primeiro, pontuacao_atual, creditos_livres):
        """Melhor pontuação teórica possível a partir daqui (relaxando choques e orçamentos)."""
        total, livres = pontuacao_atual, creditos_livres
        for indice in ordem_por_densidade:
            if indice < primeiro:
                continue
            assunto = assuntos[indice]
            if assunto["creditos"] <= livres + EPSILON:
                total += assunto["pontuacao"]
                livres -= assunto["creditos"]
            else:
                total += assunto["pontuacao"] * max(livres, 0) / assunto["creditos"]
                break
        return total

    def diferente_o_bastante():
        """A grade que está sendo montada difere o suficiente das grades que devem ser evitadas?"""
        if not conjuntos_a_evitar:
            return True
        atual = {codigo for codigo, _ in escolha_atual}
        # Além de diferir em >= diferenca_minima matérias, precisa ter ALGUMA matéria que a outra grade não tem
        # (senão a "versão" seria só a anterior com matérias a menos, o que não é uma alternativa de verdade).
        return all(len(atual ^ evitar) >= diferenca_minima and atual - evitar for evitar in conjuntos_a_evitar)

    def explorar(indice, pontuacao, creditos):
        nos_visitados[0] += 1
        if nos_visitados[0] > limite_de_nos:
            interrompida[0] = True
            return
        if pontuacao > melhor["pontuacao"] and diferente_o_bastante():
            melhor["pontuacao"], melhor["escolha"] = pontuacao, list(escolha_atual)
        if indice == quantidade:
            return
        if limite_superior(indice, pontuacao, limite_de_creditos - creditos) <= melhor["pontuacao"] + EPSILON:
            return

        assunto = assuntos[indice]
        categoria = assunto["categoria"]
        cabe_nos_creditos = creditos + assunto["creditos"] <= limite_de_creditos + EPSILON
        cabe_no_orcamento = (creditos_por_categoria.get(categoria, 0) + assunto["creditos"]
                             <= orcamento_por_categoria.get(categoria, float("inf")) + EPSILON)
        if cabe_nos_creditos and cabe_no_orcamento:
            for turma in assunto["turmas"]:
                if aulas_se_sobrepoem(turma["aulas"], aulas_ocupadas):
                    continue
                escolha_atual.append((assunto["codigo"], turma["id"]))
                aulas_ocupadas.extend(turma["aulas"])
                creditos_por_categoria[categoria] = creditos_por_categoria.get(categoria, 0) + assunto["creditos"]
                explorar(indice + 1, pontuacao + assunto["pontuacao"], creditos + assunto["creditos"])
                creditos_por_categoria[categoria] -= assunto["creditos"]
                del aulas_ocupadas[len(aulas_ocupadas) - len(turma["aulas"]):]
                escolha_atual.pop()
        explorar(indice + 1, pontuacao, creditos)  # alternativa: não cursar esta matéria agora

    explorar(0, 0.0, 0.0)
    return melhor["pontuacao"], melhor["escolha"], not interrompida[0], nos_visitados[0]


# ========================================================================================
# PARTE 2: regras do projeto (BOA + currículo + ofertas -> candidatas -> grade)
# ========================================================================================
def requisito_satisfeito(requisito, feitas, alias, extras):
    """O requisito vale se foi cumprido, ou se algum código equivalente (alias ou extra) foi."""
    if requisito in feitas or alias.get(requisito) in feitas:
        return True
    return any(x["codigo"] == requisito and any(all(c in feitas for c in alternativa) for alternativa in x["alternativas"])
               for x in extras)


def contar_materias_que_cada_uma_destrava(codigos_pendentes, disciplinas, alias):
    """Para cada matéria pendente, quantas outras matérias PENDENTES dependem dela (direta ou em cadeia)."""
    dependentes_diretos = {}
    for codigo in codigos_pendentes:
        for requisito in disciplinas.get(codigo, {}).get("requisitos", []):
            dependentes_diretos.setdefault(alias.get(requisito, requisito), set()).add(codigo)
    destrava = {}
    for codigo in codigos_pendentes:
        visitadas, pilha = set(), [codigo]
        while pilha:
            for dependente in dependentes_diretos.get(pilha.pop(), ()):
                if dependente not in visitadas:
                    visitadas.add(dependente)
                    pilha.append(dependente)
        destrava[codigo] = len(visitadas)
    return destrava


def calcular_efeito_da_marcacao(dados_do_boa, curriculo, ofertas, codigo):
    """
    Se o usuário marcar `codigo` (uma matéria 'Cursando') como cumprida, quais matérias 'Vedada'
    passam a ter todos os pré-requisitos completos? E quais delas têm turma utilizável no período?
    (Mesma regra do motor: só conta matéria liberada POR causa da marcação.)
    """
    disciplinas = curriculo["disciplinas"]
    alias = curriculo.get("alias_codigo", {})
    extras = curriculo.get("equivalencias_extras_de_requisito", [])
    feitas_antes = {c["codigo"] for c in dados_do_boa["cumpridas"]}
    feitas_depois = feitas_antes | {codigo}
    liberadas = []
    for pendente in dados_do_boa["pendentes"]:
        if pendente["status"] != "Vedada" or pendente["codigo"] == codigo or pendente["codigo"] not in disciplinas:
            continue
        requisitos = disciplinas[pendente["codigo"]]["requisitos"]
        if (all(requisito_satisfeito(r, feitas_depois, alias, extras) for r in requisitos)
                and not all(requisito_satisfeito(r, feitas_antes, alias, extras) for r in requisitos)):
            liberadas.append(pendente["codigo"])
    com_turma = {t["codigo_no_curriculo"] for t in ofertas["turmas"]
                 if t.get("codigo_no_curriculo") and t["situacao"] in SITUACOES_UTILIZAVEIS and t["horario_completo"]}
    return {"liberadas": sorted(liberadas), "ofertadas": sorted(c for c in liberadas if c in com_turma)}


def formatar_horarios(aulas):
    return " · ".join(f'{a["dia"]} {a["inicio"]}–{a["fim"]}' for a in aulas)


def descrever_choque(turma_candidata, escolhidas):
    """Texto curto: com quais matérias escolhidas a turma colide, e em que dia e horário."""
    detalhes = []
    for escolhida in escolhidas:
        for aula_a in turma_candidata["aulas_lista"]:
            for aula_b in escolhida["aulas_lista"]:
                if aula_a[0] == aula_b[0] and aula_a[1] < aula_b[2] and aula_b[1] < aula_a[2]:
                    detalhes.append((escolhida["codigo"], DIAS_DA_SEMANA[aula_a[0]],
                                     f"{aula_a[1] // 60:02d}:{aula_a[1] % 60:02d}–{aula_a[2] // 60:02d}:{aula_a[2] % 60:02d}"))
    codigos = sorted({d[0] for d in detalhes})
    dias = sorted({d[1] for d in detalhes}, key=DIAS_DA_SEMANA.index)
    faixas = sorted({d[2] for d in detalhes})
    return f'choque de horário com {", ".join(codigos)} ({" e ".join(dias)}, {" / ".join(faixas)})'


def gerar_grade(dados_do_boa, curriculo, ofertas, limite_de_creditos=24, cursando_como_cumpridas=(),
                incluir_optativas=True, prioridade="equilibrado",
                credito_extra_de_optativas=CREDITO_EXTRA_PADRAO_DE_OPTATIVAS,
                conjuntos_a_evitar=(), diferenca_minima=2, area_de_interesse=None):
    if prioridade not in PESOS_DA_PRIORIDADE:
        raise ErroDoMotor(f"prioridade deve ser uma de {list(PESOS_DA_PRIORIDADE)}")
    peso_periodo, peso_destrava = PESOS_DA_PRIORIDADE[prioridade]
    areas = curriculo.get("areas_de_interesse", {})
    if area_de_interesse is not None and area_de_interesse not in areas:
        raise ErroDoMotor("Área de interesse não encontrada no currículo.")
    codigos_da_area = set(areas.get(area_de_interesse, ()))
    avisos = []

    # ---------- confere se as três fontes são compatíveis ----------
    meta_curriculo = curriculo["_meta"]
    if (dados_do_boa["curso"]["codigo"], dados_do_boa["versao_curricular"]) != (meta_curriculo["curso_codigo"], meta_curriculo["versao_curricular"]):
        raise ErroDoMotor(f'O BOA é do curso {dados_do_boa["curso"]["codigo"]} versão {dados_do_boa["versao_curricular"]}, '
                          f'mas o currículo carregado é {meta_curriculo["curso_codigo"]} versão {meta_curriculo["versao_curricular"]}.')
    disciplinas = curriculo["disciplinas"]
    alias = curriculo.get("alias_codigo", {})
    extras = curriculo.get("equivalencias_extras_de_requisito", [])

    # ---------- "Cursando": o que o usuário marcou como cumprido ----------
    em_curso = {p["codigo"] for p in dados_do_boa["pendentes"] if p["status"] == "Cursando"}
    if cursando_como_cumpridas == "todas":
        cursando_como_cumpridas = sorted(em_curso)
    marcadas = []
    for codigo in cursando_como_cumpridas:
        if codigo in em_curso:
            marcadas.append(codigo)
        else:
            avisos.append({"tipo": "marcacao_ignorada", "detalhe": f"{codigo} não está como 'Cursando' no BOA"})

    feitas_originais = {c["codigo"] for c in dados_do_boa["cumpridas"]}
    feitas_com_marcadas = feitas_originais | set(marcadas)
    pendentes = [p for p in dados_do_boa["pendentes"] if p["codigo"] not in marcadas]
    pendentes_por_codigo = {p["codigo"]: p for p in pendentes}

    # ---------- elegibilidade: vale o status do BOA; a marcação do usuário pode liberar "Vedada" ----------
    elegiveis, bloqueadas = {}, {}
    for pendente in pendentes:
        codigo = pendente["codigo"]
        if pendente["status"] in ("Facultada", "Cursando"):
            elegiveis[codigo] = pendente
            continue
        requisitos = disciplinas.get(codigo, {}).get("requisitos", [])
        completos_antes = all(requisito_satisfeito(r, feitas_originais, alias, extras) for r in requisitos)
        completos_depois = all(requisito_satisfeito(r, feitas_com_marcadas, alias, extras) for r in requisitos)
        if completos_depois and not completos_antes:   # liberada POR causa da marcação do usuário
            elegiveis[codigo] = pendente
        else:
            faltam = [alias.get(r, r) for r in requisitos if not requisito_satisfeito(r, feitas_com_marcadas, alias, extras)]
            bloqueadas[codigo] = {"pendente": pendente, "faltam": faltam}

    # ---------- turmas utilizáveis por matéria ----------
    turmas_por_materia = {}
    for turma in ofertas["turmas"]:
        codigo = turma.get("codigo_no_curriculo")
        if codigo and turma["situacao"] in SITUACOES_UTILIZAVEIS and turma["horario_completo"]:
            turmas_por_materia.setdefault(codigo, []).append(turma)
    alertas_por_turma = {}
    for aviso in ofertas.get("avisos", []):
        if aviso["tipo"] == "aulas_nao_somam_as_horas":
            alertas_por_turma[aviso["turma"]] = "horário possivelmente incompleto na planilha provisória; confirme no SIGA"

    # ---------- pontuação, orçamentos e candidatas ----------
    destrava = contar_materias_que_cada_uma_destrava(list(pendentes_por_codigo), disciplinas, alias)
    orcamento = {}
    for categoria in CATEGORIAS_DE_OPTATIVA:
        if not incluir_optativas:
            orcamento[categoria] = 0.0
            continue
        linha_do_resumo = dados_do_boa.get("resumo", {}).get(CHAVE_DO_RESUMO[categoria])
        if linha_do_resumo is None:
            avisos.append({"tipo": "resumo_ausente", "detalhe": f"sem limite de optativas para {categoria}"})
            continue
        ja_marcadas = sum(disciplinas[c]["creditos"] for c in marcadas if disciplinas.get(c, {}).get("tipo") == (
            "optativa_condicionada" if categoria == "optativa_condicionada" else "optativa_restrita_humanidades"))
        orcamento[categoria] = max(0.0, linha_do_resumo["falta_creditos"] - ja_marcadas) + (credito_extra_de_optativas if linha_do_resumo["falta_creditos"] - ja_marcadas > 0 else 0)

    assuntos, sem_turma = [], []
    for codigo, pendente in elegiveis.items():
        categoria = pendente["secao"]
        disciplina = disciplinas[codigo]
        if categoria in CATEGORIAS_DE_OPTATIVA and orcamento.get(categoria, float("inf")) <= 0:
            continue                       # optativa que o aluno não precisa cursar agora
        turmas = turmas_por_materia.get(codigo, [])
        if not turmas:
            sem_turma.append(codigo)
            continue
        if categoria == "obrigatoria":
            pontuacao = (PONTOS_BASE_OBRIGATORIA + peso_periodo * (PERIODO_MAXIMO - (disciplina["periodo"] or PERIODO_MAXIMO))
                         + peso_destrava * destrava[codigo])
        else:
            pontuacao = PONTOS_BASE_OPTATIVA + peso_destrava * destrava[codigo] + disciplina["creditos"]
            if categoria == "optativa_condicionada" and codigo in codigos_da_area:
                pontuacao += BONUS_AREA_DE_INTERESSE
        assuntos.append({
            "codigo": codigo, "pontuacao": float(pontuacao), "creditos": float(disciplina["creditos"]), "categoria": categoria,
            "turmas": [{"id": t["id"], "aulas": [(a["dia_numero"], a["inicio_min"], a["fim_min"]) for a in t["aulas"]]} for t in turmas],
        })

    # ---------- a busca ----------
    pontuacao, escolha, completa, nos = buscar_melhor_combinacao(assuntos, limite_de_creditos, orcamento,
                                                                 conjuntos_a_evitar=conjuntos_a_evitar,
                                                                 diferenca_minima=diferenca_minima)
    if not completa:
        avisos.append({"tipo": "busca_interrompida", "detalhe": "limite de segurança atingido; a grade é a melhor encontrada, não necessariamente a ótima"})

    # ---------- monta o resultado ----------
    turmas_por_id = {t["id"]: t for t in ofertas["turmas"]}
    grade = []
    for codigo, id_da_turma in escolha:
        turma, disciplina = turmas_por_id[id_da_turma], disciplinas[codigo]
        categoria = elegiveis[codigo]["secao"]
        if categoria == "obrigatoria":
            motivo = f'Obrig. · período {disciplina["periodo"]}' + (f' · destrava {destrava[codigo]}' if destrava[codigo] else "")
        else:
            motivo = ROTULO_DA_CATEGORIA[categoria] + (f' · destrava {destrava[codigo]}' if destrava[codigo] else "")
            if categoria == "optativa_condicionada" and codigo in codigos_da_area:
                motivo += f' · área de interesse: {area_de_interesse}'
        grade.append({
            "codigo": codigo, "nome": disciplina["nome"], "tipo": ROTULO_DA_CATEGORIA[categoria], "categoria": categoria,
            "creditos": disciplina["creditos"], "periodo": disciplina["periodo"], "turma_id": id_da_turma,
            "docentes": turma["docentes"], "situacao_da_turma": turma["situacao"],
            "aulas": [{k: a[k] for k in ("dia", "dia_numero", "inicio", "fim", "inicio_min", "fim_min", "sala")} for a in turma["aulas"]],
            "motivo": motivo, "em_curso_no_boa": codigo in em_curso,
            "alerta": alertas_por_turma.get(id_da_turma),
        })
    grade.sort(key=lambda g: (g["categoria"] != "obrigatoria", g["periodo"] or 99, g["codigo"]))
    creditos_usados = sum(g["creditos"] for g in grade)

    # ---------- por que cada candidata ficou de fora ----------
    escolhidas = [{"codigo": g["codigo"], "aulas_lista": [(a["dia_numero"], a["inicio_min"], a["fim_min"]) for a in g["aulas"]]} for g in grade]
    creditos_por_categoria = {}
    for g in grade:
        creditos_por_categoria[g["categoria"]] = creditos_por_categoria.get(g["categoria"], 0) + g["creditos"]
    codigos_escolhidos = {g["codigo"] for g in grade}
    nao_incluidas = []
    for assunto in sorted(assuntos, key=lambda a: (a["categoria"] != "obrigatoria", a["codigo"])):
        if assunto["codigo"] in codigos_escolhidos:
            continue
        candidatas = [{"aulas_lista": t["aulas"]} for t in assunto["turmas"]]
        if all(aulas_se_sobrepoem(c["aulas_lista"], [x for e in escolhidas for x in e["aulas_lista"]]) for c in candidatas):
            motivo = descrever_choque(candidatas[0], escolhidas)
        elif creditos_usados + assunto["creditos"] > limite_de_creditos + EPSILON:
            motivo = "limite de créditos"
        elif creditos_por_categoria.get(assunto["categoria"], 0) + assunto["creditos"] > orcamento.get(assunto["categoria"], float("inf")) + EPSILON:
            motivo = "as optativas escolhidas já cobrem os créditos que faltam"
        elif conjuntos_a_evitar:
            motivo = "esta versão usa outra combinação de matérias"
        else:
            motivo = "pontuação menor que a das matérias escolhidas"
        nao_incluidas.append({"codigo": assunto["codigo"], "nome": disciplinas[assunto["codigo"]]["nome"],
                              "tipo": ROTULO_DA_CATEGORIA[assunto["categoria"]], "motivo": motivo})

    # obrigatórias liberadas mas sem turma com horário (atividades sem horário fixo ou não ofertadas)
    sem_horario_fixo = [{"codigo": c, "nome": disciplinas[c]["nome"], "motivo": "sem turma com horário na planilha de ofertas"}
                        for c in sorted(sem_turma) if elegiveis[c]["secao"] == "obrigatoria"]
    # obrigatórias bloqueadas por pré-requisito
    for codigo, info in sorted(bloqueadas.items()):
        if info["pendente"]["secao"] != "obrigatoria" and codigo not in turmas_por_materia:
            continue  # optativa bloqueada e sem turma: não vale listar
        faltantes = ", ".join(f + (" (em curso)" if f in em_curso else "") for f in info["faltam"]) or "indefinido (vale o status do BOA)"
        nao_incluidas.append({"codigo": codigo, "nome": disciplinas[codigo]["nome"], "tipo": ROTULO_DA_CATEGORIA[info["pendente"]["secao"]],
                              "motivo": f"bloqueada (Vedada): pré-requisito pendente {faltantes}"})

    # optativas ainda necessárias, mas sem nenhuma turma ofertada
    for categoria in CATEGORIAS_DE_OPTATIVA:
        resumo = dados_do_boa.get("resumo", {}).get(CHAVE_DO_RESUMO[categoria])
        if resumo and incluir_optativas and orcamento.get(categoria, 1) > 0:
            ofertadas = [a for a in assuntos if a["categoria"] == categoria]
            if not ofertadas:
                avisos.append({"tipo": "sem_oferta_de_optativas", "detalhe":
                               f'faltam {resumo["falta_creditos"]:g} créditos de {ROTULO_DA_CATEGORIA[categoria]} e nenhuma turma disponível neste período'})

    return {
        "_meta": {"motor": f"motor_grade.py {VERSAO_DO_MOTOR}", "gerado_em": datetime.now().isoformat(timespec="seconds"),
                  "periodo_das_ofertas": ofertas["_meta"]["periodo"], "aviso_da_planilha": ofertas["_meta"].get("aviso_da_planilha"),
                  "curso": dados_do_boa["curso"], "versao_curricular": dados_do_boa["versao_curricular"],
                  "parametros": {"limite_de_creditos": limite_de_creditos, "cursando_como_cumpridas": marcadas,
                                 "incluir_optativas": incluir_optativas, "prioridade": prioridade,
                                 "credito_extra_de_optativas": credito_extra_de_optativas,
                                 "area_de_interesse": area_de_interesse},
                  "orcamento_de_optativas": {k: (None if v == float("inf") else v) for k, v in orcamento.items()}},
        "grade": grade,
        "creditos_total": creditos_usados,
        "pontuacao": pontuacao,
        "nao_incluidas": nao_incluidas,
        "sem_horario_fixo": sem_horario_fixo,
        "estatisticas": {"candidatas": len(assuntos), "nos_visitados": nos, "busca_completa": completa},
        "avisos": avisos,
    }


# ========================================================================================
# PARTE 2a: versões alternativas da grade
# ========================================================================================
def gerar_versoes_da_grade(dados_do_boa, curriculo, ofertas, quantidade=3, diferenca_minima=2, **parametros):
    """
    Devolve até `quantidade` grades (cada uma no mesmo formato do gerar_grade), da melhor para a pior.
    A versão 1 é a grade de sempre. A versão 2 é a MELHOR grade cujo conjunto de matérias difere da 1
    em pelo menos `diferenca_minima` matérias; a versão 3 difere da 1 e da 2. A busca continua exata.
    Pode devolver menos versões se não existirem grades suficientemente diferentes.

    `parametros` são os mesmos do gerar_grade (limite_de_creditos, cursando_como_cumpridas,
    incluir_optativas, prioridade, credito_extra_de_optativas, area_de_interesse).
    Cada resultado ganha _meta["versao"] e _meta["diferencas_da_versao_1"] ({"entram": [...], "saem": [...]}).
    """
    versoes, a_evitar = [], []
    for numero in range(1, quantidade + 1):
        resultado = gerar_grade(dados_do_boa, curriculo, ofertas, conjuntos_a_evitar=list(a_evitar),
                                diferenca_minima=diferenca_minima, **parametros)
        codigos = frozenset(g["codigo"] for g in resultado["grade"])
        if numero > 1 and not codigos:        # não sobrou nenhuma grade diferente: para por aqui
            break
        resultado["_meta"]["versao"] = numero
        versoes.append(resultado)
        a_evitar.append(codigos)
    base = {g["codigo"] for g in versoes[0]["grade"]}
    for resultado in versoes:
        codigos = {g["codigo"] for g in resultado["grade"]}
        resultado["_meta"]["diferencas_da_versao_1"] = {"entram": sorted(codigos - base), "saem": sorted(base - codigos)}
    return versoes


# ========================================================================================
# PARTE 2b: edição manual da grade (usada pela interface; NÃO altera o que gerar_grade faz)
# ========================================================================================
def listar_materias_disponiveis(dados_do_boa, curriculo, ofertas, cursando_como_cumpridas=()):
    """
    Classifica as matérias PENDENTES do BOA para o período das ofertas, com as mesmas regras de
    elegibilidade do gerar_grade (vale o status do BOA; marcar um "Cursando" como cumprido pode
    liberar matérias "Vedada"). Diferença: aqui NÃO há limite de créditos nem orçamento de optativas,
    porque quem edita a grade pode escolher qualquer matéria que esteja ao seu alcance.

    Devolve um dicionário com:
      disponiveis : matérias liberadas e com pelo menos uma turma utilizável (cada uma traz "turmas")
      bloqueadas  : matérias "Vedada" por pré-requisito (com a lista "faltam")
      sem_turma   : matérias liberadas, mas sem turma confirmada com horário completo
      cumpridas   : conjunto de códigos já cumpridos (inclui os "Cursando" marcados como cumpridos)
      alertas_por_turma : {id da turma: texto de alerta} (horário possivelmente incompleto)
    """
    disciplinas = curriculo["disciplinas"]
    alias = curriculo.get("alias_codigo", {})
    extras = curriculo.get("equivalencias_extras_de_requisito", [])

    em_curso = {p["codigo"] for p in dados_do_boa["pendentes"] if p["status"] == "Cursando"}
    if cursando_como_cumpridas == "todas":
        cursando_como_cumpridas = sorted(em_curso)
    marcadas = [c for c in cursando_como_cumpridas if c in em_curso]

    feitas_originais = {c["codigo"] for c in dados_do_boa["cumpridas"]}
    feitas_com_marcadas = feitas_originais | set(marcadas)
    pendentes = [p for p in dados_do_boa["pendentes"] if p["codigo"] not in marcadas]
    destrava = contar_materias_que_cada_uma_destrava([p["codigo"] for p in pendentes], disciplinas, alias)

    # turmas utilizáveis por matéria (mesmo filtro do motor)
    turmas_por_materia = {}
    for turma in ofertas["turmas"]:
        codigo = turma.get("codigo_no_curriculo")
        if codigo and turma["situacao"] in SITUACOES_UTILIZAVEIS and turma["horario_completo"]:
            turmas_por_materia.setdefault(codigo, []).append(turma)
    alertas_por_turma = {aviso["turma"]: "horário possivelmente incompleto na planilha provisória; confirme no SIGA"
                         for aviso in ofertas.get("avisos", []) if aviso["tipo"] == "aulas_nao_somam_as_horas"}

    disponiveis, bloqueadas, sem_turma = [], [], []
    for pendente in pendentes:
        codigo = pendente["codigo"]
        disciplina = disciplinas.get(codigo, {})
        materia = {
            "codigo": codigo, "nome": disciplina.get("nome", pendente["nome"]), "categoria": pendente["secao"],
            "tipo": ROTULO_DA_CATEGORIA[pendente["secao"]], "periodo": disciplina.get("periodo"),
            "creditos": disciplina.get("creditos", pendente.get("creditos") or 0),
            "status_no_boa": pendente["status"], "destrava": destrava[codigo],
            "em_curso_no_boa": codigo in em_curso, "turmas": turmas_por_materia.get(codigo, []),
        }
        if pendente["status"] in ("Facultada", "Cursando"):
            elegivel = True
        else:
            requisitos = disciplina.get("requisitos", [])
            completos_antes = all(requisito_satisfeito(r, feitas_originais, alias, extras) for r in requisitos)
            completos_depois = all(requisito_satisfeito(r, feitas_com_marcadas, alias, extras) for r in requisitos)
            elegivel = completos_depois and not completos_antes     # liberada POR causa da marcação
            if not elegivel:
                materia["faltam"] = [alias.get(r, r) for r in requisitos
                                     if not requisito_satisfeito(r, feitas_com_marcadas, alias, extras)]
                bloqueadas.append(materia)
                continue
        (disponiveis if materia["turmas"] else sem_turma).append(materia)

    ordem = lambda m: (m["categoria"] != "obrigatoria", m["periodo"] or 99, m["codigo"])
    return {"disponiveis": sorted(disponiveis, key=ordem), "bloqueadas": sorted(bloqueadas, key=ordem),
            "sem_turma": sorted(sem_turma, key=ordem), "cumpridas": feitas_com_marcadas,
            "alertas_por_turma": alertas_por_turma}


def _aulas_como_tuplas(aulas):
    return [(a["dia_numero"], a["inicio_min"], a["fim_min"]) for a in aulas]


def explicar_choque(turma, itens_da_grade, ignorar_codigo=None):
    """
    Se `turma` colide com alguma matéria de `itens_da_grade` (itens no formato do resultado do motor),
    devolve o texto do choque; senão, None. `ignorar_codigo` serve para TROCAR a turma de uma matéria
    que já está na grade (a turma antiga não conta como choque com a nova).
    """
    alvo = {"aulas_lista": _aulas_como_tuplas(turma["aulas"])}
    colidem = [{"codigo": item["codigo"], "aulas_lista": _aulas_como_tuplas(item["aulas"])}
               for item in itens_da_grade
               if item["codigo"] != ignorar_codigo
               and aulas_se_sobrepoem(alvo["aulas_lista"], _aulas_como_tuplas(item["aulas"]))]
    return descrever_choque(alvo, colidem) if colidem else None


def montar_item_da_grade(materia, turma, alerta=None, motivo="Escolha manual"):
    """Item no MESMO formato dos itens de resultado["grade"], para a interface tratar tudo igual."""
    if materia["destrava"]:
        motivo += f' · destrava {materia["destrava"]}'
    return {
        "codigo": materia["codigo"], "nome": materia["nome"], "tipo": materia["tipo"], "categoria": materia["categoria"],
        "creditos": materia["creditos"], "periodo": materia["periodo"], "turma_id": turma["id"],
        "docentes": turma["docentes"], "situacao_da_turma": turma["situacao"],
        "aulas": [{k: a[k] for k in ("dia", "dia_numero", "inicio", "fim", "inicio_min", "fim_min", "sala")} for a in turma["aulas"]],
        "motivo": motivo, "em_curso_no_boa": materia["em_curso_no_boa"], "alerta": alerta,
    }


def montar_grade_da_selecao(selecao, disponibilidade, itens_originais=()):
    """
    Converte a escolha do usuário ({código da matéria: id da turma}) em itens de grade.
    Se a turma escolhida é a mesma que o motor sugeriu, reaproveita o item original (com o motivo do motor).
    Escolhas que deixaram de ser válidas (matéria ou turma que não existe mais) são ignoradas.
    """
    por_codigo = {m["codigo"]: m for m in disponibilidade["disponiveis"]}
    originais = {g["codigo"]: g for g in itens_originais}
    grade = []
    for codigo, id_da_turma in selecao.items():
        materia = por_codigo.get(codigo)
        if materia is None:
            continue
        original = originais.get(codigo)
        if original and original["turma_id"] == id_da_turma:
            grade.append(original)
            continue
        turma = next((t for t in materia["turmas"] if t["id"] == id_da_turma), None)
        if turma is not None:
            grade.append(montar_item_da_grade(materia, turma, disponibilidade["alertas_por_turma"].get(id_da_turma)))
    grade.sort(key=lambda g: (g["categoria"] != "obrigatoria", g["periodo"] or 99, g["codigo"]))
    return grade


# ========================================================================================
# PARTE 3: linha de comando
# ========================================================================================
def imprimir_grade(resultado):
    parametros = resultado["_meta"]["parametros"]
    print(f'Grade para {resultado["_meta"]["periodo_das_ofertas"]} | {len(resultado["grade"])} matérias | '
          f'{resultado["creditos_total"]:g} de {parametros["limite_de_creditos"]} créditos | '
          f'prioridade: {parametros["prioridade"]} | marcadas como cumpridas: {parametros["cursando_como_cumpridas"] or "nenhuma"}')
    for g in resultado["grade"]:
        alerta = f'   [!] {g["alerta"]}' if g["alerta"] else ""
        print(f'  {g["codigo"]:7} {g["nome"][:32]:32} {g["tipo"]:12} {g["creditos"]:g} cr | {formatar_horarios(g["aulas"])} | {g["motivo"]}{alerta}')

    faixas = sorted({(a["inicio_min"], a["fim_min"], a["inicio"], a["fim"]) for g in resultado["grade"] for a in g["aulas"]})
    if faixas:
        print("\n  " + "faixa".ljust(13) + "".join(d.ljust(9) for d in DIAS_DA_SEMANA[:6]))
        for inicio_min, fim_min, inicio, fim in faixas:
            linha = f"{inicio}-{fim}".ljust(13)
            for numero in range(6):
                codigos = [g["codigo"] for g in resultado["grade"] for a in g["aulas"]
                           if a["dia_numero"] == numero and (a["inicio_min"], a["fim_min"]) == (inicio_min, fim_min)]
                linha += (codigos[0] if codigos else "·").ljust(9)
            print("  " + linha)

    if resultado["nao_incluidas"]:
        print("\n  Ficaram de fora:")
        for n in resultado["nao_incluidas"][:12]:
            print(f'    {n["codigo"]:7} {n["nome"][:30]:30} {n["tipo"]:12} {n["motivo"]}')
        if len(resultado["nao_incluidas"]) > 12:
            print(f'    ... e mais {len(resultado["nao_incluidas"]) - 12}')
    for s in resultado["sem_horario_fixo"]:
        print(f'  Sem horário: {s["codigo"]} {s["nome"]} ({s["motivo"]})')
    for aviso in resultado["avisos"]:
        print(f'  AVISO {aviso["tipo"]}: {aviso["detalhe"]}')
    estatisticas = resultado["estatisticas"]
    print(f'\n  {estatisticas["candidatas"]} matérias candidatas, {estatisticas["nos_visitados"]} combinações examinadas '
          f'({"busca completa" if estatisticas["busca_completa"] else "busca interrompida"})')


def main():
    analisador = argparse.ArgumentParser(description="Gera a melhor grade a partir do BOA, do currículo e das ofertas.")
    analisador.add_argument("--boa", required=True, help="JSON do extrator_boa.py")
    analisador.add_argument("--curriculo", required=True, help="JSON do currículo")
    analisador.add_argument("--ofertas", required=True, help="JSON do extrator_ofertas.py")
    analisador.add_argument("--limite", type=float, default=24, help="limite de créditos no período (padrão 24)")
    analisador.add_argument("--cursando-cumpridas", default="", help="códigos 'Cursando' a tratar como cumpridos, separados por vírgula, ou 'todas'")
    analisador.add_argument("--sem-optativas", action="store_true", help="não incluir optativas")
    analisador.add_argument("--prioridade", default="equilibrado", choices=list(PESOS_DA_PRIORIDADE))
    analisador.add_argument("--area-de-interesse", help="nome da área de interesse definida no currículo")
    analisador.add_argument("--credito-extra-optativas", type=float, default=CREDITO_EXTRA_PADRAO_DE_OPTATIVAS,
                            help="folga de créditos de optativas acima do que falta (padrão 3)")
    analisador.add_argument("--saida", default="grade.json", help="JSON de saída (padrão: grade.json)")
    argumentos = analisador.parse_args()

    entradas = []
    for caminho in (argumentos.boa, argumentos.curriculo, argumentos.ofertas):
        with open(caminho, encoding="utf-8") as arquivo:
            entradas.append(json.load(arquivo))
    marcadas = "todas" if argumentos.cursando_cumpridas.strip().lower() == "todas" else \
        [c.strip().upper() for c in argumentos.cursando_cumpridas.split(",") if c.strip()]
    try:
        resultado = gerar_grade(*entradas, limite_de_creditos=argumentos.limite, cursando_como_cumpridas=marcadas,
                                incluir_optativas=not argumentos.sem_optativas, prioridade=argumentos.prioridade,
                                credito_extra_de_optativas=argumentos.credito_extra_optativas,
                                area_de_interesse=argumentos.area_de_interesse)
    except ErroDoMotor as erro:
        sys.exit(f"ERRO: {erro}")
    with open(argumentos.saida, "w", encoding="utf-8") as arquivo:
        json.dump(resultado, arquivo, ensure_ascii=False, indent=2)
    imprimir_grade(resultado)
    print(f"JSON salvo em: {argumentos.saida}")


if __name__ == "__main__":
    main()
