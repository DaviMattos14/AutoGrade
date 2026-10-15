"""Parser do currículo do SIGA/UFRJ.

Entrada: a página `repositorio-curriculo/distribuicoes/<id>.html` (a que contém a
tabela de verdade; as outras, `<id>.html` e `combo<id>.html`, são só molduras de frame).
O SIGA serve a página em windows-1252, então os bytes são lidos e decodificados aqui.

Saída: objeto `Curriculo` com disciplinas, pré-requisitos, equivalências e exigências,
mais utilitários para checar pré-requisitos a partir de um conjunto de disciplinas
concluídas (por exemplo, as extraídas do boletim).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

from bs4 import BeautifulSoup

COD = r"[A-Z]{3}[A-Z0-9]{3}"
RE_FULL_COD = re.compile(rf"^{COD}$")
RE_REQ = re.compile(rf"({COD})\s*\(([A-Z])\)")          # "ICP131 (P)"
RE_EQ_LINE = re.compile(rf"^\s*({COD})\s*=\s*(.+?)\s*$")  # "ICP131 = ICP037 + ICP121"
RE_COD_PAREN = re.compile(rf"({COD})\s*\(")               # "ICP131 ( Nome )"


@dataclass
class Disciplina:
    codigo: str
    nome: str
    creditos: float
    ch_teorica: int
    ch_pratica: int
    ch_extensao: int
    grupo: str                      # obrigatoria | condicionada | restrita
    periodo: int | None = None      # só para obrigatórias
    subgrupo: str | None = None     # ex.: "Humanidades" (escolha restrita)
    requisitos: list[str] = field(default_factory=list)  # pré-requisitos (P)
    requisitos_tipo: dict[str, str] = field(default_factory=dict)  # código -> "P"

    @property
    def ch_total(self) -> int:
        return self.ch_teorica + self.ch_pratica + self.ch_extensao


@dataclass
class Bloco:
    """Linha sem código (ex.: 'Atividades Academicas Optativas 8.0') dentro de um período."""
    periodo: int
    nome: str
    categoria: str                  # condicionada | restrita_humanidades | livre_escolha
    creditos: float
    ch: int


class Curriculo:
    def __init__(self) -> None:
        self.meta: dict[str, str] = {}
        self.disciplinas: dict[str, Disciplina] = {}
        self.blocos: list[Bloco] = []
        self.totais_periodo: dict[int, float] = {}
        self.creditos_a_cumprir: dict[str, float] = {}   # restrita / condicionada
        self.exigencias: dict[str, dict[str, float]] = {}
        self.equacoes: list[dict] = []        # equações globais (esquerda = direita)
        self.equiv_codigo_anterior: list[dict] = []
        # código -> lista de alternativas; cada alternativa é um conjunto de códigos
        # que, juntos, substituem o código (AND dentro da alternativa, OR entre elas)
        self.equiv: dict[str, list[frozenset[str]]] = {}

    # ------------------------------------------------------------------ consultas
    def satisfaz(self, req: str, concluidas: set[str]) -> bool:
        if req in concluidas:
            return True
        return any(alt <= concluidas for alt in self.equiv.get(req, []))

    def pendencias(self, codigo: str, concluidas: set[str]) -> list[str]:
        d = self.disciplinas[codigo]
        return [r for r in d.requisitos if not self.satisfaz(r, concluidas)]

    # ------------------------------------------------------------------ saída
    def to_dict(self) -> dict:
        return {
            "meta": self.meta,
            "disciplinas": {k: asdict(v) for k, v in self.disciplinas.items()},
            "blocos": [asdict(b) for b in self.blocos],
            "totais_periodo": self.totais_periodo,
            "creditos_a_cumprir": self.creditos_a_cumprir,
            "exigencias": self.exigencias,
            "equacoes": self.equacoes,
            "equiv_codigo_anterior": self.equiv_codigo_anterior,
            "equiv": {k: [sorted(a) for a in v] for k, v in self.equiv.items()},
        }

    def salvar_json(self, caminho: str | Path) -> None:
        Path(caminho).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8"
        )

    # ------------------------------------------------------------------ validação
    def validar(self) -> list[str]:
        """Confere os totais de créditos por período contra os totais impressos na página."""
        avisos = []
        for per, total in sorted(self.totais_periodo.items()):
            soma = sum(d.creditos for d in self.disciplinas.values() if d.periodo == per)
            soma += sum(b.creditos for b in self.blocos if b.periodo == per)
            if abs(soma - total) > 1e-6:
                avisos.append(f"{per}º período: soma {soma} != total {total}")
        for cod, d in self.disciplinas.items():
            for r in d.requisitos:
                if r not in self.disciplinas and r not in self.equiv:
                    avisos.append(f"{cod}: requisito {r} sem equivalência conhecida")
        return avisos


# ---------------------------------------------------------------------- parsing
def _decodificar(caminho: Path) -> str:
    dados = caminho.read_bytes()
    try:
        return dados.decode("cp1252")
    except UnicodeDecodeError:
        return dados.decode("latin-1")


def _num(txt: str) -> float:
    return float(txt.replace(",", "."))


def _codigos_paren(txt: str) -> list[str]:
    return RE_COD_PAREN.findall(txt)


def _add_equiv(equiv: dict, alvo: str, alt: list[str]) -> None:
    conj = frozenset(alt)
    lista = equiv.setdefault(alvo, [])
    if conj not in lista:
        lista.append(conj)


def carregar(caminho: str | Path) -> Curriculo:
    caminho = Path(caminho)
    soup = BeautifulSoup(_decodificar(caminho), "lxml")
    cur = Curriculo()

    modo = "inicio"          # inicio | periodos | restrita | condicionada | exigencias | equacoes | anterior
    periodo: int | None = None
    subgrupo: str | None = None
    ultimo_esq: list[str] = []

    for tr in soup.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue
        classes = tr.get("class", [])
        textos = [t.get_text(" ", strip=True) for t in tds]

        # --- cabeçalhos de seção -------------------------------------------------
        if len(tds) == 1 and "tableTitle" in classes:
            t = textos[0]
            m = re.match(r"(\d+)º Período", t)
            if m:
                modo, periodo, subgrupo = "periodos", int(m.group(1)), None
            elif "Escolha Restrita" in t:
                modo, periodo, subgrupo = "restrita", None, None
            elif "Escolha Condicionada" in t:
                modo, periodo, subgrupo = "condicionada", None, None
            elif t.startswith("Grupo "):
                subgrupo = t[len("Grupo "):].strip()
            elif "Para fazer jus" in t:
                modo = "exigencias"
            continue
        if len(tds) == 1 and "tableTitleBlue" in classes:
            t = textos[0]
            if t.startswith("Equações de Equivalência"):
                modo = "equacoes"
            elif t.startswith("Equivalências por Código Anterior"):
                modo = "anterior"
            continue

        # --- metadados do curso ----------------------------------------------------
        if modo == "inicio" and len(tds) in (2, 4):
            for i in range(0, len(tds) - 1, 2):
                chave = textos[i].rstrip(":").strip()
                if chave in {"Código", "Denominação Oficial", "Situação", "Modalidade"}:
                    cur.meta[chave] = textos[i + 1]
            continue

        # --- totais ----------------------------------------------------------------
        if len(tds) == 3 and "tableTitleBlue" in classes:
            if textos[0].startswith("Total de Créditos") and periodo is not None:
                cur.totais_periodo[periodo] = _num(textos[1])
            elif textos[0].startswith("Créditos a cumprir"):
                cur.creditos_a_cumprir[modo] = _num(textos[1])
            continue

        # --- exigências para o diploma ---------------------------------------------
        if modo == "exigencias" and len(tds) == 3:
            try:
                cur.exigencias[textos[0]] = {
                    "creditos": _num(textos[1]), "horas": _num(textos[2])
                }
            except ValueError:
                pass            # linha de cabeçalho
            continue

        # --- equações globais e equivalências por código anterior -------------------
        if modo in ("equacoes", "anterior") and len(tds) == 4 and textos[2] == "=":
            esq = _codigos_paren(textos[1]) or ultimo_esq
            dir_ = _codigos_paren(textos[3])
            ultimo_esq = esq
            item = {"id": textos[0].strip(" :[]") or None, "esquerda": esq, "direita": dir_}
            (cur.equacoes if modo == "equacoes" else cur.equiv_codigo_anterior).append(item)
            continue

        # --- disciplinas -----------------------------------------------------------
        if modo in ("periodos", "restrita", "condicionada"):
            if len(tds) == 7 and RE_FULL_COD.match(textos[0]):
                grupo = "obrigatoria" if modo == "periodos" else modo
                cod = textos[0]
                if cod in cur.disciplinas:
                    raise ValueError(f"disciplina duplicada no currículo: {cod}")
                linhas = [l.strip() for l in tds[6].get_text("\n").split("\n") if l.strip()]
                reqs: dict[str, str] = {}
                for lin in linhas:
                    eq = RE_EQ_LINE.match(lin)
                    if eq:
                        alvo, resto = eq.groups()
                        _add_equiv(cur.equiv, alvo, [c.strip() for c in resto.split("+")])
                    else:
                        for c, tipo in RE_REQ.findall(lin):
                            reqs[c] = tipo
                cur.disciplinas[cod] = Disciplina(
                    codigo=cod, nome=textos[1], creditos=_num(textos[2]),
                    ch_teorica=int(textos[3]), ch_pratica=int(textos[4]),
                    ch_extensao=int(textos[5]), grupo=grupo,
                    periodo=periodo if modo == "periodos" else None,
                    subgrupo=subgrupo if modo == "restrita" else None,
                    requisitos=list(reqs), requisitos_tipo=reqs,
                )
            elif len(tds) == 6 and modo == "periodos" and not RE_FULL_COD.match(textos[0]):
                nome = textos[0]
                cat = ("livre_escolha" if "Livre Escolha" in nome
                       else "restrita_humanidades" if "Humanidades" in nome
                       else "condicionada")
                cur.blocos.append(Bloco(periodo or 0, nome, cat, _num(textos[1]),
                                        int(textos[2]) + int(textos[3]) + int(textos[4])))

    # --- equivalências derivadas das equações globais ----------------------------------
    for eq in cur.equacoes + cur.equiv_codigo_anterior:
        esq, dir_ = eq["esquerda"], eq["direita"]
        for x in esq:                    # a direita (inteira) substitui cada código da esquerda
            _add_equiv(cur.equiv, x, dir_)
        if len(dir_) == 1:               # código legado único: a esquerda inteira o substitui
            _add_equiv(cur.equiv, dir_[0], esq)
    return cur


if __name__ == "__main__":
    import sys
    c = carregar(sys.argv[1])
    print(c.meta)
    print(len(c.disciplinas), "disciplinas;", len(c.blocos), "blocos;", len(c.equacoes), "equações")
    print("avisos:", c.validar() or "nenhum")
