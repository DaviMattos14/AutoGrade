#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extrator_boa.py  (versão beta)
==============================
Lê o BOA (Boletim de Orientação Acadêmica) da UFRJ em PDF e gera um JSON com o mínimo
necessário para o planejador de grade: curso, versão curricular, matérias cumpridas e
matérias pendentes com o status que o próprio BOA informa.

Uso:
    python extrator_boa.py boa.pdf
    python extrator_boa.py boa.pdf --curriculo curriculo_85783_2022-2.json --saida boa_extraido.json

Como função (para o Streamlit ou para uma Lambda):
    from extrator_boa import extrair_boa
    dados = extrair_boa(arquivo_ou_caminho, caminho_do_curriculo=None)

Dependência: pdfplumber (pip install pdfplumber). É Python puro, sem programas externos.

PRIVACIDADE: o script NÃO extrai nome, matrícula nem notas. O JSON de saída só contém
códigos de matérias, status, créditos e totais. (Também não guarda o nome do arquivo.)

Como o BOA é organizado (e o que o script faz com isso)
-------------------------------------------------------
Cada linha das tabelas tem duas metades lado a lado:
  * ESQUERDA: a matéria do currículo (código, nome, créditos, carga horária, período);
  * DIREITA: a matéria cursada que a cumpriu (ou equivalente) e a nota;
  * última coluna: o status das matérias NÃO cumpridas ("Inscrição Facultada",
    "Inscrição Vedada" ou "Cursando"). Para as cumpridas, o status fica vazio.
O script usa a POSIÇÃO horizontal de cada palavra na página para saber a que coluna ela
pertence, porque o texto "corrido" do PDF embaralha as duas metades.
Uma matéria cumprida por duas equivalências ocupa duas linhas; a segunda só tem a metade
direita, e o script a junta à linha anterior.
"""

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

try:
    import pdfplumber
except ImportError:  # mensagem amigável em vez de um erro técnico
    sys.exit("Este script precisa do pdfplumber:  pip install pdfplumber")

VERSAO_DO_EXTRATOR = "0.1-beta"

# ----------------------------------------------------------------------------------------
# Onde fica cada coluna, como fração da largura da página (0 = borda esquerda, 1 = direita).
# Medido no BOA da UFRJ (página A4 na horizontal). Se o layout mudar, é aqui que se ajusta.
# ----------------------------------------------------------------------------------------
COLUNA_CODIGO_ESQUERDA = (0.00, 0.12)
COLUNA_NOME_ESQUERDA = (0.07, 0.31)
COLUNA_CREDITOS_ESQUERDA = (0.31, 0.36)
COLUNA_CARGA_HORARIA_ESQUERDA = (0.36, 0.40)
COLUNA_PERIODO = (0.40, 0.44)
COLUNA_CODIGO_DIREITA = (0.44, 0.50)
COLUNA_STATUS = (0.885, 1.01)
COLUNA_NUMEROS_DO_RESUMO = (0.24, 1.01)   # tabela 'Resumo': rótulo à esquerda, 6 números à direita

PADRAO_DE_CODIGO = re.compile(r"[A-Z]{3}[A-Z0-9]\d{2}")   # ICP131, MAE111, ICPX06, ICPZ55...
PADRAO_DE_NUMERO = re.compile(r"\d+(?:\.\d+)?")

# Tradução do texto do BOA para o status usado no JSON
STATUS_DO_BOA = {"facultada": "Facultada", "vedada": "Vedada", "cursando": "Cursando"}

# Rótulos da tabela "Resumo" (última página) -> chave no JSON
ROTULOS_DO_RESUMO = [("obrigat", "obrigatorias"), ("condicionada", "escolha_condicionada"),
                     ("restrita", "escolha_restrita_humanidades"), ("livre", "livre_escolha"),
                     ("extens", "extensao")]
CAMPOS_DO_RESUMO = ["total_creditos", "total_horas", "cumpridos_creditos", "cumpridos_horas",
                    "falta_creditos", "falta_horas"]


class ErroDeBOA(Exception):
    """O PDF não é um BOA legível, ou o layout mudou."""


# ----------------------------------------------------------------------------------------
# 1) Leitura do PDF: palavras com posição, agrupadas em linhas
# ----------------------------------------------------------------------------------------
def normalizar_texto(texto):
    return unicodedata.normalize("NFC", texto).casefold()


def ler_linhas_das_paginas(origem):
    """
    Devolve uma lista de páginas; cada página é uma lista de linhas; cada linha é uma lista
    de palavras (dicionários com 'texto', 'x' = posição relativa à largura e 'topo').
    """
    paginas = []
    with pdfplumber.open(origem) as pdf:
        for pagina in pdf.pages:
            palavras = pagina.extract_words(x_tolerance=2, y_tolerance=2)
            palavras.sort(key=lambda p: (p["top"], p["x0"]))
            linhas, topo_da_linha = [], None
            for palavra in palavras:
                item = {"texto": palavra["text"], "x": palavra["x0"] / pagina.width, "topo": palavra["top"]}
                if topo_da_linha is not None and abs(palavra["top"] - topo_da_linha) <= 2.5:
                    linhas[-1].append(item)
                else:
                    linhas.append([item])
                    topo_da_linha = palavra["top"]
            for linha in linhas:
                linha.sort(key=lambda p: p["x"])
            paginas.append(linhas)
    return paginas


def texto_da_linha(linha):
    return " ".join(p["texto"] for p in linha)


def palavras_na_faixa(linha, faixa):
    return [p for p in linha if faixa[0] <= p["x"] < faixa[1]]


def converter_numero(texto):
    """'4.0' -> 4.0; 'NCC' (sem crédito) -> 0.0; qualquer outra coisa -> None."""
    if texto == "NCC":
        return 0.0
    return float(texto) if PADRAO_DE_NUMERO.fullmatch(texto) else None


# ----------------------------------------------------------------------------------------
# 2) Cabeçalho: curso, versão curricular e data de emissão (sem nome nem matrícula)
# ----------------------------------------------------------------------------------------
def extrair_cabecalho(primeira_pagina):
    todas_as_palavras = [p for linha in primeira_pagina for p in linha]
    if not any("boletim de orientação acadêmica" in normalizar_texto(texto_da_linha(l)) for l in primeira_pagina):
        raise ErroDeBOA("Este PDF não parece ser um BOA (não encontrei o título do boletim).")

    # curso: "85783 - Ciência da Computação" (código de 5 dígitos, hífen e nome na mesma linha)
    curso = None
    for linha in primeira_pagina:
        for posicao, palavra in enumerate(linha):
            if re.fullmatch(r"\d{5}", palavra["texto"]) and posicao + 1 < len(linha) and linha[posicao + 1]["texto"] == "-":
                nome = " ".join(p["texto"] for p in linha[posicao + 2:] if p["x"] >= palavra["x"])
                curso = {"codigo": palavra["texto"], "nome": nome}
    versao = next((p["texto"] for p in todas_as_palavras if re.fullmatch(r"(?:19|20)\d{2}/[12]", p["texto"])), None)

    emitido_em = None
    for linha in primeira_pagina:
        for posicao, palavra in enumerate(linha[:-1]):
            if re.fullmatch(r"\d{2}/\d{2}/\d{4}", palavra["texto"]) and re.fullmatch(r"\d{2}:\d{2}", linha[posicao + 1]["texto"]):
                emitido_em = datetime.strptime(f'{palavra["texto"]} {linha[posicao + 1]["texto"]}',
                                               "%d/%m/%Y %H:%M").isoformat(timespec="minutes")

    if not curso or not versao:
        raise ErroDeBOA("Não consegui identificar o curso e a versão curricular no cabeçalho do BOA.")
    return curso, versao, emitido_em


# ----------------------------------------------------------------------------------------
# 3) Corpo: matérias cumpridas e pendentes
# ----------------------------------------------------------------------------------------
def descobrir_secao(texto):
    """Reconhece os títulos de seção do BOA. Devolve o nome da seção, ou None se a linha não for título."""
    t = normalizar_texto(texto)
    if "atividades acadêmicas obrigatórias" in t:
        return "obrigatoria"
    if "atividades acadêmicas optativas" in t:
        return "optativa_restrita_humanidades" if "escolha restrita" in t else "optativa_condicionada"
    if "cursadas e não explicitadas" in t:
        return "livre_escolha"
    if "observações finais" in t:
        return "observacoes"
    if t.strip() == "resumo":
        return "resumo"
    if "relatório de extensão" in t:
        return "extensao"
    return None


def interpretar_status(texto):
    for chave, status in STATUS_DO_BOA.items():
        if chave in normalizar_texto(texto):
            return status
    return None


def extrair_materias_e_resumo(paginas, avisos):
    cumpridas, pendentes, livre_escolha, resumo = [], [], [], {}
    secao = None
    ultima_cumprida = None   # para anexar a segunda equivalência, que vem na linha de baixo
    rotulo_do_resumo_pendente = ""   # rótulo comprido que quebra em duas linhas (números na de baixo)

    for numero_da_pagina, linhas in enumerate(paginas, start=1):
        for linha in linhas:
            nova_secao = descobrir_secao(texto_da_linha(linha))
            if nova_secao:
                secao, ultima_cumprida = nova_secao, None
                continue

            # ---------------------------------------------------- tabela "Resumo"
            if secao == "resumo":
                rotulo = normalizar_texto(" ".join(p["texto"] for p in linha if p["x"] < COLUNA_NUMEROS_DO_RESUMO[0]))
                numeros = [float(p["texto"]) for p in palavras_na_faixa(linha, COLUNA_NUMEROS_DO_RESUMO)
                           if PADRAO_DE_NUMERO.fullmatch(p["texto"])]
                if rotulo and len(numeros) < len(CAMPOS_DO_RESUMO):
                    rotulo_do_resumo_pendente = rotulo        # os números virão na linha seguinte
                    continue
                if not rotulo and numeros:
                    rotulo, rotulo_do_resumo_pendente = rotulo_do_resumo_pendente, ""
                chave = next((c for trecho, c in ROTULOS_DO_RESUMO if trecho in rotulo), None)
                if chave and len(numeros) == len(CAMPOS_DO_RESUMO):
                    resumo[chave] = dict(zip(CAMPOS_DO_RESUMO, numeros))
                continue

            # ---------------------------------------------------- tabela de livre escolha (uma metade só)
            if secao == "livre_escolha":
                codigos = [p for p in palavras_na_faixa(linha, COLUNA_CODIGO_ESQUERDA) if PADRAO_DE_CODIGO.fullmatch(p["texto"])]
                if codigos:
                    nome = " ".join(p["texto"] for p in palavras_na_faixa(linha, COLUNA_NOME_ESQUERDA)
                                    if not PADRAO_DE_CODIGO.fullmatch(p["texto"]))
                    creditos = next((converter_numero(p["texto"]) for p in palavras_na_faixa(linha, COLUNA_CREDITOS_ESQUERDA)), None)
                    horas = next((converter_numero(p["texto"]) for p in palavras_na_faixa(linha, COLUNA_CARGA_HORARIA_ESQUERDA)), None)
                    livre_escolha.append({"codigo": codigos[0]["texto"], "nome": nome, "creditos": creditos,
                                          "carga_horaria": int(horas) if horas is not None else None})
                continue

            # ---------------------------------------------------- tabelas com duas metades
            if secao not in ("obrigatoria", "optativa_condicionada", "optativa_restrita_humanidades"):
                continue
            codigo_esquerda = next((p["texto"] for p in palavras_na_faixa(linha, COLUNA_CODIGO_ESQUERDA)
                                    if PADRAO_DE_CODIGO.fullmatch(p["texto"])), None)
            codigo_direita = next((p["texto"] for p in palavras_na_faixa(linha, COLUNA_CODIGO_DIREITA)
                                   if PADRAO_DE_CODIGO.fullmatch(p["texto"])), None)

            if codigo_esquerda is None:
                # segunda equivalência da matéria anterior (só tem a metade direita)
                if codigo_direita and ultima_cumprida is not None:
                    ultima_cumprida["cursada_como"].append(codigo_direita)
                continue

            nome = " ".join(p["texto"] for p in palavras_na_faixa(linha, COLUNA_NOME_ESQUERDA)
                            if not PADRAO_DE_CODIGO.fullmatch(p["texto"]))
            creditos = next((converter_numero(p["texto"]) for p in palavras_na_faixa(linha, COLUNA_CREDITOS_ESQUERDA)), None)
            periodo = next((int(p["texto"]) for p in palavras_na_faixa(linha, COLUNA_PERIODO) if p["texto"].isdigit()), None)
            texto_do_status = " ".join(p["texto"] for p in palavras_na_faixa(linha, COLUNA_STATUS))
            status = interpretar_status(texto_do_status)

            if texto_do_status and status is None:
                avisos.append({"tipo": "status_desconhecido", "pagina": numero_da_pagina,
                               "detalhe": f"{codigo_esquerda}: {texto_do_status}"})
            if status:
                ultima_cumprida = None
                pendentes.append({"codigo": codigo_esquerda, "nome": nome, "secao": secao,
                                  "periodo": periodo, "creditos": creditos, "status": status})
            elif codigo_direita:
                ultima_cumprida = {"codigo": codigo_esquerda, "nome": nome, "secao": secao,
                                   "creditos": creditos, "cursada_como": [codigo_direita]}
                cumpridas.append(ultima_cumprida)
            else:
                ultima_cumprida = None
                avisos.append({"tipo": "linha_sem_status_nem_aprovacao", "pagina": numero_da_pagina,
                               "detalhe": f"{codigo_esquerda} - {nome}"})
    return cumpridas, pendentes, livre_escolha, resumo


# ----------------------------------------------------------------------------------------
# 4) Conferências (o que dá confiança de que a leitura está certa)
# ----------------------------------------------------------------------------------------
def conferir_com_resumo(cumpridas, pendentes, resumo, avisos):
    """Os créditos lidos linha a linha devem bater com a tabela 'Resumo' do próprio BOA."""
    por_secao = {"obrigatoria": "obrigatorias", "optativa_condicionada": "escolha_condicionada",
                 "optativa_restrita_humanidades": "escolha_restrita_humanidades"}
    resultado = {}
    for secao, chave in por_secao.items():
        if chave not in resumo:
            avisos.append({"tipo": "resumo_ausente", "detalhe": f"não achei a linha '{chave}' no Resumo"})
            continue
        cumpridos = sum(c["creditos"] or 0 for c in cumpridas if c["secao"] == secao)
        if secao == "obrigatoria":  # nas obrigatórias, o 'falta cumprir' é a soma das pendentes
            faltam = sum(p["creditos"] or 0 for p in pendentes if p["secao"] == secao)
            confere = cumpridos == resumo[chave]["cumpridos_creditos"] and faltam == resumo[chave]["falta_creditos"]
        else:  # nas optativas, só as cumpridas são comparáveis (as pendentes são um cardápio)
            confere = cumpridos == resumo[chave]["cumpridos_creditos"]
        resultado[chave] = confere
        if not confere:
            avisos.append({"tipo": "creditos_nao_batem_com_o_resumo", "detalhe":
                           f"{chave}: lido {cumpridos} créditos cumpridos; o Resumo diz {resumo[chave]['cumpridos_creditos']}"})
    return resultado


def conferir_com_curriculo(dados, caminho_do_curriculo, avisos):
    """Confere versão e códigos com o JSON do currículo e testa se o status bate com os pré-requisitos."""
    with open(caminho_do_curriculo, encoding="utf-8") as arquivo:
        curriculo = json.load(arquivo)
    meta, disciplinas = curriculo["_meta"], curriculo["disciplinas"]
    apelidos, extras = curriculo.get("alias_codigo", {}), curriculo.get("equivalencias_extras_de_requisito", [])

    if dados["versao_curricular"] != meta["versao_curricular"] or dados["curso"]["codigo"] != meta["curso_codigo"]:
        avisos.append({"tipo": "curriculo_diferente", "detalhe":
                       f"BOA: {dados['curso']['codigo']} {dados['versao_curricular']}; "
                       f"currículo carregado: {meta['curso_codigo']} {meta['versao_curricular']}"})
        return {"executada": False}

    desconhecidos = sorted({m["codigo"] for m in dados["cumpridas"] + dados["pendentes"] if m["codigo"] not in disciplinas})
    for codigo in desconhecidos:
        avisos.append({"tipo": "codigo_fora_do_curriculo", "detalhe": codigo})

    feitas = {m["codigo"] for m in dados["cumpridas"]}

    def requisito_satisfeito(requisito):
        if requisito in feitas or apelidos.get(requisito) in feitas:
            return True
        return any(x["codigo"] == requisito and any(all(c in feitas for c in alternativa) for alternativa in x["alternativas"])
                   for x in extras)

    coincidem, divergem = 0, []
    for materia in dados["pendentes"]:
        if materia["status"] == "Cursando" or materia["codigo"] not in disciplinas:
            continue
        liberada = all(requisito_satisfeito(r) for r in disciplinas[materia["codigo"]]["requisitos"])
        previsto = "Facultada" if liberada else "Vedada"
        if previsto == materia["status"]:
            coincidem += 1
        else:
            divergem.append(materia["codigo"])
            avisos.append({"tipo": "status_diferente_do_previsto_pelos_pre_requisitos",
                           "detalhe": f'{materia["codigo"]}: BOA diz {materia["status"]}, pré-requisitos indicam {previsto} '
                                      "(vale o status do BOA)"})
    return {"executada": True, "status_coincidem": coincidem, "status_divergem": divergem,
            "codigos_fora_do_curriculo": desconhecidos}


# ----------------------------------------------------------------------------------------
# 5) Função principal
# ----------------------------------------------------------------------------------------
def extrair_boa(origem, caminho_do_curriculo=None):
    """`origem` pode ser um caminho ou um arquivo aberto em modo binário (ex.: upload do Streamlit)."""
    paginas = ler_linhas_das_paginas(origem)
    if not paginas or sum(len(linha) for pagina in paginas for linha in pagina) < 50:
        raise ErroDeBOA("O PDF não tem texto legível (talvez seja uma imagem escaneada).")

    curso, versao, emitido_em = extrair_cabecalho(paginas[0])
    avisos = []
    cumpridas, pendentes, livre_escolha, resumo = extrair_materias_e_resumo(paginas, avisos)
    if not cumpridas and not pendentes:
        raise ErroDeBOA("Não encontrei nenhuma matéria nas tabelas. O layout do BOA pode ter mudado.")

    dados = {
        "_meta": {"extrator": f"extrator_boa.py {VERSAO_DO_EXTRATOR}", "paginas": len(paginas),
                  "extraido_em": datetime.now().isoformat(timespec="seconds"),
                  "observacao": "Sem nome, matrícula ou notas, de propósito."},
        "curso": curso,
        "versao_curricular": versao,
        "emitido_em": emitido_em,
        "cumpridas": cumpridas,
        "pendentes": pendentes,
        "livre_escolha_cursadas": livre_escolha,
        "resumo": resumo,
    }
    dados["conferencias"] = {"resumo_do_boa": conferir_com_resumo(cumpridas, pendentes, resumo, avisos)}
    if caminho_do_curriculo:
        dados["conferencias"]["curriculo"] = conferir_com_curriculo(dados, caminho_do_curriculo, avisos)
    dados["avisos"] = avisos
    return dados


def imprimir_resumo(dados):
    contagem_status = {}
    for materia in dados["pendentes"]:
        contagem_status[materia["status"]] = contagem_status.get(materia["status"], 0) + 1
    print(f'Curso: {dados["curso"]["codigo"]} - {dados["curso"]["nome"]} | versão {dados["versao_curricular"]} '
          f'| emitido em {dados["emitido_em"]}')
    print(f'Cumpridas: {len(dados["cumpridas"])} | pendentes: {len(dados["pendentes"])} {contagem_status} '
          f'| livre escolha cursada: {len(dados["livre_escolha_cursadas"])}')
    print("Créditos batem com o Resumo do BOA:", dados["conferencias"]["resumo_do_boa"])
    curriculo = dados["conferencias"].get("curriculo")
    if curriculo and curriculo.get("executada"):
        print(f'Status x pré-requisitos: {curriculo["status_coincidem"]} coincidem, '
              f'{len(curriculo["status_divergem"])} divergem {curriculo["status_divergem"]}')
    tipos = {}
    for aviso in dados["avisos"]:
        tipos[aviso["tipo"]] = tipos.get(aviso["tipo"], 0) + 1
    print("Avisos:", tipos or "nenhum")


def main():
    analisador = argparse.ArgumentParser(description="Extrai matérias cumpridas e pendentes de um BOA da UFRJ (PDF).")
    analisador.add_argument("pdf", help="arquivo do BOA")
    analisador.add_argument("--curriculo", help="JSON do currículo, para conferir versão, códigos e status")
    analisador.add_argument("--saida", default="boa_extraido.json", help="JSON de saída (padrão: boa_extraido.json)")
    argumentos = analisador.parse_args()
    try:
        dados = extrair_boa(argumentos.pdf, argumentos.curriculo)
    except ErroDeBOA as erro:
        sys.exit(f"ERRO: {erro}")
    with open(argumentos.saida, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
    imprimir_resumo(dados)
    print(f"JSON salvo em: {argumentos.saida}")


if __name__ == "__main__":
    main()
