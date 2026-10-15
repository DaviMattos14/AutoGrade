# -*- coding: utf-8 -*-
"""
app.py: Planejador de Grade (versão funcional beta)

Como executar:
    pip install -r requirements.txt
    streamlit run app.py

Arquivos que precisam estar na mesma pasta:
    extrator_boa.py                  lê o BOA em PDF
    motor_grade.py                   escolhe a melhor grade
    curriculo_<curso>_<versão>.json  ex.: curriculo_85783_2022-2.json
    ofertas_<período>.json           ex.: ofertas_2026-2.json

Privacidade: o PDF é lido na memória e nunca é gravado em disco. O extrator não guarda nome,
matrícula nem notas, e o app só mantém na sessão as matérias cumpridas e pendentes.
"""

import csv
import io
import json
from datetime import datetime
from pathlib import Path

import streamlit as st

from extrator_boa import ErroDeBOA, extrair_boa
from motor_grade import (CREDITO_EXTRA_PADRAO_DE_OPTATIVAS, ROTULO_DA_CATEGORIA, ErroDoMotor,
                         calcular_efeito_da_marcacao, gerar_grade)

PASTA_DO_APP = Path(__file__).parent
NOMES_DAS_ETAPAS = ["Enviar BOA", "Conferir", "Parâmetros", "Resultado"]
DIAS_DA_SEMANA = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB"]
PRIORIDADES = {"Períodos mais baixos": "periodos", "Equilibrado": "equilibrado", "Pré-requisitos": "prerequisitos"}
ESCOLHAS_INICIAIS = {"marcadas": [], "limite": 24, "incluir_optativas": True, "prioridade": "equilibrado",
                     "folga": CREDITO_EXTRA_PADRAO_DE_OPTATIVAS}

st.set_page_config(page_title="Planejador de Grade", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
.etapa{display:flex;align-items:center;gap:.65rem;padding:.4rem 0;color:#6b7280;font-size:.95rem}
.etapa .bolinha{width:1.65rem;height:1.65rem;border-radius:50%;border:1.5px solid #cbd5e1;display:flex;
  align-items:center;justify-content:center;font-size:.8rem;background:#fff}
.etapa.atual{color:#111827;font-weight:600}
.etapa.atual .bolinha{background:#ff4b4b;border-color:#ff4b4b;color:#fff}
.etapa.feita .bolinha{background:#e8f5e9;border-color:#81c784;color:#2e7d32}
table.grade{border-collapse:separate;border-spacing:6px;width:100%;table-layout:fixed}
table.grade td,table.grade th{border:none !important;padding:0 !important;background:transparent !important}
table.grade th{font-weight:600;font-size:.85rem;color:#475569;padding:.3rem !important;text-align:left}
table.grade td.hora{width:96px;font-size:.78rem;color:#64748b;text-align:right;padding-right:.5rem !important}
.aula{border-radius:8px;padding:.45rem .55rem;font-size:.76rem;line-height:1.3;border:1px solid;height:104px;overflow:hidden}
.aula b{font-size:.82rem}
.aula.obrigatoria{background:#e7f1ff;border-color:#8bb8f8;color:#0b3d91}
.aula.optativa{background:#e8f6ec;border-color:#86cf9c;color:#14532d}
.vazio{height:104px;border-radius:8px;background:#f8fafc;border:1px dashed #e2e8f0}
.legenda span{display:inline-block;width:.8rem;height:.8rem;border-radius:3px;margin:0 .35rem 0 .9rem;border:1px solid}
</style>""", unsafe_allow_html=True)


# ======================================================================================
# Arquivos de dados
# ======================================================================================
@st.cache_data
def carregar_json(caminho, modificado_em):
    """Lê um JSON da pasta do app. O 'modificado_em' faz o cache se renovar quando o arquivo muda."""
    with open(caminho, encoding="utf-8") as arquivo:
        return json.load(arquivo)


def ler_json_da_pasta(caminho):
    return carregar_json(str(caminho), Path(caminho).stat().st_mtime)


def listar_ofertas():
    """{período: caminho} para cada ofertas_*.json da pasta, em ordem crescente de período."""
    ofertas = {}
    for caminho in sorted(PASTA_DO_APP.glob("ofertas_*.json")):
        ofertas[ler_json_da_pasta(caminho)["_meta"]["periodo"]] = caminho
    return dict(sorted(ofertas.items()))


def achar_curriculo(curso, versao):
    caminho = PASTA_DO_APP / f"curriculo_{curso}_{versao.replace('/', '-')}.json"
    return caminho if caminho.exists() else None


def formatar_data(iso):
    return datetime.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "data desconhecida"


# ======================================================================================
# Estado da sessão
# ======================================================================================
def iniciar_estado():
    st.session_state.setdefault("etapa", 1)
    st.session_state.setdefault("boa", None)
    st.session_state.setdefault("curriculo", None)
    st.session_state.setdefault("periodo", None)
    st.session_state.setdefault("escolhas", dict(ESCOLHAS_INICIAIS))


def ir_para(etapa):
    st.session_state.etapa = etapa


def recomecar():
    for chave in list(st.session_state.keys()):
        del st.session_state[chave]


def ofertas_do_periodo():
    return ler_json_da_pasta(listar_ofertas()[st.session_state.periodo])


def executar_motor():
    escolhas = st.session_state.escolhas
    return gerar_grade(st.session_state.boa, st.session_state.curriculo, ofertas_do_periodo(),
                       limite_de_creditos=escolhas["limite"], cursando_como_cumpridas=escolhas["marcadas"],
                       incluir_optativas=escolhas["incluir_optativas"], prioridade=escolhas["prioridade"],
                       credito_extra_de_optativas=escolhas["folga"])


def barra_lateral():
    etapa_atual = st.session_state.etapa
    with st.sidebar:
        st.markdown("### Planejador de Grade")
        boa = st.session_state.boa
        st.caption(boa["curso"]["nome"] if boa else "UFRJ")
        html = ""
        for posicao, nome in enumerate(NOMES_DAS_ETAPAS, start=1):
            classe = "atual" if posicao == etapa_atual else ("feita" if posicao < etapa_atual else "")
            html += f'<div class="etapa {classe}"><span class="bolinha">{"✓" if posicao < etapa_atual else posicao}</span>{nome}</div>'
        st.markdown(html, unsafe_allow_html=True)
        st.divider()
        if etapa_atual > 1:
            st.button("Recomeçar", on_click=recomecar, icon=":material/restart_alt:", width="stretch")
        st.caption("Seu PDF é lido na memória e não é salvo. Nome, matrícula e notas não são extraídos.")


# ======================================================================================
# Etapa 1: envio do BOA
# ======================================================================================
def ler_boa(arquivo, periodo):
    conteudo = arquivo.getvalue()   # fica só na memória; nada é gravado em disco
    try:
        with st.spinner("Lendo o BOA..."):
            lido = extrair_boa(io.BytesIO(conteudo))
            caminho_curriculo = achar_curriculo(lido["curso"]["codigo"], lido["versao_curricular"])
            if caminho_curriculo is None:
                st.error(f'Ainda não tenho o currículo do curso {lido["curso"]["codigo"]} '
                         f'({lido["curso"]["nome"]}), versão {lido["versao_curricular"]}. '
                         "Esta versão do planejador só funciona com currículos que estejam na pasta do app.")
                return
            boa = extrair_boa(io.BytesIO(conteudo), str(caminho_curriculo))
    except ErroDeBOA as erro:
        st.error(str(erro))
        return
    except Exception:  # PDF corrompido, protegido por senha etc.
        st.error("Não consegui abrir este PDF. Confira se é o BOA original, baixado do sistema da UFRJ.")
        return
    st.session_state.update(boa=boa, curriculo=ler_json_da_pasta(caminho_curriculo), periodo=periodo,
                            etapa=2, escolhas=dict(ESCOLHAS_INICIAIS))
    st.rerun()


def tela_envio():
    st.title("Planejador de Grade")
    st.markdown("Envie o seu BOA e receba uma grade sem choques de horário para o próximo período.")
    ofertas = listar_ofertas()
    if not ofertas:
        st.error("Não encontrei nenhum arquivo ofertas_<período>.json na pasta do app.")
        st.stop()

    esquerda, direita = st.columns([3, 2], gap="large")
    with esquerda:
        with st.container(border=True):
            st.subheader("1. Envie o seu BOA")
            arquivo = st.file_uploader("Boletim de Orientação Acadêmica (PDF)", type=["pdf"])
            periodos = list(ofertas)
            periodo = st.selectbox("Período das ofertas", periodos, index=len(periodos) - 1)
            if st.button("Ler BOA", type="primary", disabled=arquivo is None, icon=":material/description:"):
                ler_boa(arquivo, periodo)
        if st.session_state.boa:
            st.info("Já existe um BOA lido nesta sessão.", icon=":material/info:")
            st.button("Continuar com o BOA já lido", on_click=ir_para, args=(2,))
    with direita:
        with st.container(border=True):
            st.subheader("Como funciona")
            st.markdown("1. O sistema lê o PDF e identifica o que falta cursar.\n"
                        "2. Você confere o resultado e marca as matérias que está cursando.\n"
                        "3. A grade é montada priorizando períodos mais baixos e pré-requisitos.")
        st.info("**Privacidade.** O PDF é usado só para extrair as matérias. Nome, matrícula e notas não são "
                "extraídos, e o arquivo não é salvo.", icon=":material/lock:")


# ======================================================================================
# Etapa 2: conferência
# ======================================================================================
def tela_conferencia():
    boa, escolhas = st.session_state.boa, st.session_state.escolhas
    st.title("Confira o que foi lido")
    st.success(f'BOA lido: **{boa["curso"]["nome"]} ({boa["curso"]["codigo"]})**, currículo **{boa["versao_curricular"]}**, '
               f'emitido em {formatar_data(boa["emitido_em"])}.', icon=":material/check_circle:")

    resumo = boa.get("resumo", {})
    quadros = [("Obrigatórias (créditos)", "obrigatorias", "creditos"), ("Optativas (créditos)", "escolha_condicionada", "creditos"),
               ("Humanidades (créditos)", "escolha_restrita_humanidades", "creditos"), ("Extensão (horas)", "extensao", "horas")]
    colunas = st.columns(len(quadros))
    for coluna, (rotulo, chave, unidade) in zip(colunas, quadros):
        if chave in resumo:
            coluna.metric(rotulo, f'{resumo[chave][f"cumpridos_{unidade}"]:g} / {resumo[chave][f"total_{unidade}"]:g}')

    st.subheader("Matérias em curso")
    em_curso = sorted((p for p in boa["pendentes"] if p["status"] == "Cursando"), key=lambda p: (p["secao"], p["codigo"]))
    if em_curso:
        st.caption("Por padrão, elas contam como **não cumpridas**. Marque as que o sistema deve considerar concluídas.")
        ofertas = ofertas_do_periodo()
        with st.container(border=True):
            for materia in em_curso:
                esquerda, direita = st.columns([3, 2], vertical_alignment="center")
                periodo = f' · período {materia["periodo"]}' if materia["periodo"] else ""
                esquerda.checkbox(f'**{materia["codigo"]}** {materia["nome"]}  \n{ROTULO_DA_CATEGORIA[materia["secao"]]}{periodo}',
                                  value=materia["codigo"] in escolhas["marcadas"], key=f'marca_{materia["codigo"]}')
                efeito = calcular_efeito_da_marcacao(boa, st.session_state.curriculo, ofertas, materia["codigo"])
                if efeito["liberadas"]:
                    direita.caption(f'Se marcada, libera **{len(efeito["liberadas"])} matérias** '
                                    f'({len(efeito["ofertadas"])} ofertada neste período).')
                else:
                    direita.caption("Não libera outras matérias.")
        escolhas["marcadas"] = [m["codigo"] for m in em_curso if st.session_state.get(f'marca_{m["codigo"]}')]
    else:
        st.info("Nenhuma matéria está como \"Cursando\" neste BOA.")

    with st.expander("Obrigatórias pendentes lidas do BOA"):
        st.dataframe([{"Código": p["codigo"], "Matéria": p["nome"], "Créd.": f'{p["creditos"]:g}', "Período": p["periodo"],
                       "Status no BOA": p["status"]} for p in sorted(boa["pendentes"], key=lambda p: (p["periodo"] or 99, p["codigo"]))
                      if p["secao"] == "obrigatoria"], hide_index=True, width="stretch")
    with st.expander("Detalhes da leitura"):
        conferencia = boa["conferencias"]["resumo_do_boa"]
        st.write("Créditos conferidos com o Resumo do próprio BOA: " +
                 ", ".join(f'{nome} {"✓" if ok else "✗"}' for nome, ok in conferencia.items()))
        for aviso in boa["avisos"]:
            st.caption(f'{aviso["tipo"]}: {aviso["detalhe"]}')

    esquerda, direita, _ = st.columns([1, 1, 4])
    esquerda.button("Voltar", on_click=ir_para, args=(1,), width="stretch")
    direita.button("Continuar", on_click=ir_para, args=(3,), type="primary", width="stretch")


# ======================================================================================
# Etapa 3: parâmetros
# ======================================================================================
def tela_parametros():
    escolhas = st.session_state.escolhas
    st.title("Parâmetros da grade")
    esquerda, direita = st.columns([3, 2], gap="large")
    with esquerda:
        with st.container(border=True):
            escolhas["limite"] = st.slider("Limite de créditos no período", 8, 32, escolhas["limite"],
                                           help="O sistema não passa desse total.")
            escolhas["incluir_optativas"] = st.toggle("Incluir optativas", value=escolhas["incluir_optativas"])
            st.caption("Entram só até o que ainda falta cumprir, com uma folga para fechar matérias inteiras.")
            rotulo_atual = next(r for r, v in PRIORIDADES.items() if v == escolhas["prioridade"])
            escolhas["prioridade"] = PRIORIDADES[st.select_slider("O que priorizar", options=list(PRIORIDADES), value=rotulo_atual)]
            with st.expander("Avançado"):
                escolhas["folga"] = st.number_input("Folga de créditos de optativas", 0, 8, int(escolhas["folga"]),
                                                    help="Quantos créditos além do que falta o sistema pode incluir.")
    with direita:
        with st.container(border=True):
            st.subheader("Resumo")
            try:
                previa = executar_motor()
                st.metric("Matérias candidatas", previa["estatisticas"]["candidatas"],
                          help="Pendentes liberadas e com turma confirmada no período.")
                orcamento = previa["_meta"]["orcamento_de_optativas"].get("optativa_condicionada")
                if escolhas["incluir_optativas"] and orcamento:
                    st.caption(f"Optativas: até {orcamento:g} créditos neste período.")
                st.caption(f'Marcadas como cumpridas: {", ".join(escolhas["marcadas"]) or "nenhuma"}.')
            except ErroDoMotor as erro:
                st.error(str(erro))
    esquerda, direita, _ = st.columns([1, 1.4, 4])
    esquerda.button("Voltar", on_click=ir_para, args=(2,), width="stretch")
    direita.button("Gerar grade", on_click=ir_para, args=(4,), type="primary", width="stretch", icon=":material/calendar_month:")


# ======================================================================================
# Etapa 4: resultado
# ======================================================================================
def desenhar_grade_semanal(grade):
    faixas = sorted({(a["inicio_min"], a["fim_min"], a["inicio"], a["fim"]) for g in grade for a in g["aulas"]})
    quantidade_de_dias = 6 if any(a["dia_numero"] == 5 for g in grade for a in g["aulas"]) else 5
    celulas = {}
    for g in grade:
        classe = "obrigatoria" if g["categoria"] == "obrigatoria" else "optativa"
        for a in g["aulas"]:
            alerta = " &#9888;" if g["alerta"] else ""
            celulas[((a["inicio_min"], a["fim_min"]), a["dia_numero"])] = (
                f'<div class="aula {classe}"><b>{g["codigo"]}</b>{alerta}<br>{g["nome"]}<br>{a["sala"] or ""}</div>')
    html = "<tr><th></th>" + "".join(f"<th>{dia}</th>" for dia in DIAS_DA_SEMANA[:quantidade_de_dias]) + "</tr>"
    for inicio_min, fim_min, inicio, fim in faixas:
        html += f'<tr><td class="hora">{inicio}–{fim}</td>'
        for dia_numero in range(quantidade_de_dias):
            html += f'<td>{celulas.get(((inicio_min, fim_min), dia_numero), "<div class=vazio></div>")}</td>'
        html += "</tr>"
    st.markdown(f'<table class="grade">{html}</table>', unsafe_allow_html=True)
    st.markdown('<div class="legenda"><span style="background:#e7f1ff;border-color:#8bb8f8"></span>Obrigatória'
                '<span style="background:#e8f6ec;border-color:#86cf9c"></span>Optativa</div>', unsafe_allow_html=True)


def grade_em_csv(grade):
    saida = io.StringIO()
    escritor = csv.writer(saida)
    escritor.writerow(["Código", "Matéria", "Tipo", "Créditos", "Horários", "Docente", "Salas", "Motivo"])
    for g in grade:
        escritor.writerow([g["codigo"], g["nome"], g["tipo"], f'{g["creditos"]:g}',
                           " · ".join(f'{a["dia"]} {a["inicio"]}-{a["fim"]}' for a in g["aulas"]),
                           ", ".join(g["docentes"]), ", ".join(sorted({a["sala"] for a in g["aulas"] if a["sala"]})), g["motivo"]])
    return saida.getvalue().encode("utf-8-sig")   # com BOM, para o Excel abrir os acentos certo


def tela_resultado():
    escolhas = st.session_state.escolhas
    try:
        resultado = executar_motor()
    except ErroDoMotor as erro:
        st.error(str(erro))
        st.button("Voltar", on_click=ir_para, args=(3,))
        return
    grade = resultado["grade"]
    st.title(f'Sua grade para {resultado["_meta"]["periodo_das_ofertas"]}')
    aviso_da_planilha = resultado["_meta"].get("aviso_da_planilha") or ""
    marcadas = escolhas["marcadas"]
    st.caption(("A planilha de ofertas traz informações provisórias, sujeitas a mudanças. " if "provis" in aviso_da_planilha.lower() else "") +
               (f'Considerando como cumpridas: {", ".join(marcadas)}.' if marcadas else ""))

    for fora in resultado["nao_incluidas"]:
        if fora["tipo"] == "Obrigatória" and fora["motivo"].startswith("choque"):
            st.warning(f'**{fora["nome"]} ({fora["codigo"]})** ficou de fora: {fora["motivo"]}. O sistema prioriza matérias de '
                       "período mais baixo e que destravam mais matérias. Se alguma matéria em curso já está concluída, "
                       "volte a *Conferir* e marque-a.", icon=":material/warning:")

    colunas = st.columns(3)
    colunas[0].metric("Créditos", f'{resultado["creditos_total"]:g} de {escolhas["limite"]:g}')
    colunas[1].metric("Matérias", len(grade))
    colunas[2].metric("Obrigatórias", sum(1 for g in grade if g["categoria"] == "obrigatoria"))

    if grade:
        desenhar_grade_semanal(grade)
        st.subheader("Turmas escolhidas")
        linhas = [{"Código": g["codigo"], "Matéria": g["nome"], "Créd.": f'{g["creditos"]:g}',
                   "Horários": " · ".join(f'{a["dia"]} {a["inicio"]}–{a["fim"]}' for a in g["aulas"]),
                   "Docente": ", ".join(g["docentes"]) or "A definir", "Motivo da escolha": g["motivo"]} for g in grade]
        st.dataframe(linhas, hide_index=True, width="stretch")
        for g in grade:
            if g["alerta"]:
                st.caption(f'⚠ {g["codigo"]}: {g["alerta"]}.')
    else:
        st.warning("Nenhuma matéria coube com estes parâmetros. Veja abaixo o motivo de cada uma e ajuste o limite de créditos.")

    for aviso in resultado["avisos"]:
        if aviso["tipo"] == "sem_oferta_de_optativas":
            st.info(aviso["detalhe"][0].upper() + aviso["detalhe"][1:] + ".", icon=":material/info:")
    if resultado["sem_horario_fixo"]:
        codigos = " e ".join(s["codigo"] for s in resultado["sem_horario_fixo"])
        st.info(f"**{codigos}** não têm horário fixo na planilha de ofertas e não entram na grade.", icon=":material/info:")

    with st.expander(f'Ficaram de fora ({len(resultado["nao_incluidas"])})', expanded=not grade):
        st.dataframe([{"Código": n["codigo"], "Matéria": n["nome"], "Tipo": n["tipo"], "Motivo": n["motivo"]}
                      for n in sorted(resultado["nao_incluidas"], key=lambda n: (n["tipo"] != "Obrigatória", n["codigo"]))],
                     hide_index=True, width="stretch", column_config={"Motivo": st.column_config.TextColumn(width=420)})

    esquerda, centro, direita, _ = st.columns([1, 1.2, 1.2, 3])
    esquerda.button("Voltar", on_click=ir_para, args=(3,), width="stretch")
    centro.download_button("Baixar CSV", grade_em_csv(grade), file_name="grade.csv", mime="text/csv",
                           icon=":material/download:", width="stretch")
    direita.download_button("Baixar JSON", json.dumps(resultado, ensure_ascii=False, indent=2).encode("utf-8"),
                            file_name="grade.json", mime="application/json", icon=":material/data_object:", width="stretch")


# ======================================================================================
# Roteador
# ======================================================================================
iniciar_estado()
if st.session_state.etapa > 1 and st.session_state.boa is None:
    st.session_state.etapa = 1
barra_lateral()
{1: tela_envio, 2: tela_conferencia, 3: tela_parametros, 4: tela_resultado}[st.session_state.etapa]()
