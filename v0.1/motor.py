"""Motor de montagem de grade (OR-Tools CP-SAT).

Escolhe, entre as turmas ofertadas das disciplinas que o aluno *pode* cursar, o conjunto
que maximiza a pontuação abaixo, respeitando choques de horário, uma turma por disciplina,
o limite de créditos e o que ainda falta em cada bloco do currículo.

Pontuação (maximizar):
  + obrigatórias: `obrigatoria_por_credito` por crédito
  + obrigatórias que destravam outras: `dependente` por disciplina pendente que depende
    dela, direta ou indiretamente (ex.: ICP472 destrava ICPK01)
  + optativas (escolha condicionada / restrita): `optativa_por_credito`, só até o que falta
    no bloco, para não pegar optativa que não conta
  - buracos: `buraco_por_minuto` por minuto livre entre a primeira e a última aula do dia
  - créditos de optativa que passam do que falta no bloco: `credito_excedente` por crédito

Premissa configurável: disciplinas "Cursando" são tratadas como aprovadas ao planejar o
próximo período (`assumir_cursando_aprovado`).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

import boletim as B
import curriculo as C
import oferta as O

ORDEM_DIAS = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB"]


@dataclass
class Pesos:
    obrigatoria_por_credito: int = 100
    dependente: int = 100
    optativa_por_credito: int = 30
    buraco_por_minuto: int = 1
    credito_excedente: int = 5       # pontos perdidos por crédito de optativa que não conta


@dataclass
class Selecao:
    turmas: list[O.Turma]
    secoes: dict[str, str]                 # código -> obrigatorias | condicionada | restrita
    creditos: float
    buracos_min: dict[str, int]            # dia -> minutos livres entre aulas
    pontos: float
    destrava: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class Diagnostico:
    n_candidatos: int
    falta: dict[str, float]                # créditos que ainda faltam por bloco
    premissas: list[str]


def _c10(x: float | None) -> int:
    return int(round((x or 0.0) * 10))


def dependentes(cur: C.Curriculo, pendentes: set[str]) -> dict[str, list[str]]:
    """Para cada disciplina pendente, as pendentes que dependem dela (transitivo)."""
    filhos: dict[str, set[str]] = {c: set() for c in pendentes}
    for d in pendentes:
        if d not in cur.disciplinas:
            continue
        for r in cur.disciplinas[d].requisitos:
            supridores = {r} | {c for alt in cur.equiv.get(r, []) for c in alt}
            for c in supridores & pendentes:
                if c != d:
                    filhos[c].add(d)
    saida: dict[str, list[str]] = {}
    for c in pendentes:
        vistos: set[str] = set()
        pilha = list(filhos[c])
        while pilha:
            x = pilha.pop()
            if x not in vistos:
                vistos.add(x)
                pilha.extend(filhos[x])
        saida[c] = sorted(vistos)
    return saida


def candidatos(cur, bol, turmas, curso, assumir_cursando, exigir_vaga):
    cursando = bol.cursando()
    concl = bol.concluidas() | (cursando if assumir_cursando else set())
    por_cod: dict[str, list[O.Turma]] = {}
    for t in turmas:
        por_cod.setdefault(t.codigo, []).append(t)
    cand = []
    for it in bol.pendentes():
        if it.codigo in cursando or cur.pendencias(it.codigo, concl):
            continue
        for t in por_cod.get(it.codigo, []):
            if not t.aulas or t.abrir is False:
                continue
            v = t.vagas_para(curso)
            if exigir_vaga and not (v and v > 0):
                continue
            cand.append((it, t))
    return cand


def _faltas(bol: B.Boletim, assumir_cursando: bool) -> dict[str, float]:
    r = bol.resumo
    falta = {
        "condicionada": r.get("condicionada", {}).get("falta_cred", 0.0),
        "restrita": r.get("restrita_humanidades", {}).get("falta_cred", 0.0),
    }
    if assumir_cursando:
        for it in bol.itens:
            if it.situacao == "Cursando" and it.secao in falta:
                falta[it.secao] = max(0.0, falta[it.secao] - (it.creditos or 0.0))
    return falta


def montar_grade(cur: C.Curriculo, bol: B.Boletim, turmas: list[O.Turma], *,
                 max_creditos: float = 24, curso: str = "BCC1", n_solucoes: int = 1,
                 pesos: Pesos | None = None, assumir_cursando_aprovado: bool = True,
                 exigir_vaga: bool = True, tempo_max_s: float = 20.0
                 ) -> tuple[list[Selecao], Diagnostico]:
    pesos = pesos or Pesos()
    cand = candidatos(cur, bol, turmas, curso, assumir_cursando_aprovado, exigir_vaga)
    pend = {it.codigo for it in bol.pendentes()}
    deps = dependentes(cur, pend)
    falta = _faltas(bol, assumir_cursando_aprovado)

    premissas = []
    if assumir_cursando_aprovado:
        premissas.append("disciplinas 'Cursando' tratadas como aprovadas: "
                         + ", ".join(sorted(bol.cursando())))
    premissas.append(f"limite de {max_creditos:g} créditos; vagas do curso {curso} > 0")
    diag = Diagnostico(len(cand), falta, premissas)
    if not cand:
        return [], diag

    m = cp_model.CpModel()
    x = [m.NewBoolVar(f"x{k}") for k in range(len(cand))]

    # uma turma por disciplina
    por_cod: dict[str, list[int]] = {}
    for k, (it, _) in enumerate(cand):
        por_cod.setdefault(it.codigo, []).append(k)
    for ks in por_cod.values():
        m.AddAtMostOne(x[k] for k in ks)

    # choques de horário
    for a in range(len(cand)):
        for b in range(a + 1, len(cand)):
            if O.conflita(cand[a][1], cand[b][1]):
                m.AddBoolOr([x[a].Not(), x[b].Not()])

    # limite de créditos
    m.Add(sum(_c10(it.creditos) * x[k] for k, (it, _) in enumerate(cand))
          <= _c10(max_creditos))

    # optativas: só conta o que falta no bloco
    obj_terms = []
    for bloco in ("condicionada", "restrita"):
        ks = [k for k, (it, _) in enumerate(cand) if it.secao == bloco]
        if not ks:
            continue
        soma = sum(_c10(cand[k][0].creditos) * x[k] for k in ks)
        util = m.NewIntVar(0, _c10(falta[bloco]), f"util_{bloco}")
        m.AddMinEquality(util, [soma, _c10(falta[bloco])])
        excesso = m.NewIntVar(0, 1000, f"exc_{bloco}")
        m.Add(excesso == soma - util)
        obj_terms.append(pesos.optativa_por_credito * util - pesos.credito_excedente * excesso)

    # obrigatórias: créditos + bônus por destravar outras
    for k, (it, _) in enumerate(cand):
        if it.secao == "obrigatorias":
            obj_terms.append((pesos.obrigatoria_por_credito * _c10(it.creditos)
                              + pesos.dependente * 10 * len(deps.get(it.codigo, []))) * x[k])

    # buracos entre aulas (por dia)
    gaps = {}
    for d in ORDEM_DIAS:
        aulas_d = [(k, a) for k, (_, t) in enumerate(cand) for a in t.aulas if a.dia == d]
        if not aulas_d:
            continue
        fs = m.NewIntVar(0, 1440, f"fs_{d}")
        le = m.NewIntVar(0, 1440, f"le_{d}")
        gap = m.NewIntVar(0, 1440, f"gap_{d}")
        for k, a in aulas_d:
            m.Add(fs <= a.ini).OnlyEnforceIf(x[k])
            m.Add(le >= a.fim).OnlyEnforceIf(x[k])
        m.Add(gap >= le - fs - sum((a.fim - a.ini) * x[k] for k, a in aulas_d))
        gaps[d] = gap
        obj_terms.append(-10 * pesos.buraco_por_minuto * gap)

    m.Maximize(sum(obj_terms))

    solucoes: list[Selecao] = []
    for _ in range(n_solucoes):
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = tempo_max_s
        solver.parameters.num_workers = 8
        status = solver.Solve(m)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break
        sel = [k for k in range(len(cand)) if solver.Value(x[k])]
        ts = [cand[k][1] for k in sel]
        cods = [cand[k][0].codigo for k in sel]
        solucoes.append(Selecao(
            turmas=ts,
            secoes={cand[k][0].codigo: cand[k][0].secao for k in sel},
            creditos=sum(cand[k][0].creditos or 0 for k in sel),
            buracos_min=_buracos(ts),
            pontos=solver.ObjectiveValue() / 10,
            destrava={c: deps.get(c, []) for c in cods if deps.get(c)},
        ))
        # próxima solução: precisa ser diferente desta
        m.Add(sum(x[k] for k in sel) <= len(sel) - 1)
    return solucoes, diag


def _buracos(turmas: list[O.Turma]) -> dict[str, int]:
    """Minutos livres entre a primeira e a última aula de cada dia (calculado a posteriori)."""
    out = {}
    for d in ORDEM_DIAS:
        aulas = sorted((a.ini, a.fim) for t in turmas for a in t.aulas if a.dia == d)
        if aulas:
            out[d] = (aulas[-1][1] - aulas[0][0]) - sum(f - i for i, f in aulas)
    return out


def formatar(sel: Selecao, cur: C.Curriculo | None = None) -> str:
    linhas = []
    for t in sorted(sel.turmas, key=lambda t: t.codigo):
        nome = cur.disciplinas[t.codigo].nome if cur and t.codigo in cur.disciplinas else t.nome
        hor = ", ".join(f"{a.dia} {a.ini // 60:02d}:{a.ini % 60:02d}-{a.fim // 60:02d}:{a.fim % 60:02d}"
                        for a in t.aulas)
        extra = (f"  [destrava {', '.join(sel.destrava[t.codigo])}]" if t.codigo in sel.destrava else "")
        docente = f" — {', '.join(t.docentes)}" if t.docentes else ""
        linhas.append(f"  {t.codigo} {nome} ({sel.secoes[t.codigo][:4]}) {hor}{docente}{extra}")
    dias = {d: [] for d in ORDEM_DIAS}
    for t in sel.turmas:
        for a in t.aulas:
            dias[a.dia].append((a.ini, a.fim, t.codigo))
    semana = []
    for d, aulas in dias.items():
        if aulas:
            semana.append(f"  {d}: " + " | ".join(
                f"{i // 60:02d}-{f // 60:02d}h {c}" for i, f, c in sorted(aulas)))
    buracos = ", ".join(f"{d} {m} min" for d, m in sel.buracos_min.items() if m) or "nenhum"
    return ("\n".join(linhas) + "\n  semana:\n" + "\n".join(semana)
            + f"\n  créditos: {sel.creditos:g} | buracos: {buracos} | pontos: {sel.pontos:g}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Monta a grade do período a partir do boletim.")
    ap.add_argument("curriculo"); ap.add_argument("boletim"); ap.add_argument("oferta")
    ap.add_argument("--max-creditos", type=float, default=24)
    ap.add_argument("--curso", default="BCC1")
    ap.add_argument("--n", type=int, default=3, help="quantidade de alternativas")
    ap.add_argument("--peso-buraco", type=int, default=1, help="pontos perdidos por minuto de buraco")
    ap.add_argument("--peso-dependente", type=int, default=100,
                    help="pontos por disciplina pendente destravada por uma obrigatória")
    ap.add_argument("--nao-assumir-cursando", action="store_true")
    a = ap.parse_args()

    cur = C.carregar(a.curriculo)
    bol = B.carregar(a.boletim)
    turmas, _ = O.carregar(a.oferta)
    sols, diag = montar_grade(
        cur, bol, turmas, max_creditos=a.max_creditos, curso=a.curso, n_solucoes=a.n,
        pesos=Pesos(buraco_por_minuto=a.peso_buraco, dependente=a.peso_dependente),
        assumir_cursando_aprovado=not a.nao_assumir_cursando)
    print(f"candidatos (turmas): {diag.n_candidatos} | falta por bloco: {diag.falta}")
    for p in diag.premissas:
        print("premissa:", p)
    for i, s in enumerate(sols, 1):
        print(f"\nOpção {i}")
        print(formatar(s, cur))
    if not sols:
        print("nenhuma grade viável")


if __name__ == "__main__":
    main()
