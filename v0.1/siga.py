import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

def extrair_grade_curricular(url):
    response = requests.get(url)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')

    tabelas = soup.find_all('table')

    lista_obrigatorias = []
    lista_requisitos = []
    lista_equivalencias = []

    # Contadores globais para garantir o agrupamento lógico (DNF)
    id_grupo_req = 1
    id_grupo_eq = 1

    for tabela in tabelas:
        linhas = tabela.find_all('tr')
        
        for linha in linhas[1:]:  # Pular o cabeçalho
            colunas = linha.find_all('td')
            
            if len(colunas) < 5:
                continue
                
            codigo_alvo = colunas[0].text.strip()
            nome = colunas[1].text.strip()
            creditos = colunas[2].text.strip()
            
            lista_obrigatorias.append({
                'codigo': codigo_alvo,
                'nome': nome,
                'creditos': creditos
            })
            
            # Extrair texto da célula de requisitos preservando quebras de linha como '\n'
            texto_requisitos = colunas[4].get_text(separator='\n').strip()
            if not texto_requisitos:
                continue

            linhas_regra = texto_requisitos.split('\n')
            
            for regra in linhas_regra:
                regra = regra.strip()
                if not regra:
                    continue
                
                # 1. Tratamento de Equivalências (Possui o sinal "=")
                if '=' in regra:
                    partes = regra.split('=')
                    if len(partes) == 2:
                        alvo_eq = re.sub(r'[^A-Z0-9]', '', partes[0])
                        # Na equivalência, o símbolo "+" atua como E lógico
                        equivalentes = partes[1].split('+')
                        
                        for eq in equivalentes:
                            codigo_eq = re.sub(r'[^A-Z0-9]', '', eq)
                            if codigo_eq and alvo_eq:
                                lista_equivalencias.append({
                                    'disciplina_alvo': alvo_eq,
                                    'disciplina_equivalente': codigo_eq,
                                    'id_grupo_equivalencia': id_grupo_eq
                                })
                        id_grupo_eq += 1
                        
                # 2. Tratamento de Requisitos Originais (Não possui "=")
                else:
                    # Remove identificadores como "(P)", "(C)" ou espaços extras
                    regra_limpa = re.sub(r'\s*\([A-Za-z]\)\s*', '', regra)
                    # Nos requisitos originais, a vírgula "," atua como E lógico
                    requisitos = regra_limpa.split(',')
                    
                    for req in requisitos:
                        codigo_req = re.sub(r'[^A-Z0-9]', '', req)
                        if codigo_req:
                            lista_requisitos.append({
                                'disciplina_alvo': codigo_alvo,
                                'requisito': codigo_req,
                                'id_grupo_requisito': id_grupo_req
                            })
                    id_grupo_req += 1

    # Conversão para DataFrames e exportação
    pd.DataFrame(lista_obrigatorias).to_csv('obrigatorias.csv', index=False, encoding='utf-8')
    pd.DataFrame(lista_requisitos).to_csv('requisitos.csv', index=False, encoding='utf-8')
    pd.DataFrame(lista_equivalencias).to_csv('equivalencias.csv', index=False, encoding='utf-8')
    print("Extração concluída com sucesso. Arquivos .csv gerados.")

# URL direta dos dados (conteúdo do iframe)
url_fonte = "https://siga.ufrj.br/repositorio-curriculo/3BA3881A-92A4-F79C-3ACF-54A4AF7D2C8F.html"
extrair_grade_curricular(url_fonte)