# -*- coding: utf-8 -*-
"""
Protótipo visual do Planejador de Grade (Streamlit), com DADOS DE EXEMPLO.

As telas são escolhidas pelo parâmetro ?tela=N da URL, só para gerar as imagens do protótipo:
    streamlit run prototipo_streamlit.py          ->  abrir http://localhost:8501/?tela=1  (1 a 5)
    1 = envio do BOA | 2 = conferência | 3 = parâmetros | 4 = resultado (Redes I marcada)
    5 = resultado padrão, com aviso de conflito
Nenhum cálculo real é feito aqui: o motor, os extratores e a nuvem entram nas próximas etapas.
"""
import json
import streamlit as st

st.set_page_config(page_title="Planejador de Grade", layout="wide", initial_sidebar_state="expanded")

# Dados de exemplo, gerados a partir do currículo, das ofertas 2026-2 e do BOA reais
DADOS = json.loads(r'''{
 "cenario_com_redes_cumprida": [
  {
   "codigo": "ICP472",
   "nome": "Metodologia da Pesquisa",
   "tipo": "Obrigatória",
   "creditos": 4.0,
   "periodo": 7,
   "docentes": "Carla Delgado",
   "aulas": [
    {
     "dia": "QUA",
     "dia_numero": 2,
     "inicio": "10:00",
     "fim": "12:00",
     "sala": "SDCC"
    },
    {
     "dia": "SEX",
     "dia_numero": 4,
     "inicio": "10:00",
     "fim": "12:00",
     "sala": "SDCC"
    }
   ],
   "motivo": "Obrig. · período 7 · destrava 1"
  },
  {
   "codigo": "ICP473",
   "nome": "Segurança da Informação",
   "tipo": "Obrigatória",
   "creditos": 4.0,
   "periodo": 7,
   "docentes": "Gabriel Caldas",
   "aulas": [
    {
     "dia": "QUA",
     "dia_numero": 2,
     "inicio": "08:00",
     "fim": "10:00",
     "sala": "F2-014/016"
    },
    {
     "dia": "SEX",
     "dia_numero": 4,
     "inicio": "08:00",
     "fim": "10:00",
     "sala": "F2-014/016"
    }
   ],
   "motivo": "Obrig. · período 7"
  },
  {
   "codigo": "ICP478",
   "nome": "Métodos Numéricos I",
   "tipo": "Optativa",
   "creditos": 4.0,
   "periodo": null,
   "docentes": "Mauro Rincon",
   "aulas": [
    {
     "dia": "TER",
     "dia_numero": 1,
     "inicio": "08:00",
     "fim": "10:00",
     "sala": "SDCC"
    },
    {
     "dia": "QUI",
     "dia_numero": 3,
     "inicio": "08:00",
     "fim": "10:00",
     "sala": "SDCC"
    }
   ],
   "motivo": "Optativa"
  },
  {
   "codigo": "ICP005",
   "nome": "Ética em Computação",
   "tipo": "Optativa",
   "creditos": 4.0,
   "periodo": null,
   "docentes": "João Carlos Pereira",
   "aulas": [
    {
     "dia": "TER",
     "dia_numero": 1,
     "inicio": "13:00",
     "fim": "15:00",
     "sala": "F2-007"
    },
    {
     "dia": "QUI",
     "dia_numero": 3,
     "inicio": "13:00",
     "fim": "15:00",
     "sala": "F2-007"
    }
   ],
   "motivo": "Optativa"
  },
  {
   "codigo": "ICP532",
   "nome": "Mineração de Dados",
   "tipo": "Optativa",
   "creditos": 4.0,
   "periodo": null,
   "docentes": "Silas Lima Filho",
   "aulas": [
    {
     "dia": "TER",
     "dia_numero": 1,
     "inicio": "15:00",
     "fim": "17:00",
     "sala": "LEP1"
    },
    {
     "dia": "QUI",
     "dia_numero": 3,
     "inicio": "15:00",
     "fim": "17:00",
     "sala": "F3-003"
    }
   ],
   "motivo": "Optativa"
  },
  {
   "codigo": "ICP016",
   "nome": "Introd Métod Elementos Finitos",
   "tipo": "Optativa",
   "creditos": 4.0,
   "periodo": null,
   "docentes": "Marcello Goulart",
   "aulas": [
    {
     "dia": "SEG",
     "dia_numero": 0,
     "inicio": "13:00",
     "fim": "15:00",
     "sala": "F2-007"
    },
    {
     "dia": "QUA",
     "dia_numero": 2,
     "inicio": "13:00",
     "fim": "15:00",
     "sala": "F2-007"
    }
   ],
   "motivo": "Optativa"
  }
 ],
 "cenario_padrao": [
  {
   "codigo": "ICP362",
   "nome": "Redes de Computadores I",
   "tipo": "Obrigatória",
   "creditos": 4.0,
   "periodo": 6,
   "docentes": "Daniel Sadoc",
   "aulas": [
    {
     "dia": "QUA",
     "dia_numero": 2,
     "inicio": "10:00",
     "fim": "12:00",
     "sala": "F2-007"
    },
    {
     "dia": "SEX",
     "dia_numero": 4,
     "inicio": "10:00",
     "fim": "12:00",
     "sala": "F2-007"
    }
   ],
   "motivo": "Obrig. · período 6 · destrava 5"
  },
  {
   "codigo": "ICP478",
   "nome": "Métodos Numéricos I",
   "tipo": "Optativa",
   "creditos": 4.0,
   "periodo": null,
   "docentes": "Mauro Rincon",
   "aulas": [
    {
     "dia": "TER",
     "dia_numero": 1,
     "inicio": "08:00",
     "fim": "10:00",
     "sala": "SDCC"
    },
    {
     "dia": "QUI",
     "dia_numero": 3,
     "inicio": "08:00",
     "fim": "10:00",
     "sala": "SDCC"
    }
   ],
   "motivo": "Optativa"
  },
  {
   "codigo": "ICP005",
   "nome": "Ética em Computação",
   "tipo": "Optativa",
   "creditos": 4.0,
   "periodo": null,
   "docentes": "João Carlos Pereira",
   "aulas": [
    {
     "dia": "TER",
     "dia_numero": 1,
     "inicio": "13:00",
     "fim": "15:00",
     "sala": "F2-007"
    },
    {
     "dia": "QUI",
     "dia_numero": 3,
     "inicio": "13:00",
     "fim": "15:00",
     "sala": "F2-007"
    }
   ],
   "motivo": "Optativa"
  },
  {
   "codigo": "ICP532",
   "nome": "Mineração de Dados",
   "tipo": "Optativa",
   "creditos": 4.0,
   "periodo": null,
   "docentes": "Silas Lima Filho",
   "aulas": [
    {
     "dia": "TER",
     "dia_numero": 1,
     "inicio": "15:00",
     "fim": "17:00",
     "sala": "LEP1"
    },
    {
     "dia": "QUI",
     "dia_numero": 3,
     "inicio": "15:00",
     "fim": "17:00",
     "sala": "F3-003"
    }
   ],
   "motivo": "Optativa"
  },
  {
   "codigo": "ICP016",
   "nome": "Introd Métod Elementos Finitos",
   "tipo": "Optativa",
   "creditos": 4.0,
   "periodo": null,
   "docentes": "Marcello Goulart",
   "aulas": [
    {
     "dia": "SEG",
     "dia_numero": 0,
     "inicio": "13:00",
     "fim": "15:00",
     "sala": "F2-007"
    },
    {
     "dia": "QUA",
     "dia_numero": 2,
     "inicio": "13:00",
     "fim": "15:00",
     "sala": "F2-007"
    }
   ],
   "motivo": "Optativa"
  },
  {
   "codigo": "ICP518",
   "nome": "Teoria de Grafos",
   "tipo": "Optativa",
   "creditos": 4.0,
   "periodo": null,
   "docentes": "Matheus Adauto",
   "aulas": [
    {
     "dia": "SEG",
     "dia_numero": 0,
     "inicio": "08:00",
     "fim": "10:00",
     "sala": "F3-006"
    },
    {
     "dia": "QUA",
     "dia_numero": 2,
     "inicio": "08:00",
     "fim": "10:00",
     "sala": "F3-006"
    }
   ],
   "motivo": "Optativa"
  }
 ],
 "libera": {
  "ICPZ55": {
   "qtd": 0,
   "ofertadas": []
  },
  "ICP362": {
   "qtd": 5,
   "ofertadas": [
    "ICP473"
   ]
  },
  "ICP082": {
   "qtd": 0,
   "ofertadas": []
  },
  "NEP110": {
   "qtd": 0,
   "ofertadas": []
  }
 },
 "candidatas_com_turma": 14,
 "destrava": {
  "ICP362": 5,
  "ICP472": 1
 },
 "em_curso": [
  {
   "codigo": "ICPZ55",
   "nome": "Ativ Curricular Extensão - Bcc",
   "tipo": "Obrigatória",
   "periodo": 1
  },
  {
   "codigo": "ICP362",
   "nome": "Redes de Computadores I",
   "tipo": "Obrigatória",
   "periodo": 6
  },
  {
   "codigo": "ICP082",
   "nome": "Oficina de Teconologia II",
   "tipo": "Optativa",
   "periodo": null
  },
  {
   "codigo": "NEP110",
   "nome": "Fund Direitos Humanos",
   "tipo": "Humanidades",
   "periodo": null
  }
 ],
 "pendentes_obrigatorias": [
  {
   "codigo": "ICPX06",
   "nome": "Atividades Complementares Bcc",
   "creditos": 2.0,
   "periodo": 1,
   "status": "Facultada"
  },
  {
   "codigo": "ICPZ55",
   "nome": "Ativ Curricular Extensão - Bcc",
   "creditos": 0.0,
   "periodo": 1,
   "status": "Cursando"
  },
  {
   "codigo": "ICP362",
   "nome": "Redes de Computadores I",
   "creditos": 4.0,
   "periodo": 6,
   "status": "Cursando"
  },
  {
   "codigo": "ICP472",
   "nome": "Metodologia da Pesquisa",
   "creditos": 4.0,
   "periodo": 7,
   "status": "Facultada"
  },
  {
   "codigo": "ICP473",
   "nome": "Segurança da Informação",
   "creditos": 4.0,
   "periodo": 7,
   "status": "Vedada"
  },
  {
   "codigo": "ICPK01",
   "nome": "Trab Conclusão de Curso Bcc",
   "creditos": 2.0,
   "periodo": 8,
   "status": "Vedada"
  }
 ]
}''')

tela = st.query_params.get("tela", "1")
NOMES_DAS_ETAPAS = ["Enviar BOA", "Conferir", "Parâmetros", "Resultado"]
etapa_atual = {"1": 0, "2": 1, "3": 2, "4": 3, "5": 3}.get(tela, 0)
DIAS = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB"]
FAIXAS_DE_HORARIO = [("08:00", "10:00"), ("10:00", "12:00"), ("13:00", "15:00"), ("15:00", "17:00")]

st.markdown("""<style>
.etapa{display:flex;align-items:center;gap:.65rem;padding:.4rem 0;color:#6b7280;font-size:.95rem}
.etapa .bolinha{width:1.65rem;height:1.65rem;border-radius:50%;border:1.5px solid #cbd5e1;display:flex;
  align-items:center;justify-content:center;font-size:.8rem;background:#fff}
.etapa.atual{color:#111827;font-weight:600}
.etapa.atual .bolinha{background:#ff4b4b;border-color:#ff4b4b;color:#fff}
.etapa.feita .bolinha{background:#e8f5e9;border-color:#81c784;color:#2e7d32}
table.grade{border-collapse:separate;border-spacing:6px;width:100%;table-layout:fixed}
table.grade td,table.grade th{border:none !important;padding:0 !important;background:transparent !important}
table.grade th{font-weight:600;font-size:.85rem;color:#475569;padding:.3rem}
table.grade td.hora{width:96px;font-size:.78rem;color:#64748b;text-align:right;padding-right:.5rem}
.aula{border-radius:8px;padding:.45rem .55rem;font-size:.76rem;line-height:1.3;border:1px solid;height:104px;overflow:hidden}
.aula b{font-size:.82rem}
.aula.obrigatoria{background:#e7f1ff;border-color:#8bb8f8;color:#0b3d91}
.aula.optativa{background:#e8f6ec;border-color:#86cf9c;color:#14532d}
.vazio{height:104px;border-radius:8px;background:#f8fafc;border:1px dashed #e2e8f0}
.legenda span{display:inline-block;width:.8rem;height:.8rem;border-radius:3px;margin:0 .35rem 0 .9rem;border:1px solid}
</style>""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------------- barra lateral
with st.sidebar:
    st.markdown("### Planejador de Grade")
    st.caption("UFRJ · Ciência da Computação")
    html_das_etapas = ""
    for posicao, nome in enumerate(NOMES_DAS_ETAPAS):
        classe = "atual" if posicao == etapa_atual else ("feita" if posicao < etapa_atual else "")
        marca = "✓" if posicao < etapa_atual else str(posicao + 1)
        html_das_etapas += f'<div class="etapa {classe}"><span class="bolinha">{marca}</span>{nome}</div>'
    st.markdown(html_das_etapas, unsafe_allow_html=True)
    st.divider()
    st.caption("Protótipo com dados de exemplo.")


def formatar_creditos(valor):
    return str(int(valor)) if float(valor).is_integer() else str(valor)


def desenhar_grade_semanal(turmas):
    """Monta a tabela dias x faixas de horário com uma caixa colorida para cada aula."""
    celulas = {}
    for turma in turmas:
        classe = "obrigatoria" if turma["tipo"] == "Obrigatória" else "optativa"
        for aula in turma["aulas"]:
            faixa = FAIXAS_DE_HORARIO.index((aula["inicio"], aula["fim"]))
            celulas[(faixa, aula["dia_numero"])] = (
                f'<div class="aula {classe}"><b>{turma["codigo"]}</b><br>{turma["nome"]}<br>{aula["sala"]}</div>')
    linhas = '<tr><th></th>' + "".join(f"<th>{dia}</th>" for dia in DIAS) + "</tr>"
    for faixa, (inicio, fim) in enumerate(FAIXAS_DE_HORARIO):
        linhas += f'<tr><td class="hora">{inicio}–{fim}</td>'
        for dia_numero in range(len(DIAS)):
            linhas += f'<td>{celulas.get((faixa, dia_numero), "<div class=vazio></div>")}</td>'
        linhas += "</tr>"
    st.markdown(f'<table class="grade">{linhas}</table>', unsafe_allow_html=True)
    st.markdown('<div class="legenda"><span style="background:#e7f1ff;border-color:#8bb8f8"></span>Obrigatória'
                '<span style="background:#e8f6ec;border-color:#86cf9c"></span>Optativa</div>', unsafe_allow_html=True)


def tabela_de_turmas(turmas):
    linhas = []
    for turma in turmas:
        horarios = " · ".join(f'{a["dia"]} {a["inicio"]}–{a["fim"]}' for a in turma["aulas"])
        linhas.append({"Código": turma["codigo"], "Matéria": turma["nome"],
                       "Créd.": formatar_creditos(turma["creditos"]), "Horários": horarios,
                       "Docente": turma["docentes"], "Motivo da escolha": turma["motivo"]})
    # larguras fixas (em pixels) para o texto de cada coluna caber sem ser cortado
    larguras = {"Código": 70, "Matéria": 215, "Créd.": 55, "Horários": 250, "Docente": 140, "Motivo da escolha": 205}
    st.dataframe(linhas, hide_index=True, width="stretch",
                 column_config={nome: st.column_config.TextColumn(width=largura) for nome, largura in larguras.items()})


# ---------------------------------------------------------------------------------- tela 1
if tela == "1":
    st.title("Planejador de Grade")
    st.markdown("Envie o seu BOA e receba uma grade sem choques de horário para o próximo período.")
    esquerda, direita = st.columns([3, 2], gap="large")
    with esquerda:
        with st.container(border=True):
            st.subheader("1. Envie o seu BOA")
            st.file_uploader("Boletim de Orientação Acadêmica (PDF)", type=["pdf"])
            st.selectbox("Período das ofertas", ["2026-2 (informações provisórias)", "2026-1"])
            st.button("Ler BOA", type="primary", disabled=True, icon=":material/description:")
    with direita:
        with st.container(border=True):
            st.subheader("Como funciona")
            st.markdown("1. O sistema lê o PDF e identifica o que falta cursar.\n"
                        "2. Você confere o resultado e marca as matérias que está cursando.\n"
                        "3. A grade é montada priorizando períodos mais baixos e pré-requisitos.")
        st.info("**Privacidade.** O PDF é usado só para extrair as matérias. Nome e matrícula não são "
                "salvos, e o arquivo é apagado depois do processamento.", icon=":material/lock:")

# ---------------------------------------------------------------------------------- tela 2
elif tela == "2":
    st.title("Confira o que foi lido")
    st.success("BOA lido: **Ciência da Computação (85783)**, currículo **2022/2**.", icon=":material/check_circle:")
    colunas = st.columns(4)
    colunas[0].metric("Obrigatórias (créditos)", "123 / 139")
    colunas[1].metric("Optativas (créditos)", "26 / 32")
    colunas[2].metric("Humanidades (créditos)", "0 / 4")
    colunas[3].metric("Extensão (horas)", "0 / 320")

    st.subheader("Matérias em curso")
    st.caption("Por padrão, elas contam como **não cumpridas**. Marque as que o sistema deve considerar concluídas.")
    with st.container(border=True):
        for materia in DADOS["em_curso"]:
            esquerda, direita = st.columns([3, 2], vertical_alignment="center")
            periodo = f' · período {materia["periodo"]}' if materia["periodo"] else ""
            esquerda.checkbox(f'**{materia["codigo"]}** {materia["nome"]}  \n{materia["tipo"]}{periodo}',
                              key=materia["codigo"])
            efeito = DADOS["libera"][materia["codigo"]]
            if efeito["qtd"]:
                direita.caption(f'Se marcada, libera **{efeito["qtd"]} matérias** '
                                f'({len(efeito["ofertadas"])} ofertada neste período).')
            else:
                direita.caption("Não libera outras matérias.")

    with st.expander("Obrigatórias pendentes lidas do BOA"):
        st.dataframe([{"Código": p["codigo"], "Matéria": p["nome"], "Créd.": formatar_creditos(p["creditos"]),
                       "Período": p["periodo"], "Status no BOA": p["status"]}
                      for p in DADOS["pendentes_obrigatorias"]], hide_index=True, width="stretch")
    esquerda, direita, _ = st.columns([1, 1, 4])
    esquerda.button("Voltar", width="stretch")
    direita.button("Continuar", type="primary", width="stretch")

# ---------------------------------------------------------------------------------- tela 3
elif tela == "3":
    st.title("Parâmetros da grade")
    esquerda, direita = st.columns([3, 2], gap="large")
    with esquerda:
        with st.container(border=True):
            st.slider("Limite de créditos no período", min_value=8, max_value=32, value=24, step=2,
                      help="O sistema não passa desse total.")
            st.toggle("Incluir optativas", value=True)
            st.select_slider("O que priorizar", options=["Períodos mais baixos", "Equilibrado", "Pré-requisitos"],
                             value="Equilibrado")
            st.toggle("Mostrar outras opções de grade", value=False, disabled=True,
                      help="Recurso futuro.")
            st.caption("Outras opções de grade: em breve.")
    with direita:
        with st.container(border=True):
            st.subheader("Resumo")
            st.metric("Matérias candidatas", DADOS["candidatas_com_turma"],
                      help="Pendentes liberadas e com turma confirmada em 2026-2.")
            st.caption("Matérias pendentes com turma confirmada ou externa em 2026-2. As *Vedada* ficam de fora, "
                       "a menos que você marque uma matéria em curso como cumprida.")
    esquerda, direita, _ = st.columns([1, 1.4, 4])
    esquerda.button("Voltar", width="stretch")
    direita.button("Gerar grade", type="primary", width="stretch", icon=":material/calendar_month:")

# ---------------------------------------------------------------------------------- telas 4 e 5
else:
    conflito = tela == "5"
    turmas = DADOS["cenario_padrao"] if conflito else DADOS["cenario_com_redes_cumprida"]
    st.title("Sua grade para 2026-2")
    st.caption("Informações provisórias da planilha de ofertas." +
               ("" if conflito else " Considerando **Redes de Computadores I** como cumprida."))
    if conflito:
        st.warning("**Metodologia da Pesquisa (ICP472)** ficou de fora: tem aula na quarta e na sexta, das "
                   f'10:00 às 12:00, no mesmo horário de **Redes de Computadores I (ICP362)**, que vem antes no '
                   f'currículo e destrava {DADOS["destrava"]["ICP362"]} matérias (a outra destrava '
                   f'{DADOS["destrava"]["ICP472"]}). Se Redes I já está concluída, marque-a em *Matérias em curso*.',
                   icon=":material/warning:")
    colunas = st.columns(3)
    colunas[0].metric("Créditos", "24 de 24")
    colunas[1].metric("Matérias", len(turmas))
    colunas[2].metric("Obrigatórias", sum(1 for t in turmas if t["tipo"] == "Obrigatória"))
    desenhar_grade_semanal(turmas)
    st.subheader("Turmas escolhidas")
    tabela_de_turmas(turmas)
    st.info("**ICPZ55** (Atividade Curricular de Extensão, 320 h) não tem horário fixo e não entra na grade.",
            icon=":material/info:")
    esquerda, direita, _ = st.columns([1.4, 1.4, 4])
    esquerda.button("Baixar como imagem", icon=":material/image:", width="stretch")
    direita.button("Baixar CSV", icon=":material/download:", width="stretch")
