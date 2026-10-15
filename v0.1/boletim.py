"""Parser do Boletim de Orientação Acadêmica (UFRJ, PDF).

O texto corrido do PDF mistura as duas colunas (elenco recomendado × atividades já
aprovadas), então a leitura é feita por *coordenadas*: cada palavra é atribuída a uma
coluna pelo seu x0 e as palavras são agrupadas em linhas pelo y.

Estrutura do boletim:
  - cada disciplina recomendada (esquerda) pode ter 0, 1 ou mais disciplinas aprovadas
    equivalentes (direita; mais de uma ocupa linhas extras, com a esquerda em branco);
  - a última coluna traz a situação: "Cursando", "Inscrição Facultada", "Inscrição Vedada".

Por privacidade, nome e matrícula do aluno NÃO são extraídos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

import pdfplumber

COD = re.compile(r"^[A-Z]{3}[A-Z0-9]{3}$")

# limites de coluna (x0, em pontos; página A4 paisagem de 842 pt)
COLS = [
    ("l_cod", 0, 70), ("l_nome", 70, 268), ("l_cred", 268, 308), ("l_ch", 308, 348),
    ("l_per", 348, 380),
    ("r_cod", 380, 430), ("r_nome", 430, 630), ("r_cred", 630, 670), ("r_ch", 670, 705),
    ("r_grau", 705, 739),
    ("status", 739, 900),
]


@dataclass
class Aprovada:
    codigo: str
    nome: str
    creditos: float | None
    ch: int | None
    grau: float | None


@dataclass
class Item:
    codigo: str
    nome: str
    creditos: float | None
    ch: int | None
    secao: str                      # obrigatorias | condicionada | restrita
    periodo: int | None = None      # período recomendado (obrigatórias)
    subgrupo: str | None = None     # ex.: "Humanidades"
    situacao: str | None = None     # Cursando | Inscrição Facultada | Inscrição Vedada
    aprovadas: list[Aprovada] = field(default_factory=list)

    @property
    def cumprida(self) -> bool:
        return bool(self.aprovadas)


@dataclass
class Boletim:
    meta: dict[str, str] = field(default_factory=dict)
    itens: list[Item] = field(default_factory=list)
    nao_explicitadas: list[Aprovada] = field(default_factory=list)
    resumo: dict[str, dict[str, float]] = field(default_factory=dict)

    # ----------------------------------------------------------- consultas úteis
    def concluidas(self) -> set[str]:
        """Todos os códigos concluídos: os aprovados de fato (direita), os códigos
        recomendados que ficaram satisfeitos por equivalência e as cursadas não explicitadas."""
        s = {a.codigo for it in self.itens for a in it.aprovadas}
        s |= {it.codigo for it in self.itens if it.cumprida}
        s |= {a.codigo for a in self.nao_explicitadas}
        return s

    def cursando(self) -> set[str]:
        return {it.codigo for it in self.itens if it.situacao == "Cursando"}

    def pendentes(self, secao: str | None = None) -> list[Item]:
        return [it for it in self.itens
                if not it.cumprida and (secao is None or it.secao == secao)]

    def to_dict(self) -> dict:
        return {"meta": self.meta, "itens": [asdict(i) for i in self.itens],
                "nao_explicitadas": [asdict(a) for a in self.nao_explicitadas],
                "resumo": self.resumo}


# ------------------------------------------------------------------ utilitários
def _f(txt: str) -> float | None:
    try:
        return float(txt.replace(",", "."))
    except ValueError:
        return None


def _i(txt: str) -> int | None:
    v = _f(txt)
    return int(v) if v is not None else None


def _linhas(page) -> list[list[dict]]:
    ws = sorted(page.extract_words(x_tolerance=1.5, y_tolerance=2), key=lambda w: w["top"])
    linhas: list[list[dict]] = []
    for w in ws:
        if linhas and abs(w["top"] - linhas[-1][0]["top"]) <= 2.5:
            linhas[-1].append(w)
        else:
            linhas.append([w])
    return [sorted(l, key=lambda w: w["x0"]) for l in linhas]


def _colunas(linha: list[dict]) -> dict[str, str]:
    out: dict[str, list[str]] = {}
    for w in linha:
        for nome, lo, hi in COLS:
            if lo <= w["x0"] < hi:
                out.setdefault(nome, []).append(w["text"])
                break
    return {k: " ".join(v) for k, v in out.items()}


def _secao(texto: str) -> str | None:
    if "Cursadas e Não Explicitadas" in texto:
        return "nao_explicitadas"
    if "Atividades Acadêmicas Obrigatórias" in texto:
        return "obrigatorias"
    if "Atividades Acadêmicas Optativas (Escolha Restrita)" in texto:
        return "restrita"
    if texto.strip() == "Atividades Acadêmicas Optativas":
        return "condicionada"
    if "Observações Finais" in texto:
        return "obs"
    if texto.strip() == "Resumo":
        return "resumo"
    if "Relatório de Extensão" in texto:
        return "extensao"
    return None


_ROTULOS_RESUMO = {
    "obrigatórias": "obrigatorias",
    "escolha condicionada": "condicionada",
    "escolha restrita - grupo humanidades": "restrita_humanidades",
    "livre escolha": "livre_escolha",
    "extensão": "extensao",
}


# ---------------------------------------------------------------------- parsing
def carregar(caminho: str | Path) -> Boletim:
    b = Boletim()
    secao: str | None = None
    subgrupo: str | None = None
    ultimo: Item | None = None
    pendente: str | None = None

    with pdfplumber.open(str(caminho)) as pdf:
        # --- metadados (página 1), sem dados pessoais ---------------------------------
        t1 = pdf.pages[0].extract_text() or ""
        m = re.search(r"\b(\d{5}) - ([^\n]+?)\s*(?:\n|$)", t1)
        if m:
            b.meta["curso"] = f"{m.group(1)} - {m.group(2).strip()}"
        m = re.search(r"\b(20\d\d/[12])\b", t1)
        if m:
            b.meta["versao_curricular"] = m.group(1)
        m = re.search(r"\b(\d{2}/\d{2}/\d{4} \d{2}:\d{2})\b", t1)
        if m:
            b.meta["emissao"] = m.group(1)

        for page in pdf.pages:
            for linha in _linhas(page):
                texto = " ".join(w["text"] for w in linha)
                nova = _secao(texto)
                if nova:
                    secao, subgrupo, ultimo = nova, None, None
                    continue
                if texto.startswith("Grupo ") and secao == "restrita":
                    subgrupo = texto[len("Grupo "):].strip()
                    continue
                c = _colunas(linha)

                if secao in ("obrigatorias", "condicionada", "restrita"):
                    lc, rc = c.get("l_cod", ""), c.get("r_cod", "")
                    if COD.match(lc):
                        ultimo = Item(
                            codigo=lc, nome=c.get("l_nome", ""), creditos=_f(c.get("l_cred", "")),
                            ch=_i(c.get("l_ch", "")), secao=secao,
                            periodo=_i(c.get("l_per", "")) if secao == "obrigatorias" else None,
                            subgrupo=subgrupo if secao == "restrita" else None,
                        )
                        b.itens.append(ultimo)
                    elif not lc and ultimo is None:
                        continue
                    if ultimo is not None and COD.match(rc) and (COD.match(lc) or not lc):
                        ultimo.aprovadas.append(Aprovada(
                            rc, c.get("r_nome", ""), _f(c.get("r_cred", "")),
                            _i(c.get("r_ch", "")), _f(c.get("r_grau", ""))))
                    if ultimo is not None and c.get("status") and (COD.match(lc) or not lc):
                        ultimo.situacao = c["status"]

                elif secao == "nao_explicitadas":
                    if COD.match(c.get("l_cod", "")):
                        b.nao_explicitadas.append(Aprovada(
                            c["l_cod"], c.get("l_nome", ""), _f(c.get("l_cred", "")),
                            _i(c.get("l_ch", "")), _f(c.get("l_per", ""))))

                elif secao == "resumo":
                    rotulo = re.split(r"\s\d", texto, maxsplit=1)[0].strip().lower()
                    chave = _ROTULOS_RESUMO.get(rotulo)
                    nums = re.findall(r"\d+(?:\.\d+)?", texto)
                    if chave and len(nums) < 6:
                        pendente = chave        # rótulo e números caem em linhas vizinhas
                        continue
                    if not chave and len(nums) >= 6 and pendente:
                        chave, pendente = pendente, None
                    if chave and len(nums) >= 6:
                        v = [float(x) for x in nums[-6:]]
                        b.resumo[chave] = {
                            "total_cred": v[0], "total_ch": v[1], "cumprido_cred": v[2],
                            "cumprido_ch": v[3], "falta_cred": v[4], "falta_ch": v[5]}
    return b


if __name__ == "__main__":
    import sys
    bol = carregar(sys.argv[1])
    print(bol.meta)
    print(len(bol.itens), "itens;", len(bol.nao_explicitadas), "não explicitadas")
    print("resumo:", bol.resumo)
