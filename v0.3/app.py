import streamlit as st
import json
import pandas as pd

# Importações robustas para lidar com possíveis sufixos "_2" nos seus arquivos

import extrator_boa
import motor_grade
import extrator_ofertas
# ==========================================
# CONFIGURAÇÃO DA PÁGINA (Deve ser o 1º comando Streamlit)
# ==========================================
st.set_page_config(page_title="PBAER UFRJ - Planejador", layout="wide")

st.markdown("""
<style>
    .titulo-principal { text-align: center; color: #003366; }
    .stButton>button { width: 100%; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# GERENCIAMENTO DE ESTADO (SESSION STATE)
# ==========================================
if "tela" not in st.session_state:
    st.session_state.tela = 1
if "dados_boa" not in st.session_state:
    st.session_state.dados_boa = None
if "materias_assumidas_aprovadas" not in st.session_state:
    st.session_state.materias_assumidas_aprovadas = []
if "grade_gerada" not in st.session_state:
    st.session_state.grade_gerada = None

def mudar_tela(nova_tela):
    st.session_state.tela = nova_tela

# ==========================================
# CARREGAMENTO DE DADOS (JSONs)
# ==========================================
@st.cache_data
def carregar_jsons():
    # Tenta carregar com ou sem o sufixo "_2"
    arquivos_grade = ["grade_curricular_bcc.json", "grade_curricular_bcc_2.json"]
    arquivos_ofertas = ["ofertas_2026-2.json", "ofertas_2026-2_2.json"]
    
    grade_curricular, ofertas = None, None
    
    for f_name in arquivos_grade:
        try:
            with open(f_name, "r", encoding="utf-8") as f:
                grade_curricular = json.load(f)
            break
        except FileNotFoundError:
            continue
            
    for f_name in arquivos_ofertas:
        try:
            with open(f_name, "r", encoding="utf-8") as f:
                ofertas = json.load(f)
            break
        except FileNotFoundError:
            continue
            
    return grade_curricular, ofertas

grade_curricular, ofertas_turmas = carregar_jsons()

# ==========================================
# CALLBACKS (Executados antes da página recarregar)
# ==========================================
def processar_boa():
    arquivo = st.session_state.get("arquivo_upload")
    if arquivo is not None:
        try:
            st.session_state.dados_boa = extrator_boa.extrair_boa(arquivo)
            st.session_state.tela = 2
        except Exception as e:
            st.session_state.erro_extracao = f"Falha na extração: {str(e)}"

# ==========================================
# TELAS DA APLICAÇÃO
# ==========================================
def tela_upload():
    st.markdown("<h1 class='titulo-principal'>Planejador de Grade - BCC UFRJ</h1>", unsafe_allow_html=True)
    st.write("Bem-vindo! Faça o upload do seu B.O.A (Boletim de Orientação Acadêmica) em PDF para começarmos.")
    
    st.file_uploader("Selecione seu B.O.A (PDF)", type=["pdf"], key="arquivo_upload")
    
    # Desabilita o botão se não houver arquivo no session_state
    desabilitar_botao = st.session_state.get("arquivo_upload") is None
    
    st.button("Ler B.O.A", type="primary", disabled=desabilitar_botao, on_click=processar_boa)
    
    if "erro_extracao" in st.session_state:
        st.error(st.session_state.erro_extracao)
        del st.session_state.erro_extracao

def tela_conferencia():
    st.title("Conferência de Matérias em Curso")
    st.write("Identificamos que você está cursando as seguintes matérias. Selecione aquelas que você espera ser aprovado (elas contarão como pré-requisitos cumpridos para a próxima grade):")
    
    materias_em_curso = [m for m in st.session_state.dados_boa.get("pendentes", []) if m.get("status") == "Cursando"]
    
    selecionadas = []
    if not materias_em_curso:
        st.info("Nenhuma matéria em curso identificada no B.O.A.")
    else:
        for mat in materias_em_curso:
            if st.checkbox(f"{mat['codigo']} - {mat['nome']}", value=True):
                selecionadas.append(mat['codigo'])
    
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.button("Voltar", on_click=mudar_tela, args=(1,))
    with col2:
        if st.button("Avançar para Parâmetros", type="primary"):
            st.session_state.materias_assumidas_aprovadas = selecionadas
            mudar_tela(3)
            st.rerun()

def tela_parametros():
    st.title("Parâmetros do Motor de Grade")
    
    limite_cred = st.slider("Limite máximo de créditos na semana", min_value=12, max_value=32, value=24)
    incluir_optativas = st.checkbox("Incluir optativas se sobrar espaço?", value=True)
    
    # Mapeando escolhas fáceis de ler para as chaves reais que o motor aceita
    opcoes_prioridade = {
        "equilibrado": "Equilíbrio Geral",
        "periodos": "Focar em matérias atrasadas (períodos baixos)",
        "prerequisitos": "Desbloquear gargalos (pré-requisitos)"
    }
    prioridade = st.selectbox(
        "Qual a sua prioridade principal?", 
        options=list(opcoes_prioridade.keys()), 
        format_func=lambda x: opcoes_prioridade[x]
    )
    
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.button("Voltar", on_click=mudar_tela, args=(2,))
    with col2:
        if st.button("Gerar Nova Grade", type="primary"):
            if grade_curricular and ofertas_turmas:
                with st.spinner("Calculando a melhor grade para você..."):
                    try:
                        # Assinatura corrigida para o motor_grade
                        st.session_state.grade_gerada = motor_grade.gerar_grade(
                            dados_do_boa=st.session_state.dados_boa,
                            curriculo=grade_curricular,
                            ofertas=ofertas_turmas,
                            limite_de_creditos=limite_cred,
                            incluir_optativas=incluir_optativas,
                            prioridade=prioridade,
                            cursando_como_cumpridas=st.session_state.materias_assumidas_aprovadas
                        )
                        mudar_tela(4)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao gerar a grade: {e}")
            else:
                st.error("As bases de dados (JSON) não foram carregadas. Verifique se os arquivos estão na pasta.")

def tela_resultado():
    st.title("Sua Grade Sugerida")
    
    if not st.session_state.grade_gerada:
        st.warning("Nenhuma grade foi gerada.")
        st.button("Tentar Novamente", on_click=mudar_tela, args=(3,))
        return

    grade = st.session_state.grade_gerada.get("grade", [])
    estatisticas = st.session_state.grade_gerada.get("estatisticas", {})
    
    st.write(f"**Créditos na Grade:** {st.session_state.grade_gerada.get('creditos_total')} | **Matérias Avaliadas:** {estatisticas.get('candidatas')}")
    
    st.subheader("Turmas Selecionadas")
    if not grade:
        st.info("O motor não selecionou nenhuma matéria com os parâmetros atuais.")
    else:
        df_grade = pd.DataFrame(grade)
        st.dataframe(df_grade[["codigo", "nome", "tipo", "creditos", "motivo"]], use_container_width=True, hide_index=True)
        
        # ==========================================
        # NOVO: Horário Visual Automatizado e Colorido
        # ==========================================
        st.subheader("Horário Semanal")
        
        # Paleta de cores pastéis para destacar as disciplinas
        cores = ["#D4E6F1", "#D5F5E3", "#FCF3CF", "#FDEBD0", "#F5EEF8", "#EAEDED", "#FADBD8", "#E8DAEF", "#D1F2EB", "#FAD7A1"]
        cor_disciplina = {}
        idx_cor = 0
        
        # Atribuir uma cor para cada matéria da grade
        for item in grade:
            cod = item.get("codigo")
            if cod not in cor_disciplina:
                cor_disciplina[cod] = cores[idx_cor % len(cores)]
                idx_cor += 1

        dias = ["SEG", "TER", "QUA", "QUI", "SEX"]
        horas = ["08:00 - 10:00", "10:00 - 12:00", "13:00 - 15:00", "15:00 - 17:00", "18:00 - 20:00"]
        
        # Preparar a estrutura vazia do horário (Dicionário de Listas)
        grid = {h: {d: [] for d in dias} for h in horas}
        
        # Preencher os horários com pequenos "cards" em HTML
        for item in grade:
            cod = item.get("codigo", "")
            nome = item.get("nome", "")
            docente = item.get("docente", "Docente não informado")
            cor = cor_disciplina.get(cod, "#ffffff")
            
            # Limitar o tamanho do nome da disciplina para não desconfigurar a tabela
            if len(nome) > 30: 
                nome = nome[:27] + "..."
            
            # Cria o cartão com CSS embutido
            card_html = f'''
            <div style="background-color: {cor}; padding: 6px; border-radius: 6px; border: 1px solid #ccc; margin-bottom: 4px; text-align: center; line-height: 1.2;">
                <strong style="font-size: 0.9em; color: #333;">{cod}</strong><br>
                <span style="font-size: 0.8em; font-weight: bold; color: #111;">{nome}</span><br>
                <span style="font-size: 0.75em; color: #444;"><em>{docente}</em></span>
            </div>
            '''
            
            for aula in item.get("aulas", []):
                dia_str = aula.get("dia")
                if dia_str in dias:
                    inicio = aula.get("inicio")
                    fim = aula.get("fim")
                    hora_faixa = f"{inicio} - {fim}"
                    if hora_faixa in grid:
                        grid[hora_faixa][dia_str].append(card_html)
                        
        # Construir a Tabela HTML Final
        html_tabela = '<table style="width: 100%; border-collapse: collapse; font-family: sans-serif;">'
        html_tabela += '<thead><tr style="background-color: #f0f2f6;">'
        html_tabela += '<th style="border: 1px solid #ddd; padding: 10px; text-align: center; width: 120px;">Horário</th>'
        for d in dias:
            html_tabela += f'<th style="border: 1px solid #ddd; padding: 10px; text-align: center; width: 17%;">{d}</th>'
        html_tabela += '</tr></thead><tbody>'
        
        for h in horas:
            html_tabela += '<tr>'
            html_tabela += f'<td style="border: 1px solid #ddd; padding: 10px; text-align: center; font-weight: bold; vertical-align: middle;">{h}</td>'
            for d in dias:
                celulas = grid[h][d]
                # Se houver conflito de horário (duas matérias na mesma hora), empilha os cards. Se não, exibe traço.
                conteudo = "".join(celulas) if celulas else '<div style="color: #ccc; text-align: center;">-</div>'
                html_tabela += f'<td style="border: 1px solid #ddd; padding: 6px; vertical-align: top;">{conteudo}</td>'
            html_tabela += '</tr>'
        html_tabela += '</tbody></table>'
        
        # Injetar o HTML no ecrã da aplicação Streamlit
        st.markdown(html_tabela, unsafe_allow_html=True)
        
        avisos = st.session_state.grade_gerada.get("avisos", [])
        for aviso in avisos:
            st.warning(f"{aviso['tipo']}: {aviso['detalhe']}")

    st.markdown("---")
    if st.button("Começar Novo Planejamento", type="primary", on_click=mudar_tela, args=(1,)):
        st.session_state.dados_boa = None
        st.session_state.materias_assumidas_aprovadas = []
        st.session_state.grade_gerada = None
        
# ==========================================
# ROTEDOR DE TELAS
# ==========================================
if st.session_state.tela == 1:
    tela_upload()
elif st.session_state.tela == 2:
    tela_conferencia()
elif st.session_state.tela == 3:
    tela_parametros()
elif st.session_state.tela == 4:
    tela_resultado()
else:
    # Fallback seguro
    st.session_state.tela = 1
    st.rerun()