"""Cruza currículo + boletim + oferta e lista o que o aluno pode cursar no período.

Uso:
    python demo.py CURRICULO.html BOLETIM.pdf OFERTA.xlsx

Também valida a lógica de pré-requisitos: o boletim já informa, por disciplina,
"Inscrição Facultada" / "Inscrição Vedada"; a elegibilidade calculada aqui deve bater
com esse rótulo (Vedada ≈ pré-requisito não cumprido).
"""
from __future__ import annotations

import sys
from collections import Counter

import boletim as B
import curriculo as C
import oferta as O


def main(f_cur: str, f_bol: str, f_ofe: str) -> None:
    cur = C.carregar(f_cur)
    bol = B.carregar(f_bol)
    turmas, avisos = O.carregar(f_ofe)

    # 1) o boletim e o currículo descrevem as mesmas disciplinas?
    cod_cur, cod_bol = set(cur.disciplinas), {i.codigo for i in bol.itens}
    print(f"currículo: {len(cod_cur)} disciplinas | boletim: {len(cod_bol)} | "
          f"só no currículo: {sorted(cod_cur - cod_bol)} | só no boletim: {sorted(cod_bol - cod_cur)}")
    print("avisos do currículo:", cur.validar() or "nenhum")

    # 2) elegibilidade por pré-requisito
    concl, cursando = bol.concluidas(), bol.cursando()
    pend = [i for i in bol.pendentes() if i.codigo not in cursando]
    elegiveis, bloqueadas = [], {}
    for it in pend:
        faltam = cur.pendencias(it.codigo, concl)
        (bloqueadas.__setitem__(it.codigo, faltam) if faltam else elegiveis.append(it))

    # 3) validação cruzada com o rótulo do próprio boletim
    tab = Counter()
    divergentes = []
    for it in pend:
        calc = "elegivel" if it.codigo not in bloqueadas else "bloqueada"
        tab[(it.situacao, calc)] += 1
        if (it.situacao == "Inscrição Facultada") != (calc == "elegivel"):
            divergentes.append((it.codigo, it.situacao, calc, bloqueadas.get(it.codigo)))
    print("\nrótulo do boletim × cálculo próprio:")
    for k, v in sorted(tab.items(), key=str):
        print("  ", k, v)
    print("divergências:", divergentes or "nenhuma")

    # 4) o que está ofertado neste período
    por_cod: dict[str, list[O.Turma]] = {}
    for t in turmas:
        por_cod.setdefault(t.codigo, []).append(t)
    print(f"\nelegíveis: {len(elegiveis)} | com turma ofertada: "
          f"{sum(1 for i in elegiveis if i.codigo in por_cod)}")
    for it in elegiveis:
        for t in por_cod.get(it.codigo, []):
            hor = ", ".join(f"{a.dia} {a.ini // 60:02d}-{a.fim // 60:02d}h" for a in t.aulas)
            print(f"  {it.secao[:4]} {it.codigo} {it.nome[:30]:30} {t.periodo_tipo:7} "
                  f"vagas BCC1={t.vagas_para('BCC1')} | {hor}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
