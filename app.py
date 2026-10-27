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
import textwrap
from datetime import datetime
from pathlib import Path

import streamlit as st
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from extrator_boa import ErroDeBOA, extrair_boa
from motor_grade import (CREDITO_EXTRA_PADRAO_DE_OPTATIVAS, ROTULO_DA_CATEGORIA, ErroDoMotor,
                         calcular_efeito_da_marcacao, explicar_choque, formatar_horarios, gerar_grade,
                         gerar_versoes_da_grade, listar_materias_disponiveis, montar_grade_da_selecao)

PASTA_DO_APP = Path(__file__).parent
QUANTIDADE_DE_VERSOES = 3
NOMES_DAS_ETAPAS = ["Enviar BOA", "Conferir", "Parâmetros", "Resultado"]
DIAS_DA_SEMANA = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB"]
PRIORIDADES = {"Períodos mais baixos": "periodos", "Equilibrado": "equilibrado", "Pré-requisitos": "prerequisitos"}
ESCOLHAS_INICIAIS = {"marcadas": [], "limite": 24, "incluir_optativas": True, "prioridade": "equilibrado",
                     "folga": CREDITO_EXTRA_PADRAO_DE_OPTATIVAS, "area_de_interesse": None}

st.set_page_config(page_title="Planejador de Grade", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
/* Cores que funcionam nos temas claro e escuro: o texto herda a cor do tema do Streamlit e os fundos
   são tons translúcidos (rgba), que se misturam com o fundo da página, seja ele branco ou escuro.
   rgba(128,128,128,x) é um cinza neutro: aparece bem sobre claro e sobre escuro. */
.etapa{display:flex;align-items:center;gap:.65rem;padding:.4rem 0;opacity:.65;font-size:.95rem}
.etapa .bolinha{width:1.65rem;height:1.65rem;border-radius:50%;border:1.5px solid rgba(128,128,128,.55);display:flex;
  align-items:center;justify-content:center;font-size:.8rem;background:transparent}
.etapa.atual{opacity:1;font-weight:600}
.etapa.atual .bolinha{background:#ff4b4b;border-color:#ff4b4b;color:#fff}
.etapa.feita{opacity:.9}
.etapa.feita .bolinha{background:rgba(34,197,94,.18);border-color:rgba(34,197,94,.65);color:#16a34a}
table.grade{border-collapse:separate;border-spacing:6px;width:100%;table-layout:fixed}
table.grade td,table.grade th{border:none !important;padding:0 !important;background:transparent !important}
table.grade th{font-weight:600;font-size:.85rem;opacity:.75;padding:.3rem !important;text-align:left}
table.grade td.hora{width:96px;font-size:.78rem;opacity:.65;text-align:right;padding-right:.5rem !important}
.aula{border-radius:8px;padding:.45rem .55rem;font-size:.76rem;line-height:1.3;border:1px solid;height:104px;overflow:hidden;color:inherit}
.aula b{font-size:.82rem}
.aula.obrigatoria,.legenda span.obrigatoria{background:rgba(59,130,246,.18);border-color:rgba(59,130,246,.6)}
.aula.optativa,.legenda span.optativa{background:rgba(34,197,94,.18);border-color:rgba(34,197,94,.6)}
.vazio{height:104px;border-radius:8px;background:rgba(128,128,128,.07);border:1px dashed rgba(128,128,128,.35)}
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
    caminho = PASTA_DO_APP / 'grades_curricular' / f"curriculo_{curso}_{versao.replace('/', '-')}.json"
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
    st.session_state.escolhas.setdefault("area_de_interesse", None)
    # Edição manual da grade: {código da matéria: id da turma}. None = ainda não montada para esta geração.
    st.session_state.setdefault("selecao", None)
    st.session_state.setdefault("editada", False)   # True depois que o usuário muda algo à mão
    st.session_state.setdefault("versao", 1)        # qual das versões do motor (1, 2 ou 3) está na tela
    st.session_state.setdefault("versoes_cache", None)   # (assinatura dos parâmetros, lista de versões)


def ir_para(etapa):
    st.session_state.etapa = etapa


def iniciar_resultado():
    """Botão "Gerar grade": começa de novo a partir da sugestão automática (descarta edições antigas)."""
    st.session_state.update(selecao=None, editada=False, versao=1, versoes_cache=None, etapa=4)


def escolher_versao(numero):
    """Botões 1, 2, 3: troca a versão da grade. Edições feitas à mão na versão anterior são descartadas."""
    st.session_state.update(versao=numero, selecao=None, editada=False)


def escolher_turma(codigo, id_da_turma):
    """Adiciona a matéria à grade com essa turma, ou troca a turma se a matéria já estava na grade."""
    st.session_state.selecao[codigo] = id_da_turma
    st.session_state.editada = True


def remover_materia(codigo):
    st.session_state.selecao.pop(codigo, None)
    st.session_state.editada = True


def restaurar_grade_automatica():
    st.session_state.update(selecao=None, editada=False)   # será refeita a partir do motor


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
                       credito_extra_de_optativas=escolhas["folga"],
                       area_de_interesse=escolhas["area_de_interesse"] if escolhas["incluir_optativas"] else None)


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
                            etapa=2, escolhas=dict(ESCOLHAS_INICIAIS), selecao=None, editada=False,
                            versao=1, versoes_cache=None)
    st.rerun()


def tela_envio():
    st.title("Planejador de Grade")
    st.markdown("Envie o seu BOA e receba uma grade sem choques de horário para o próximo período.")
    ofertas = listar_ofertas()
    if not ofertas:
        st.error("Não encontrei nenhum arquivo ofertas_<período>.json na pasta do app.")
        st.stop()
    # Usa automaticamente o período mais recente disponível na base de ofertas.
    periodo = next(reversed(ofertas))

    esquerda, direita = st.columns([3, 2], gap="large")
    with esquerda:
        with st.container(border=True):
            st.subheader("1. Envie o seu BOA")
            arquivo = st.file_uploader("Boletim de Orientação Acadêmica (PDF)", type=["pdf"])
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
            areas = [None, *st.session_state.curriculo.get("areas_de_interesse", {})]
            area_atual = escolhas["area_de_interesse"]
            escolhas["area_de_interesse"] = st.selectbox(
                "Área de interesse", areas, index=areas.index(area_atual) if area_atual in areas else 0,
                format_func=lambda area: area or "Sem preferência", disabled=not escolhas["incluir_optativas"],
                help="Prioriza as optativas da área escolhida segundo o manual do aluno. Outras áreas continuam elegíveis.")
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
    direita.button("Gerar grade", on_click=iniciar_resultado, type="primary", width="stretch", icon=":material/calendar_month:")


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
    st.markdown('<div class="legenda"><span class="obrigatoria"></span>Obrigatória'
                '<span class="optativa"></span>Optativa</div>', unsafe_allow_html=True)


def grade_em_csv(grade):
    saida = io.StringIO()
    escritor = csv.writer(saida)
    escritor.writerow(["Código", "Matéria", "Tipo", "Créditos", "Horários", "Docente", "Salas", "Motivo"])
    for g in grade:
        escritor.writerow([g["codigo"], g["nome"], g["tipo"], f'{g["creditos"]:g}',
                           " · ".join(f'{a["dia"]} {a["inicio"]}-{a["fim"]}' for a in g["aulas"]),
                           ", ".join(g["docentes"]), ", ".join(sorted({a["sala"] for a in g["aulas"] if a["sala"]})), g["motivo"]])
    return saida.getvalue().encode("utf-8-sig")   # com BOM, para o Excel abrir os acentos certo


def grade_em_imagem(resultado, formato):
    """Gera uma representação portátil da grade em PNG ou PDF.

    Layout (de cima para baixo): cabeçalho, grade semanal (dias no topo, faixas de horário à esquerda)
    e tabela de detalhes. A tabela tem altura proporcional ao número de matérias e a grade ocupa o
    espaço que sobra, então as duas áreas nunca se sobrepõem.
    """
    if formato not in ("png", "pdf"):
        raise ValueError("formato deve ser 'png' ou 'pdf'")

    grade = resultado["grade"]
    periodo = resultado["_meta"]["periodo_das_ofertas"]
    figura = Figure(figsize=(14, 9), facecolor="white")
    figura.text(0.04, 0.94, f"Planejador de Grade — {periodo}", fontsize=18, weight="bold", color="#111827")
    figura.text(0.04, 0.905, f'{resultado["_meta"]["curso"]["nome"]} ({resultado["_meta"]["curso"]["codigo"]})',
                fontsize=10, color="#475569")
    figura.text(0.04, 0.875,
                f'Créditos: {resultado["creditos_total"]:g} · Matérias: {len(grade)} · '
                f'Currículo: {resultado["_meta"]["versao_curricular"]}',
                fontsize=10, color="#475569")

    # --- Reserva o espaço da tabela (parte de baixo) e dá o resto para a grade ---------------
    linhas = [[g["codigo"], g["nome"], f'{g["creditos"]:g}',
               " · ".join(f'{a["dia"]} {a["inicio"]}-{a["fim"]}' for a in g["aulas"]),
               ", ".join(g["docentes"]) or "A definir",
               ", ".join(sorted({a["sala"] for a in g["aulas"] if a["sala"]})) or "A definir"]
              for g in grade]
    ALTURA_POR_LINHA_DA_TABELA = 0.032          # fração da altura da figura
    altura_tabela = ALTURA_POR_LINHA_DA_TABELA * (len(linhas) + 1) if linhas else 0   # +1 = cabeçalho
    base_da_grade = 0.04 + altura_tabela + 0.05                 # margem + tabela + respiro
    topo_da_grade = 0.84                                        # logo abaixo do cabeçalho
    # Margem esquerda maior (0.09) para caber os rótulos de horário; topo reservado aos dias da semana.
    eixo = figura.add_axes([0.09, base_da_grade, 0.87, topo_da_grade - base_da_grade - 0.03])
    eixo.set_frame_on(False)       # esconde só a moldura; os rótulos dos eixos continuam visíveis

    # Mostra SEG–SEX sempre; inclui SÁB apenas se alguma aula cair nele.
    dias = ["SEG", "TER", "QUA", "QUI", "SEX"]
    aulas = [a for materia in grade for a in materia["aulas"]]
    if any(a["dia_numero"] == 5 for a in aulas):
        dias.append("SÁB")
    aulas = [a for a in aulas if a["dia_numero"] < len(dias)]
    faixas = sorted({(a["inicio_min"], a["fim_min"], a["inicio"], a["fim"]) for a in aulas})

    if faixas:
        eixo.set_xlim(0, len(dias))
        eixo.set_ylim(len(faixas), 0)      # invertido: o horário mais cedo fica no TOPO
        # Dias da semana no topo
        eixo.set_xticks([i + 0.5 for i in range(len(dias))], dias)
        eixo.tick_params(axis="x", top=True, labeltop=True, bottom=False, labelbottom=False,
                         length=0, pad=8, labelsize=11)
        # Faixas de horário à esquerda
        eixo.set_yticks([i + 0.5 for i in range(len(faixas))],
                        [f"{inicio}\n{fim}" for _, _, inicio, fim in faixas])
        eixo.tick_params(axis="y", length=0, pad=8, labelsize=10)
        for rotulo in eixo.get_xticklabels():
            rotulo.set_fontweight("bold")
        for x in range(len(dias) + 1):
            eixo.axvline(x, color="#cbd5e1", linewidth=0.8)
        for y in range(len(faixas) + 1):
            eixo.axhline(y, color="#cbd5e1", linewidth=0.8)
        indice_faixa = {(inicio, fim): i for i, (inicio, fim, _, _) in enumerate(faixas)}
        largura_do_texto = 30 if len(dias) == 5 else 25      # caracteres por linha dentro de cada célula
        for materia in grade:
            cor = "#dbeafe" if materia["categoria"] == "obrigatoria" else "#dcfce7"
            borda = "#60a5fa" if materia["categoria"] == "obrigatoria" else "#4ade80"
            professores = ", ".join(materia["docentes"]) or "Professor a definir"
            # Quebra manual de linha: o texto do matplotlib não respeita a largura da célula sozinho.
            texto = (f'{materia["codigo"]}\n{textwrap.fill(materia["nome"], largura_do_texto)}\n'
                     f'{textwrap.fill(professores, largura_do_texto)}')
            for aula in materia["aulas"]:
                if aula["dia_numero"] >= len(dias):
                    continue
                linha = indice_faixa[(aula["inicio_min"], aula["fim_min"])]
                eixo.add_patch(Rectangle((aula["dia_numero"], linha), 1, 1,
                                         facecolor=cor, edgecolor=borda, linewidth=1.0))
                eixo.text(aula["dia_numero"] + 0.05, linha + 0.5, texto,
                          ha="left", va="center", fontsize=9, color="#0f172a", clip_on=True)
    else:
        eixo.axis("off")
        eixo.text(0.5, 0.65, "Nenhuma matéria foi incluída na grade.",
                  ha="center", va="center", fontsize=14, color="#64748b", transform=eixo.transAxes)

    if linhas:
        tabela_eixo = figura.add_axes([0.04, 0.04, 0.92, altura_tabela])
        tabela_eixo.axis("off")
        tabela = tabela_eixo.table(cellText=linhas,
                                   colLabels=["Código", "Matéria", "Créd.", "Horários", "Professor", "Sala"],
                                   colWidths=[0.10, 0.27, 0.07, 0.27, 0.19, 0.10],
                                   loc="upper center", cellLoc="left")
        tabela.auto_set_font_size(False)
        tabela.set_fontsize(9)
        for (linha_da_tabela, _), celula in tabela.get_celld().items():
            celula.set_edgecolor("#cbd5e1")
            celula.set_height(1 / (len(linhas) + 1))     # divide a altura reservada igualmente
            if linha_da_tabela == 0:                     # cabeçalho
                celula.set_facecolor("#f1f5f9")
                celula.set_text_props(weight="bold", color="#111827")

    saida = io.BytesIO()
    canvas = FigureCanvasAgg(figura)
    canvas.print_png(saida) if formato == "png" else figura.savefig(saida, format="pdf")
    return saida.getvalue()


def versoes_da_grade():
    """
    Até 3 versões da grade geradas pelo motor. O resultado fica guardado na sessão e só é refeito quando
    algum parâmetro muda (o motor roda 3 buscas, e a tela é redesenhada a cada clique).
    """
    escolhas = st.session_state.escolhas
    assinatura = (st.session_state.periodo, tuple(escolhas["marcadas"]), escolhas["limite"],
                  escolhas["incluir_optativas"], escolhas["prioridade"], escolhas["folga"], escolhas["area_de_interesse"])
    guardado = st.session_state.versoes_cache
    if guardado is None or guardado[0] != assinatura:
        versoes = gerar_versoes_da_grade(
            st.session_state.boa, st.session_state.curriculo, ofertas_do_periodo(), QUANTIDADE_DE_VERSOES,
            limite_de_creditos=escolhas["limite"], cursando_como_cumpridas=escolhas["marcadas"],
            incluir_optativas=escolhas["incluir_optativas"], prioridade=escolhas["prioridade"],
            credito_extra_de_optativas=escolhas["folga"],
            area_de_interesse=escolhas["area_de_interesse"] if escolhas["incluir_optativas"] else None)
        st.session_state.versoes_cache = guardado = (assinatura, versoes)
    return guardado[1]


def descrever_versao(numero, versoes):
    """Frase que explica o que muda na versão `numero` em relação à versão 1."""
    if numero == 1:
        return "A grade que o motor considera a melhor, pelas suas prioridades."
    base = {g["codigo"]: g for g in versoes[0]["grade"]}
    atual = {g["codigo"]: g for g in versoes[numero - 1]["grade"]}
    diferencas = versoes[numero - 1]["_meta"]["diferencas_da_versao_1"]

    def nome(codigo, grade):
        g = grade[codigo]
        periodo = f' (período {g["periodo"]})' if g["periodo"] else ""
        return f'**{codigo}** {g["nome"]}{periodo}'
    partes = []
    if diferencas["entram"]:
        partes.append("entra " + ", ".join(nome(c, atual) for c in diferencas["entram"]))
    if diferencas["saem"]:
        partes.append("sai " + ", ".join(nome(c, base) for c in diferencas["saem"]))
    return "Em relação à versão 1: " + "; ".join(partes) + "."


def materias_disponiveis():
    """Matérias que o aluno pode cursar no período (pendentes liberadas, com turma e horário completo)."""
    return listar_materias_disponiveis(st.session_state.boa, st.session_state.curriculo, ofertas_do_periodo(),
                                       st.session_state.escolhas["marcadas"])


def resultado_ativo(resultado_do_motor, disponibilidade):
    """
    O resultado que a tela mostra e exporta: a sugestão do motor, ou a grade editada pelo usuário.
    Na versão editada, 'nao_incluidas' e 'pontuacao' deixam de valer (eram da sugestão automática).
    """
    if not st.session_state.editada:
        return resultado_do_motor
    grade = montar_grade_da_selecao(st.session_state.selecao, disponibilidade, resultado_do_motor["grade"])
    ativo = dict(resultado_do_motor)
    ativo.update(grade=grade, creditos_total=sum(g["creditos"] for g in grade), nao_incluidas=[], pontuacao=None,
                 _meta=dict(resultado_do_motor["_meta"], editada_manualmente=True, versao_base=st.session_state.versao))
    return ativo


# --------------------------------------------------------------------------------------
# Aba 1: minha grade
# --------------------------------------------------------------------------------------
def aba_minha_grade(resultado, escolhas, versoes):
    grade = resultado["grade"]
    editada = st.session_state.editada
    aviso_da_planilha = resultado["_meta"].get("aviso_da_planilha") or ""
    marcadas = escolhas["marcadas"]
    st.caption(("A planilha de ofertas traz informações provisórias, sujeitas a mudanças. " if "provis" in aviso_da_planilha.lower() else "") +
               (f'Considerando como cumpridas: {", ".join(marcadas)}.' if marcadas else ""))

    # Botões 1, 2, 3: versões da grade geradas pelo motor (o azul é a versão que está na tela).
    numero_atual = st.session_state.versao
    st.markdown("**Versão da grade**")
    colunas_de_versao = st.columns([0.5, 0.5, 0.5, 6], vertical_alignment="center")
    for numero in range(1, QUANTIDADE_DE_VERSOES + 1):
        colunas_de_versao[numero - 1].button(
            str(numero), key=f"versao_{numero}", on_click=escolher_versao, args=(numero,), width="stretch",
            type="primary" if numero == numero_atual else "secondary", disabled=numero > len(versoes),
            help=None if numero <= len(versoes) else "Não existe uma grade suficientemente diferente para esta versão.")
    colunas_de_versao[3].caption(descrever_versao(numero_atual, versoes))
    if len(versoes) < QUANTIDADE_DE_VERSOES:
        st.caption(f"O motor encontrou só {len(versoes)} versão(ões) diferentes com estes parâmetros.")
    if editada:
        st.info(f"Esta é a **sua versão editada** (a partir da versão {numero_atual}). Use a aba *Editar grade* para mudar "
                "ou restaurar. Trocar de versão descarta as suas edições.", icon=":material/edit:")

    if not editada:
        for fora in resultado["nao_incluidas"]:
            if fora["tipo"] == "Obrigatória" and fora["motivo"].startswith("choque"):
                st.warning(f'**{fora["nome"]} ({fora["codigo"]})** ficou de fora: {fora["motivo"]}. O sistema prioriza matérias de '
                           "período mais baixo e que destravam mais matérias. Se alguma matéria em curso já está concluída, "
                           "volte a *Conferir* e marque-a. " +
                           ("Veja também as outras versões acima. " if len(versoes) > 1 else "") +
                           "Você também pode ajustar a grade na aba *Editar grade*.", icon=":material/warning:")

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
        st.warning("Nenhuma matéria na grade. Ajuste o limite de créditos ou use a aba *Editar grade* para escolher matérias.")

    for aviso in resultado["avisos"]:
        if aviso["tipo"] == "sem_oferta_de_optativas":
            st.info(aviso["detalhe"][0].upper() + aviso["detalhe"][1:] + ".", icon=":material/info:")
    if resultado["sem_horario_fixo"]:
        codigos = " e ".join(s["codigo"] for s in resultado["sem_horario_fixo"])
        st.info(f"**{codigos}** não têm horário fixo na planilha de ofertas e não entram na grade.", icon=":material/info:")

    if not editada:   # os motivos de "ficou de fora" descrevem a sugestão automática; editada, não valem mais
        with st.expander(f'Ficaram de fora ({len(resultado["nao_incluidas"])})', expanded=not grade):
            st.dataframe([{"Código": n["codigo"], "Matéria": n["nome"], "Tipo": n["tipo"], "Motivo": n["motivo"]}
                          for n in sorted(resultado["nao_incluidas"], key=lambda n: (n["tipo"] != "Obrigatória", n["codigo"]))],
                         hide_index=True, width="stretch", column_config={"Motivo": st.column_config.TextColumn(width=420)})

    centro, direita, _ = st.columns([1.2, 1.2, 3.6])
    centro.download_button("Baixar CSV", grade_em_csv(grade), file_name="grade.csv", mime="text/csv",
                           icon=":material/download:", width="stretch")
    direita.download_button("Baixar JSON", json.dumps(resultado, ensure_ascii=False, indent=2).encode("utf-8"),
                            file_name="grade.json", mime="application/json", icon=":material/data_object:", width="stretch")
    # PDF e PNG são pesados de gerar (matplotlib). Passamos uma função (lambda) em vez dos bytes prontos:
    # assim o Streamlit só gera o arquivo QUANDO o usuário clica, e não a cada vez que a tela é desenhada.
    # on_click="ignore" evita que o clique reexecute o app inteiro.
    periodo_das_ofertas = resultado["_meta"]["periodo_das_ofertas"]
    exportacoes = st.columns(2)
    exportacoes[0].download_button("Baixar PDF", lambda: grade_em_imagem(resultado, "pdf"),
                                   file_name=f"grade_{periodo_das_ofertas}.pdf",
                                   mime="application/pdf", icon=":material/picture_as_pdf:", width="stretch",
                                   on_click="ignore", key="baixar_pdf")
    exportacoes[1].download_button("Baixar PNG", lambda: grade_em_imagem(resultado, "png"),
                                   file_name=f"grade_{periodo_das_ofertas}.png",
                                   mime="image/png", icon=":material/image:", width="stretch",
                                   on_click="ignore", key="baixar_png")


# --------------------------------------------------------------------------------------
# Aba 2: editar a grade (matérias disponíveis para o aluno cursar)
# --------------------------------------------------------------------------------------
TIPOS_DE_MATERIA = ["Obrigatória", "Optativa", "Humanidades"]


def descrever_turma(turma):
    """Uma linha com número da turma, docentes, horários e salas."""
    numero = f'Turma {turma["numero_da_turma"]} · ' if turma.get("numero_da_turma") else ""
    docentes = ", ".join(turma["docentes"]) or "Docente a definir"
    salas = ", ".join(sorted({a["sala"] for a in turma["aulas"] if a["sala"]}))
    return f'{numero}{docentes} · {formatar_horarios(turma["aulas"])}' + (f' · sala {salas}' if salas else "")


def aba_editar_grade(resultado, disponibilidade, escolhas):
    grade, selecao = resultado["grade"], st.session_state.selecao
    limite = escolhas["limite"]
    st.markdown("Aqui estão as matérias que você **pode cursar neste período**. Adicione, troque de turma ou remova: "
                "a grade abaixo e a aba *Minha grade* mudam na hora. Turmas que batem horário com a sua grade ficam bloqueadas, "
                "com o motivo ao lado.")

    colunas = st.columns([1, 1, 1, 1.6], vertical_alignment="bottom")
    colunas[0].metric("Créditos", f'{resultado["creditos_total"]:g} de {limite:g}')
    colunas[1].metric("Matérias na grade", len(grade))
    colunas[2].metric("Disponíveis", len(disponibilidade["disponiveis"]))
    colunas[3].button(f'Restaurar versão {st.session_state.versao}', on_click=restaurar_grade_automatica, disabled=not st.session_state.editada,
                      icon=":material/undo:", width="stretch", key="restaurar_sugestao")
    if resultado["creditos_total"] > limite:
        st.warning(f'A grade passou do limite de {limite:g} créditos definido nos parâmetros. '
                   "Você pode manter assim, mas confira se o seu curso permite essa carga.", icon=":material/warning:")

    with st.expander("Prévia da grade", expanded=True):
        if grade:
            desenhar_grade_semanal(grade)
        else:
            st.info("A grade está vazia. Adicione matérias abaixo.")

    st.subheader("Matérias disponíveis")
    filtro_busca, filtro_tipo, filtro_cabe = st.columns([2, 2, 1.4], vertical_alignment="bottom")
    busca = filtro_busca.text_input("Buscar", placeholder="Código ou nome da matéria", key="busca_editor").strip().lower()
    tipos = filtro_tipo.multiselect("Tipo", TIPOS_DE_MATERIA, default=TIPOS_DE_MATERIA, key="tipos_editor")
    so_o_que_cabe = filtro_cabe.toggle("Só o que cabe", key="so_cabe_editor",
                                       help="Esconde as matérias cujas turmas todas batem horário com a sua grade.")

    mostradas = 0
    for materia in disponibilidade["disponiveis"]:
        codigo = materia["codigo"]
        if materia["tipo"] not in tipos or (busca and busca not in codigo.lower() and busca not in materia["nome"].lower()):
            continue
        # para cada turma: None se cabe; senão o texto do choque (trocar a turma da própria matéria não conta como choque)
        choques = {t["id"]: explicar_choque(t, grade, ignorar_codigo=codigo) for t in materia["turmas"]}
        if so_o_que_cabe and codigo not in selecao and all(choques.values()):
            continue
        mostradas += 1
        with st.container(border=True):
            topo, selo = st.columns([5, 1.2], vertical_alignment="center")
            periodo = f' · período {materia["periodo"]}' if materia["periodo"] else ""
            extras = (" · cursando no BOA" if materia["em_curso_no_boa"] else "") + \
                     (f' · destrava {materia["destrava"]}' if materia["destrava"] else "")
            topo.markdown(f'**{codigo}** {materia["nome"]}  \n{materia["tipo"]}{periodo} · {materia["creditos"]:g} créd.{extras}')
            if codigo in selecao:
                selo.markdown(":green[**✓ Na grade**]")
            for turma in materia["turmas"]:
                texto, acao = st.columns([5, 1.2], vertical_alignment="center")
                texto.markdown(descrever_turma(turma))
                if choques[turma["id"]]:
                    texto.caption(f'⚠ {choques[turma["id"]]}')
                chave = f'turma_{turma["id"]}'
                if selecao.get(codigo) == turma["id"]:
                    acao.button("Remover", on_click=remover_materia, args=(codigo,), key=chave, icon=":material/delete:", width="stretch")
                else:
                    acao.button("Trocar" if codigo in selecao else "Adicionar", on_click=escolher_turma, args=(codigo, turma["id"]),
                                key=chave, disabled=bool(choques[turma["id"]]), help=choques[turma["id"]],
                                icon=":material/swap_horiz:" if codigo in selecao else ":material/add:", width="stretch")
    if not mostradas:
        st.info("Nenhuma matéria encontrada com esses filtros.")

    # Matérias que o aluno NÃO pode cursar agora (mesma lista de motivos da sugestão automática).
    indisponiveis = [{"Código": m["codigo"], "Matéria": m["nome"], "Tipo": m["tipo"],
                      "Motivo": "bloqueada (Vedada): pré-requisito pendente " + (", ".join(m["faltam"]) or "indefinido (vale o status do BOA)")}
                     for m in disponibilidade["bloqueadas"] if m["categoria"] == "obrigatoria" or m["turmas"]]
    indisponiveis += [{"Código": m["codigo"], "Matéria": m["nome"], "Tipo": m["tipo"],
                       "Motivo": "sem turma confirmada com horário completo na planilha de ofertas"}
                      for m in disponibilidade["sem_turma"] if m["categoria"] == "obrigatoria"]
    if indisponiveis:
        with st.expander(f"Obrigatórias que você ainda não pode cursar neste período ({len(indisponiveis)})"):
            st.dataframe(indisponiveis, hide_index=True, width="stretch", column_config={"Motivo": st.column_config.TextColumn(width=420)})


# ======================================================================================
# Aba "Todas as ofertas": disponível desde o início, sem precisar enviar o BOA
# ======================================================================================
# Sem currículo à mão, a categoria da oferta indica o tipo da matéria (na planilha de 2026-2 elas coincidem).
TIPO_PELA_CATEGORIA_DA_OFERTA = {"periodo": "obrigatoria", "outra": "obrigatoria",
                                 "eletiva": "optativa_condicionada", "servico": "optativa_condicionada"}
COLUNAS_DAS_OFERTAS = ["Código", "Matéria", "Turma", "Créd.", "Docentes", "Horários", "Salas", "Situação da turma"]


def curriculo_para_consulta():
    """O currículo do BOA enviado, se houver; senão o mais recente da pasta (serve só para classificar as turmas)."""
    if st.session_state.curriculo:
        return st.session_state.curriculo
    caminhos = sorted((PASTA_DO_APP / "grades_curricular").glob("curriculo_*.json"))
    return ler_json_da_pasta(caminhos[-1]) if caminhos else None


def tipo_da_turma(turma, disciplinas):
    """'obrigatoria', 'optativa_condicionada' ou 'optativa_restrita_humanidades'."""
    codigo = turma.get("codigo_no_curriculo")
    if codigo in disciplinas:
        return disciplinas[codigo]["tipo"]
    return TIPO_PELA_CATEGORIA_DA_OFERTA.get(turma["categoria"], "optativa_condicionada")


def situacao_da_turma_para_o_aluno(turma, disponibilidade, selecao):
    """Diz, em uma frase curta, o que aquela turma significa para ESTE aluno (precisa do BOA lido)."""
    codigo, id_da_turma = turma.get("codigo_no_curriculo"), turma["id"]
    if codigo in selecao:
        return "Na sua grade" if selecao[codigo] == id_da_turma else "Matéria na grade (outra turma)"
    if not turma["horario_completo"]:
        return "Sem horário completo"
    if codigo in {m["codigo"] for m in disponibilidade["disponiveis"]}:
        return "Disponível"
    if codigo in disponibilidade["cumpridas"]:
        return "Já cumprida"
    if codigo in {m["codigo"] for m in disponibilidade["bloqueadas"]}:
        return "Bloqueada (pré-requisito)"
    return "Fora das suas pendências"


def linha_da_turma(turma, disciplinas, disponibilidade, selecao):
    codigo = turma.get("codigo_no_curriculo") or turma["codigo"]
    disciplina = disciplinas.get(codigo, {})
    linha = {
        "Código": codigo, "Matéria": turma["nome"], "Turma": str(turma.get("numero_da_turma") or ""),
        "Créd.": f'{disciplina["creditos"]:g}' if "creditos" in disciplina else "",
        "Período": str(disciplina.get("periodo") or ""),
        "Docentes": ", ".join(turma["docentes"]) or "A definir",
        "Horários": formatar_horarios(turma["aulas"]) or "Sem horário",
        "Salas": ", ".join(sorted({a["sala"] for a in turma["aulas"] if a["sala"]})),
        "Situação da turma": turma["situacao"].capitalize(),
    }
    if disponibilidade is not None:    # com BOA lido, diz o que cada turma significa para o aluno
        linha["Para você"] = situacao_da_turma_para_o_aluno(turma, disponibilidade, selecao)
    return linha


def mostrar_turmas(linhas, colunas):
    st.dataframe([{coluna: linha[coluna] for coluna in colunas if coluna in linha} for linha in linhas],
                 hide_index=True, width="stretch", height=min(38 + 35 * len(linhas), 560))


def tela_ofertas():
    st.title("Todas as ofertas")
    ofertas_por_periodo = listar_ofertas()
    if not ofertas_por_periodo:
        st.info("Não encontrei nenhum arquivo ofertas_<período>.json na pasta do app.")
        return
    periodos = list(ofertas_por_periodo)
    inicial = st.session_state.periodo if st.session_state.periodo in periodos else periodos[-1]
    if len(periodos) > 1:
        periodo = st.selectbox("Período das ofertas", periodos, index=periodos.index(inicial), key="periodo_da_aba_de_ofertas")
    else:
        periodo = periodos[0]
    ofertas = ler_json_da_pasta(ofertas_por_periodo[periodo])
    meta = ofertas["_meta"]
    curriculo = curriculo_para_consulta()
    disciplinas = curriculo["disciplinas"] if curriculo else {}

    # Com um BOA lido do mesmo período, cada turma ganha a coluna "Para você".
    disponibilidade, selecao = None, {}
    if st.session_state.boa and periodo == st.session_state.periodo:
        disponibilidade, selecao = materias_disponiveis(), st.session_state.selecao or {}

    st.caption(f'{len(ofertas["turmas"])} turmas com vaga para o curso {meta.get("curso_filtrado", "")} em {periodo}'
               + (f' (a planilha tem {meta["turmas_na_planilha"]} no total).' if meta.get("turmas_na_planilha") else ".")
               + (" A planilha traz informações provisórias, sujeitas a mudanças." if "provis" in (meta.get("aviso_da_planilha") or "").lower() else "")
               + ("" if disponibilidade is not None else " Envie o seu BOA no planejador para ver, em cada turma, se você pode cursá-la."))
    busca = st.text_input("Buscar", placeholder="Código, nome da matéria ou docente", key="busca_ofertas",
                          icon=":material/search:").strip().lower()

    turmas = []
    for turma in ofertas["turmas"]:
        linha = linha_da_turma(turma, disciplinas, disponibilidade, selecao)
        if busca and busca not in f'{linha["Código"]} {linha["Matéria"]} {linha["Docentes"]}'.lower():
            continue
        turmas.append((turma, linha, tipo_da_turma(turma, disciplinas)))
    ordem = lambda item: (item[1]["Código"], item[1]["Turma"])
    colunas = COLUNAS_DAS_OFERTAS + (["Para você"] if disponibilidade is not None else [])

    aba_periodo, aba_obrigatorias, aba_optativas = st.tabs(["Por período", "Obrigatórias", "Optativas"])
    with aba_periodo:
        grupos = {}
        for turma, linha, _ in sorted(turmas, key=ordem):
            recomendado = turma.get("periodo_recomendado") if turma["categoria"] == "periodo" else None
            grupos.setdefault(recomendado, []).append(linha)
        for recomendado in sorted(g for g in grupos if g is not None):
            st.subheader(f"{recomendado}º período ({len(grupos[recomendado])})")
            mostrar_turmas(grupos[recomendado], colunas)
        if None in grupos:
            st.subheader(f"Eletivas, serviço e outras ofertas ({len(grupos[None])})")
            mostrar_turmas(grupos[None], colunas)
        if not grupos:
            st.info("Nenhuma turma encontrada.")
    with aba_obrigatorias:
        obrigatorias = [linha for _, linha, tipo in sorted(turmas, key=lambda i: (int(i[1]["Período"] or 99), *ordem(i)))
                        if tipo == "obrigatoria"]
        if obrigatorias:
            st.caption(f"{len(obrigatorias)} turmas, ordenadas pelo período da matéria no currículo.")
            mostrar_turmas(obrigatorias, ["Período"] + colunas)
        else:
            st.info("Nenhuma turma encontrada.")
    with aba_optativas:
        achou = False
        for tipo, titulo in (("optativa_condicionada", "Optativas"), ("optativa_restrita_humanidades", "Humanidades")):
            linhas = [linha for _, linha, t in sorted(turmas, key=ordem) if t == tipo]
            if linhas:
                achou = True
                st.subheader(f"{titulo} ({len(linhas)})")
                mostrar_turmas(linhas, colunas)
        if not achou:
            st.info("Nenhuma turma encontrada.")


# --------------------------------------------------------------------------------------
# Tela de resultado: abas
# --------------------------------------------------------------------------------------
def tela_resultado():
    escolhas = st.session_state.escolhas
    try:
        versoes = versoes_da_grade()
    except ErroDoMotor as erro:
        st.error(str(erro))
        st.button("Voltar", on_click=ir_para, args=(3,))
        return
    if st.session_state.versao > len(versoes):
        st.session_state.versao = 1
    resultado_do_motor = versoes[st.session_state.versao - 1]
    if st.session_state.selecao is None:   # primeira vez nesta geração: começa igual à sugestão do motor
        st.session_state.selecao = {g["codigo"]: g["turma_id"] for g in resultado_do_motor["grade"]}
        st.session_state.editada = False

    disponibilidade = materias_disponiveis()
    resultado = resultado_ativo(resultado_do_motor, disponibilidade)
    st.title(f'Sua grade para {resultado["_meta"]["periodo_das_ofertas"]}')

    aba_grade, aba_editar = st.tabs(["Minha grade", "Editar grade"])
    with aba_grade:
        aba_minha_grade(resultado, escolhas, versoes)
    with aba_editar:
        aba_editar_grade(resultado, disponibilidade, escolhas)
    st.button("Voltar", on_click=ir_para, args=(3,))


# ======================================================================================
# Roteador
# ======================================================================================
iniciar_estado()
if st.session_state.etapa > 1 and st.session_state.boa is None:
    st.session_state.etapa = 1
barra_lateral()
# A aba de ofertas fica sempre visível, antes mesmo de enviar o BOA.
aba_planejador, aba_das_ofertas = st.tabs(["Planejador", "Todas as ofertas"])
with aba_planejador:
    {1: tela_envio, 2: tela_conferencia, 3: tela_parametros, 4: tela_resultado}[st.session_state.etapa]()
with aba_das_ofertas:
    tela_ofertas()
