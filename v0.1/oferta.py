"""Parser da planilha de oferta de turmas ("Planejado <período> - Visualização").

A aba *Turmas* tem layout empilhado: a linha de cabeçalho de cada turma traz docente,
disciplina, período/tipo, número SIGA etc.; as linhas seguintes continuam a mesma turma,
cada uma com (no máximo) uma restrição de curso (com suas vagas) e um bloco de aula
(dia, horário, tipo, sala). Aceita o .xlsx ou o .csv exportado da mesma aba.

A aba *Grades* é só uma visão em grade horária dos mesmos dados e não é necessária.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

import pandas as pd

COD_DISC = re.compile(r"^([A-Z]{3}[A-Z0-9]{3})\s*-\s*(.+)$")
RE_HORARIO = re.compile(
    r"^\s*(\d{1,2})(?:[h:](\d{2}))?\s*-\s*(\d{1,2})(?:[h:](\d{2}))?\s*h?\s*$", re.I
)
DIAS = {"SEG": 0, "TER": 1, "QUA": 2, "QUI": 3, "SEX": 4, "SAB": 5, "SÁB": 5, "DOM": 6}


@dataclass
class Aula:
    dia: str                 # SEG, TER, ...
    ini: int                 # minutos desde 00:00
    fim: int
    tipo: str | None         # T (teórica) | P (prática)
    sala: str | None
    lotacao: int | None


@dataclass
class Restricao:
    curso: str               # ex.: "BCC1"
    nome: str | None
    vagas: int | None


@dataclass
class Turma:
    numero: str | None            # número SIGA da turma
    codigo: str                   # código da disciplina
    nome: str
    periodo_tipo: str             # ex.: "6 T1", "Elet", "SVÇ"
    periodo_rec: int | None       # período recomendado, quando houver
    turma: str | None             # ex.: "T1"
    horas: float | None           # coluna "Horas" da planilha
    docentes: list[str] = field(default_factory=list)
    abrir: bool | None = None
    restricao_flag: str | None = None
    restricoes: list[Restricao] = field(default_factory=list)
    aulas: list[Aula] = field(default_factory=list)
    horario_indefinido: bool = False   # havia aula sem horário ("?")

    def vagas_para(self, curso: str) -> int | None:
        for r in self.restricoes:
            if r.curso == curso:
                return r.vagas
        return None


def _vazio(x) -> bool:
    return x is None or (isinstance(x, float) and pd.isna(x)) or str(x).strip() == ""


def _txt(x) -> str | None:
    return None if _vazio(x) else str(x).strip()


def _int(x) -> int | None:
    if _vazio(x):
        return None
    try:
        return int(float(str(x).replace(",", ".")))
    except ValueError:
        return None


def parse_horario(txt: str) -> tuple[int, int] | None:
    m = RE_HORARIO.match(txt)
    if not m:
        return None
    h1, m1, h2, m2 = m.groups()
    return int(h1) * 60 + int(m1 or 0), int(h2) * 60 + int(m2 or 0)


def _ler_tabela(caminho: Path, aba: str) -> pd.DataFrame:
    if caminho.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(caminho, sheet_name=aba, header=None)
    return pd.read_csv(caminho, header=None, dtype=object, keep_default_na=True)


def carregar(caminho: str | Path, aba: str = "Turmas") -> tuple[list[Turma], list[str]]:
    """Retorna (turmas, avisos). Linhas de aula que não puderam ser lidas viram avisos."""
    caminho = Path(caminho)
    df = _ler_tabela(caminho, aba)
    avisos: list[str] = []
    turmas: list[Turma] = []
    atual: Turma | None = None

    for i, r in df.iterrows():
        disc = _txt(r[1])
        m = COD_DISC.match(disc) if disc else None
        if m:                                           # cabeçalho de nova turma
            per = _txt(r[2]) or ""
            mp = re.match(r"^(\d+)\s*(T\d+)?", per)
            atual = Turma(
                numero=(str(_int(r[7])) if _int(r[7]) is not None else None),
                codigo=m.group(1), nome=m.group(2).strip(), periodo_tipo=per,
                periodo_rec=int(mp.group(1)) if mp else None,
                turma=(mp.group(2) if mp and mp.group(2) else None),
                horas=float(r[3]) if not _vazio(r[3]) else None,
                abrir=(None if _vazio(r[6]) else str(r[6]).strip().upper() == "SIM"),
                restricao_flag=_txt(r[8]),
            )
            turmas.append(atual)
            if _txt(r[0]):
                atual.docentes.append(_txt(r[0]))
        elif atual is None:
            continue                                    # banner / cabeçalhos da planilha
        elif _txt(r[0]) and not disc and _txt(r[0]) not in atual.docentes:
            atual.docentes.append(_txt(r[0]))           # docente adicional

        if atual is None:
            continue
        if _txt(r[5]):                                  # restrição de curso desta linha
            cod, _, nome = _txt(r[5]).partition(" - ")
            atual.restricoes.append(Restricao(cod.strip(), nome.strip() or None, _int(r[4])))
        if _txt(r[9]) or _txt(r[10]):                   # bloco de aula desta linha
            dia = (_txt(r[9]) or "").upper()
            hor = parse_horario(_txt(r[10]) or "")
            if dia in DIAS and hor:
                atual.aulas.append(Aula(dia, hor[0], hor[1], _txt(r[11]), _txt(r[12]), _int(r[14])))
            else:
                atual.horario_indefinido = True
                avisos.append(f"linha {i}: {atual.codigo} {atual.periodo_tipo} "
                              f"aula sem horário legível (dia={_txt(r[9])!r}, hor={_txt(r[10])!r})")
    return turmas, avisos


def conflita(a: Turma, b: Turma) -> bool:
    """Há choque de horário entre as duas turmas?"""
    for x in a.aulas:
        for y in b.aulas:
            if x.dia == y.dia and x.ini < y.fim and y.ini < x.fim:
                return True
    return False


def para_dataframe(turmas: list[Turma]) -> pd.DataFrame:
    linhas = []
    for t in turmas:
        d = asdict(t)
        d["docentes"] = "; ".join(t.docentes)
        d["horarios"] = "; ".join(f"{a.dia} {a.ini // 60:02d}:{a.ini % 60:02d}-"
                                  f"{a.fim // 60:02d}:{a.fim % 60:02d}" for a in t.aulas)
        d["restricoes"] = "; ".join(f"{r.curso}={r.vagas}" for r in t.restricoes)
        d.pop("aulas")
        linhas.append(d)
    return pd.DataFrame(linhas)


if __name__ == "__main__":
    import sys
    ts, av = carregar(sys.argv[1])
    print(len(ts), "turmas;", len(av), "avisos")
    for a in av[:10]:
        print(" ", a)
