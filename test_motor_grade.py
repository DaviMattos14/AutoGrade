import json
import unittest
from pathlib import Path

from motor_grade import ErroDoMotor, gerar_grade, gerar_versoes_da_grade


class AreaDeInteresseTests(unittest.TestCase):
    def setUp(self):
        self.curriculo = json.loads((Path(__file__).parent / "grades_curricular" /
                                    "curriculo_85783_2022-2.json").read_text(encoding="utf-8"))
        self.area = "Engenharia de Software"
        self.boa = {"curso": {"codigo": "85783"}, "versao_curricular": "2022/2",
                    "cumpridas": [], "pendentes": [
                        {"codigo": c, "secao": "optativa_condicionada", "status": "Facultada"}
                        for c in ("ICP508", "ICP020")],
                    "resumo": {"escolha_condicionada": {"falta_creditos": 4}}}
        self.ofertas = {"_meta": {"periodo": "2026-2"}, "turmas": [
            {"id": c, "codigo_no_curriculo": c, "situacao": "confirmada", "horario_completo": True,
             "docentes": [], "aulas": [{"dia": "SEG", "dia_numero": 0, "inicio": "08:00",
                 "fim": "10:00", "inicio_min": 480, "fim_min": 600, "sala": ""}]}
            for c in ("ICP508", "ICP020")]}

    def gerar(self, **parametros):
        return gerar_grade(self.boa, self.curriculo, self.ofertas, limite_de_creditos=4, **parametros)

    def test_area_altera_escolha_entre_optativas_em_choque(self):
        dados = self.gerar(area_de_interesse="Ciência de Dados e Engenharia de Dados")
        software = self.gerar(area_de_interesse=self.area)
        self.assertEqual([g["codigo"] for g in dados["grade"]], ["ICP508"])
        self.assertEqual([g["codigo"] for g in software["grade"]], ["ICP020"])
        self.assertIn(self.area, software["grade"][0]["motivo"])
        self.assertEqual(software["_meta"]["parametros"]["area_de_interesse"], self.area)

    def test_sem_preferencia_preserva_comportamento(self):
        self.assertEqual(self.gerar()["grade"], self.gerar(area_de_interesse=None)["grade"])

    def test_area_sem_ofertas_permite_outras_optativas(self):
        self.assertTrue(self.gerar(area_de_interesse="Computação Científica")["grade"])

    def test_preferencia_nao_libera_materia_vedada(self):
        self.boa["pendentes"][1]["status"] = "Vedada"
        self.assertEqual(self.gerar(area_de_interesse=self.area)["grade"][0]["codigo"], "ICP508")

    def test_desativar_optativas_e_limite_de_creditos(self):
        self.assertEqual(self.gerar(area_de_interesse=self.area, incluir_optativas=False)["grade"], [])
        self.curriculo["disciplinas"]["ICP020"]["creditos"] = 6
        self.assertEqual(self.gerar(area_de_interesse=self.area)["grade"][0]["codigo"], "ICP508")

    def test_obrigatoria_mantem_prioridade(self):
        self.boa["pendentes"][0]["secao"] = "obrigatoria"
        self.assertEqual(self.gerar(area_de_interesse=self.area)["grade"][0]["codigo"], "ICP508")

    def test_area_invalida(self):
        with self.assertRaises(ErroDoMotor):
            self.gerar(area_de_interesse="Área inexistente")

    def test_versoes_recebem_preferencia(self):
        versoes = gerar_versoes_da_grade(self.boa, self.curriculo, self.ofertas,
                                        limite_de_creditos=4, area_de_interesse=self.area)
        self.assertEqual(versoes[0]["grade"][0]["codigo"], "ICP020")
        self.assertTrue(all(v["_meta"]["parametros"]["area_de_interesse"] == self.area for v in versoes))

    def test_mapeamento_do_manual_contem_apenas_optativas_do_curriculo(self):
        areas = self.curriculo["areas_de_interesse"]
        self.assertEqual(len(areas), 5)
        self.assertEqual(sum(map(len, areas.values())), 57)
        for codigos in areas.values():
            for codigo in codigos:
                self.assertEqual(self.curriculo["disciplinas"][codigo]["tipo"], "optativa_condicionada")


if __name__ == "__main__":
    unittest.main()
