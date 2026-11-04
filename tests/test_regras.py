"""Regras do pipeline em casos sintéticos: cada teste reproduz uma falha achada na auditoria (docs/AUDITORIA.md,
docs/MITIGACOES.md) e confere que a regra corrigida não a repete."""
import json

import pandas as pd
import pytest

import validar_avaliacao as va
from comum import dias_uteis, somar_du
from fichas_atividades import EXPEDIENTE, limpar_pessoais, repeticoes_por_caso
from fichas_trabalho import ancorar, legado
from trilhas import RE_PRORROGACAO, SEM_UNIDADE, data_da_peca, janelas_espera_externa, montar_posse

T = pd.Timestamp


# ------------------------------------------------------------------ dias úteis

def test_dias_uteis_pula_feriado_e_fim_de_semana():
    assert dias_uteis(T("2024-12-23"), T("2024-12-30")) == 4  # 25/12 e sábado/domingo fora
    assert somar_du(T("2024-12-23"), 4) == T("2024-12-30")


def test_data_da_peca_le_dia_primeiro():
    assert data_da_peca("05-03-2024") == T("2024-03-05")
    assert data_da_peca("2024-03-05") == T("2024-03-05")
    assert pd.isna(data_da_peca("20-08-20")) and pd.isna(data_da_peca("1899-01-01"))


# ------------------------------------------------------------------ posse (erro 2 da camada A)

def _est(u, a, b):
    return dict(unidade=u, entrada=T(a), saida_calc=T(b))


DOCS_VAZIO = pd.DataFrame(columns=["unidade", "categoria", "data_inclusao", "horas_base"])


def test_posse_e_de_quem_abriu_por_ultimo_entre_os_abertos():
    # gabinete abre em 01/03 e mantém aberto; CAPET abre em 04/03 e conclui em 15/03
    po = montar_posse([_est("AGENERSA/CONS-02", "2024-03-01", "2024-04-01"),
                       _est("AGENERSA/CAPET", "2024-03-04", "2024-03-15")], DOCS_VAZIO, T("2024-04-01"))
    assert [p["sigla"] for p in po] == ["CONS-02", "CAPET", "CONS-02"]


def test_posse_sem_ninguem_aberto_e_sem_unidade():
    po = montar_posse([_est("AGENERSA/CAPET", "2024-03-01", "2024-03-08"),
                       _est("AGENERSA/PROC", "2024-04-01", "2024-04-10")], DOCS_VAZIO, T("2024-04-10"))
    assert [p["unidade"] for p in po] == ["AGENERSA/CAPET", SEM_UNIDADE, "AGENERSA/PROC"]


def test_posse_particiona_o_tempo():
    po = montar_posse([_est("A/X", "2024-03-01", "2024-05-02"), _est("A/Y", "2024-03-20", "2024-04-10"),
                       _est("A/Z", "2024-06-03", "2024-06-20")], DOCS_VAZIO, T("2024-06-20"))
    for a, b in zip(po, po[1:]):
        assert a["fim"] == b["inicio"]
    assert sum(p["du"] for p in po) == dias_uteis(T("2024-03-01"), T("2024-06-20"))


# ------------------------------------------------------------------ terceiros (erro 3 da camada A)

def _docs(*linhas):
    cols = ["numero", "categoria", "unidade", "data_efetiva", "data_real_conhecida", "pede_prorrogacao"]
    d = pd.DataFrame(linhas, columns=cols)
    d["data_efetiva"] = pd.to_datetime(d["data_efetiva"])
    d["data_inclusao"] = d["data_efetiva"]
    return d


OF = ("1", "oficio", "AGENERSA/CASAN", "2024-03-01", True, False)


def test_resposta_dentro_do_prazo_e_terceiros():
    d = _docs(OF, ("2", "peca_externa", "AGENERSA/SCEXEC", "2024-03-08", True, False))
    terc, indet, _ = janelas_espera_externa(d, {"1": 10})
    assert (terc, indet) == (5, 0)


def test_resposta_sem_data_real_e_indeterminada():
    d = _docs(OF, ("2", "peca_externa", "AGENERSA/SCEXEC", "2024-03-08", False, False))
    assert janelas_espera_externa(d, {"1": 10})[:2] == (0, 5)


def test_oficio_sem_prazo_nao_abre_janela():
    d = _docs(OF, ("2", "peca_externa", "AGENERSA/SCEXEC", "2024-03-08", True, False))
    assert janelas_espera_externa(d, {"1": 0})[:2] == (0, 0)


def test_oficio_sem_ficha_e_indeterminado():
    d = _docs(OF, ("2", "peca_externa", "AGENERSA/SCEXEC", "2024-03-08", True, False))
    assert janelas_espera_externa(d, {})[:2] == (0, 5)


def test_excesso_alem_do_prazo_mais_5_e_indeterminado():
    d = _docs(OF, ("2", "peca_externa", "AGENERSA/SCEXEC", "2024-05-02", True, False))
    det = []
    terc, indet, _ = janelas_espera_externa(d, {"1": 10}, det)
    assert terc == 15 and terc + indet == dias_uteis(T("2024-03-01"), T("2024-05-02"))
    assert det[0]["situacao"].startswith("terceiros até prazo")


def test_peticionamento_em_processo_relacionado_responde():
    d = _docs(OF, ("SEI-1/2024", "processo_relacionado", "AGENERSA/SCEXEC", "2024-03-06", False, False))
    assert janelas_espera_externa(d, {"1": 10})[0] == 3


def test_anexo_da_propria_unidade_nao_e_resposta():
    d = _docs(OF, ("2", "anexo", "AGENERSA/CASAN", "2024-03-04", True, False),
              ("3", "peca_externa", "AGENERSA/SCEXEC", "2024-03-08", True, False))
    assert janelas_espera_externa(d, {"1": 10})[0] == 5


def test_oficio_de_outro_orgao_nao_abre_janela():
    d = _docs(("1", "oficio", "PREFEITURA/GAB", "2024-03-01", True, False),
              ("2", "peca_externa", "AGENERSA/SCEXEC", "2024-03-08", True, False))
    assert janelas_espera_externa(d, {"1": 10})[:2] == (0, 0)


def test_pedido_de_prorrogacao_nao_fecha_a_janela():
    d = _docs(OF, ("2", "peca_externa", "AGENERSA/SCEXEC", "2024-03-05", True, True),
              ("3", "peca_externa", "AGENERSA/SCEXEC", "2024-03-12", True, False))
    assert janelas_espera_externa(d, {"1": 10})[0] == 7


def test_regex_de_prorrogacao():
    assert RE_PRORROGACAO.search("requer dilação do prazo por 30 dias")
    assert RE_PRORROGACAO.search("solicita prorrogação")
    assert not RE_PRORROGACAO.search("apresenta as informações solicitadas")


# ------------------------------------------------------------------ fichas (camada B)

TEXTO = "A CAPET calculou a TIR desequilibrada de 8,2% com base no fluxo de caixa livre do Anexo III."


def test_ancoragem_aceita_trecho_literal_e_recusa_inventado():
    f = ancorar({"insumos": [{"descricao": "x", "evidencia": "calculou a TIR desequilibrada de 8,2%"},
                             {"descricao": "y", "evidencia": "planilha de Monte Carlo com 10 mil cenários"},
                             {"descricao": "z", "evidencia": "TIR"},
                             {"descricao": "w", "evidencia": "A CAPET calculou ... fluxo de caixa livre"}]}, TEXTO)
    assert [x["ancorado"] for x in f["insumos"]] == [True, False, False, True]


def test_legado_so_leva_item_ancorado_e_ignora_prazo_de_prorrogacao():
    f = ancorar({"trabalho_proprio": {"ferramentas": [{"nome": "planilha", "evidencia": "fluxo de caixa livre do Anexo III"},
                                                      {"nome": "Power BI", "evidencia": "painel em Power BI"}]},
                 "prazos": [{"dias": 30, "natureza": "prorrogacao", "beneficiario": "concessionaria",
                             "evidencia": "fluxo de caixa livre"},
                            {"dias": 10, "natureza": "diligencia", "beneficiario": "concessionaria",
                             "evidencia": "calculou a TIR"}]}, TEXTO)
    f = legado(f)
    assert f["ferramentas"] == ["planilha"] and f["prazo_concedido_dias"] == 10
    assert any(x.get("nome") == "Power BI" for x in f["nao_ancorados"])


def test_expediente_nao_vira_ferramenta():
    assert EXPEDIENTE.search("Encaminho os autos à SCEXEC para conhecimento")
    assert not EXPEDIENTE.search("simulação do fluxo de caixa descontado em planilha")


def test_limpeza_de_dados_pessoais():
    t = limpar_pessoais({"a": ["a reclamante Maria da Silva Souza mora na Rua das Flores, nº 120, apto 3",
                               "CPF 123.456.789-00, e-mail fulano@gmail.com, tel. (21) 99876-5432"]})
    s = json.dumps(t, ensure_ascii=False)
    for proibido in ("Maria", "Flores", "123.456", "fulano@", "99876"):
        assert proibido not in s


def test_repeticao_de_peca_da_mesma_categoria():
    base = " ".join(f"palavra{i}" for i in range(300))
    texto = {"a": base, "b": base + " novo trecho final", "c": base, "d": " ".join(f"outra{i}" for i in range(300))}
    texto.update({f"ruido{i}": " ".join(f"r{i}x{j}" for j in range(60)) for i in range(40)})
    esf = pd.DataFrame({"categoria": ["parecer", "parecer", "oficio", "parecer"],
                        "tipo": ["Parecer 1", "Parecer 2", "Ofício", "Parecer 3"],
                        "data_inclusao": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-01-15", "2024-03-01"])},
                       index=["a", "b", "c", "d"])
    out = repeticoes_por_caso({"caso": ["a", "b", "c", "d"]}, texto, esf)
    assert set(out) == {"b"}  # c é de outra categoria; d é texto novo


# ------------------------------------------------------------------ validador das avaliações (camada F)

@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(va, "DIR", tmp_path)
    monkeypatch.setattr(va, "datas_conhecidas", lambda cod: {"2024-03-04"})
    fatos = {"fatos": [{"id": "tipico.lead", "caso": "X", "valor": 120.0, "unidade": "du"},
                       {"id": "tipico.terceiros", "caso": "X", "valor": 23.0, "unidade": "du"}]}
    (tmp_path / "fatos_PX.json").write_text(json.dumps(fatos), encoding="utf-8")
    (tmp_path / "fichas_PX.json").write_text(json.dumps({"atividades": {"t1": {"laudas": 57}}}), encoding="utf-8")
    (tmp_path / "vinculos_PX.json").write_text(json.dumps({"atividades": {}}), encoding="utf-8")
    (tmp_path / "modelo_PX.json").write_text(json.dumps({"elementos": []}), encoding="utf-8")

    def escrever(av, vin=None):
        (tmp_path / "avaliacao_PX.json").write_text(json.dumps(av, ensure_ascii=False), encoding="utf-8")
        if vin:
            (tmp_path / "vinculos_PX.json").write_text(json.dumps(vin, ensure_ascii=False), encoding="utf-8")
        return va.validar("PX")
    return escrever


def test_validador_aceita_texto_ancorado(base):
    av = {"sintese": "Lead de 120 du, voto de 57 laudas; terceiros 23 du em 04/03/2024.",
          "fatos_sintese": ["tipico.lead", "tipico.terceiros"]}
    assert base(av) == []


@pytest.mark.parametrize("texto,fatos,trecho", [
    ("Terceiros somam 96 du.", ["tipico.terceiros"], "96 du"),           # número desatualizado
    ("Lead de 120 du.", [], "sem fatos_usados"),                           # sem fato citado
    ("Lead de 120 du.", ["tipico.inexistente"], "inexistentes"),           # fato que não existe
    ("Resposta em 12/08/2024; lead 120 du.", ["tipico.lead"], "data"),     # data sem lastro
    ("A mediana é de 120 du.", ["tipico.lead"], "mediana"),                # mediana sem dizer de quem
    ("Trabalho de 75 h.", ["tipico.lead"], "75"),                          # número fora de fatos e ficha
])
def test_validador_barra(base, texto, fatos, trecho):
    erros = base({"sintese": texto, "fatos_sintese": fatos})
    assert erros and any(trecho in e for e in erros), erros


def test_validador_barra_tempo_medido_no_descritivo(base):
    vin = {"atividades": {"t1": {"descritivo": "A CAPET levou 153 dias úteis para responder."}}}
    assert any("t1.descritivo" in e for e in base({"sintese": ""}, vin))
    vin = {"atividades": {"t1": {"descritivo": "Concede 57 dias úteis à concessionária."}}}  # prazo da peça
    assert base({"sintese": ""}, vin) == []


def test_validador_exige_entrada_para_cada_tarefa_do_modelo(base, tmp_path):
    mod = {"elementos": [{"id": "t1", "tipo": "tarefa"}, {"id": "t2", "tipo": "tarefa"}, {"id": "g1", "tipo": "xor"}]}
    (tmp_path / "modelo_PX.json").write_text(json.dumps(mod), encoding="utf-8")
    erros = base({"sintese": "", "atividades": {"t1": {}, "t9": {}}})
    assert any("sem entrada" in e and "t2" in e for e in erros) and any("não existem" in e and "t9" in e for e in erros)


def test_validador_sem_caso_piloto_usa_numeros_da_coorte(base, tmp_path, monkeypatch):
    """Tipo sem fichas nem vínculos do piloto: contagens vêm do procedimento da coorte."""
    (tmp_path / "fichas_PX.json").unlink()
    (tmp_path / "vinculos_PX.json").unlink()
    monkeypatch.setattr(va, "SAIDA", tmp_path)
    (tmp_path / "fase2").mkdir()
    (tmp_path / "fase2" / "procedimento_PX.json").write_text(json.dumps({"casos": 19}), encoding="utf-8")
    assert base({"sintese": "Lead de 120 du em 19 processos.", "fatos_sintese": ["tipico.lead"]}) == []
    assert base({"sintese": "Lead de 120 du em 23 processos.", "fatos_sintese": ["tipico.lead"]})


def test_carimbo_invalida_quando_fato_muda(base, tmp_path):
    base({"sintese": "Lead de 120 du.", "fatos_sintese": ["tipico.lead"]})
    va.carimbar("PX")
    assert va.validar("PX", exigir_carimbo=True) == []
    f = json.loads((tmp_path / "fatos_PX.json").read_text(encoding="utf-8"))
    f["fatos"][1]["valor"] = 19.0
    (tmp_path / "fatos_PX.json").write_text(json.dumps(f), encoding="utf-8")
    assert any("carimbada" in e for e in va.validar("PX", exigir_carimbo=True))


# ------------------------------------------------------------------ fase 2

def test_data_do_relator_brasileira_ou_iso():
    from pecas_relator import _data
    s = _data(pd.Series(["05/03/2024", "2024-03-05T00:00:00.000Z", None]))
    assert s.iloc[0] == T("2024-03-05") and s.iloc[1] == T("2024-03-05") and pd.isna(s.iloc[2])


def test_distribuicao_ignora_ausentes():
    from procedimento import dist
    d = dist([1, 2, 3, 4, None, float("nan")])
    assert d["n"] == 4 and d["mediana"] == 2.5 and d["max"] == 4
    assert dist([]) is None


def test_coorte_tira_copia_de_processo_migrado():
    from coorte_fase2 import duplicatas
    t = {"MIG": {"a", "b", "c", "d"}, "COPIA": {"a", "b", "c"}, "REL": {"a", "x", "y", "z"},
         "S1": {"p", "q", "r", "s"}, "S2": {"p", "q", "r", "s"}}
    tr = {"MIG": "migrada", "COPIA": "sem", "REL": "sem", "S1": "sem", "S2": "sem"}
    d = duplicatas(t, tr)
    assert d["COPIA"] == "MIG"          # cópia integral do migrado sai
    assert "REL" not in d               # peça compartilhada entre processos relacionados não é duplicata
    assert "MIG" not in d               # processo com trilha nunca sai
    assert len({"S1", "S2"} & set(d)) == 1  # entre dois sem trilha idênticos, sai só um


def test_situacao_do_codigo_pela_auditoria():
    from procedimento import situacao
    assert situacao(12, {"concordancia_substantivas": 0.93}) == "procedimento"
    assert situacao(12, {"concordancia_substantivas": 0.64}) == "indicativo"
    assert situacao(12, None) == "indicativo"          # sem auditoria não vira procedimento
    assert situacao(3, {"concordancia_substantivas": 1.0}) == "estudo_de_caso"


def test_probabilidade_dos_ramos_pela_transicao_observada():
    from gerar_bpmn import probabilidades_ramos
    m = {"elementos": [{"id": "s", "tipo": "inicio"}, {"id": "t1", "tipo": "tarefa"}, {"id": "j", "tipo": "xor_juncao"},
                       {"id": "g", "tipo": "xor"}, {"id": "e", "tipo": "evento_mensagem"}, {"id": "t2", "tipo": "tarefa"},
                       {"id": "t3", "tipo": "tarefa"}, {"id": "f", "tipo": "fim"}],
         "fluxos": [{"de": "s", "para": "t1"}, {"de": "t1", "para": "j"}, {"de": "j", "para": "g"},
                    {"de": "g", "para": "e"}, {"de": "e", "para": "t2"},       # ramo 3: passa por evento até t2
                    {"de": "g", "para": "t3"}, {"de": "t2", "para": "j"}, {"de": "t3", "para": "f"}]}
    tr = {"t1": [{"para": "t2", "n": 3}, {"para": "t3", "n": 1}], "t2": [{"para": "t2", "n": 5}, {"para": "t3", "n": 1}]}
    p = probabilidades_ramos(m, tr)
    # antes da decisão: t1 e t2 (laço pela junção); ramo F3 → t2, ramo F5 → t3
    assert p[3] == (8, 80) and p[5] == (2, 20)
    # ramos que chegam à mesma atividade não recebem %
    m2 = {**m, "fluxos": m["fluxos"] + [{"de": "g", "para": "t2"}]}
    assert probabilidades_ramos(m2, tr) == {}


# ------------------------------------------------------------------ conformidade legal (fase 3)

def _ev(*itens):
    return [dict(atividade=a, data=T(d), prazo=p) for a, d, p in itens]


def test_conformidade_precede_exige_ordem_e_nao_aplica_sem_o_ato():
    from conformidade import avaliar
    t = {"tipo": "precede", "a": "t7", "b": "t8"}
    assert avaliar(t, _ev(("t7", "2024-01-02", None), ("t8", "2024-02-01", None)))[0] == "conforme"
    assert avaliar(t, _ev(("t8", "2024-01-02", None), ("t7", "2024-02-01", None)))[0] == "nao_conforme"
    assert avaliar(t, _ev(("t7", "2024-01-02", None)))[0] == "nao_aplicavel"


def test_conformidade_prazo_min_usa_a_ultima_notificacao_antes_do_ato():
    from conformidade import avaliar
    t = {"tipo": "prazo_min", "de": "t7", "ate": "t8", "min": 10, "unidade": "du"}
    ev = _ev(("t7", "2024-01-02", None), ("t7", "2024-03-01", None), ("t8", "2024-03-05", None))
    res, det = avaliar(t, ev)  # a 2ª notificação reabre o prazo: só 2 du até a sessão
    assert res == "nao_conforme" and det.startswith("2 du")


def test_conformidade_prazo_concedido_sem_leitura_e_sem_evidencia_nao_violacao():
    from conformidade import avaliar
    t = {"tipo": "prazo_concedido_min", "atividade": "t3", "min": 15}
    assert avaliar(t, _ev(("t3", "2024-01-02", None)))[0] == "sem_evidencia"
    assert avaliar(t, _ev(("t3", "2024-01-02", 10), ("t3", "2024-02-02", 20)))[0] == "nao_conforme"
    assert avaliar(t, _ev(("t3", "2024-01-02", 15)))[0] == "conforme"


def test_conformidade_duracao_max_em_anos_conta_do_primeiro_evento():
    from conformidade import avaliar
    t = {"tipo": "duracao_max", "ate": "t8", "max": 5, "unidade": "anos"}
    assert avaliar(t, _ev(("t1", "2019-01-02", None), ("t8", "2025-01-02", None)))[0] == "nao_conforme"
    assert avaliar(t, _ev(("t1", "2021-01-02", None), ("t8", "2025-01-02", None)))[0] == "conforme"


# ------------------------------------------------------------------ simulação do TO-BE (fase 3)

def _caso():
    oc = [dict(atividade="t1", espera_antes_du=2.0, execucao_du=1.0, espera_antes_por_unidade={}, horas_piso=1.0, horas_teto=2.0),
          dict(atividade="t4", espera_antes_du=30.0, execucao_du=0.0, espera_antes_por_unidade={"SEM UNIDADE": 20.0, "PROC": 10.0},
               horas_piso=4.0, horas_teto=6.0),
          dict(atividade="t4", espera_antes_du=10.0, execucao_du=0.0, espera_antes_por_unidade={}, horas_piso=2.0, horas_teto=3.0)]
    return dict(cauda_du=5.0, ocorrencias=oc)


def test_tobe_fase_zero_reproduz_o_lead_da_linha_do_tempo():
    from simular_tobe import simular
    (m,) = simular([_caso()], [], 0, "esperado")
    assert m["lead"] == 48.0 and m["horas_piso"] == 7.0


def test_tobe_teto_sem_unidade_corta_so_o_tempo_sem_dono():
    from simular_tobe import simular
    mel = [dict(id="M1", fase=1, efeito=dict(tipo="teto_espera", atividades=["t4"], parte="sem_unidade",
                                              cenarios=dict(conservador=10, esperado=5, otimista=0)))]
    (m,) = simular([_caso()], mel, 1, "esperado")
    assert m["lead"] == 48.0 - 15.0  # 20 du sem unidade viram 5; os 10 du na PROC ficam


def test_tobe_laco_so_reduz_ocorrencia_repetida_e_fases_sao_cumulativas():
    from simular_tobe import simular
    mel = [dict(id="M1", fase=1, efeito=dict(tipo="elimina_laco_pct", atividades=["t4"], cenarios=dict(conservador=0, esperado=50, otimista=100))),
           dict(id="M2", fase=2, efeito=dict(tipo="reduz_horas_pct", atividades=["t1"], cenarios=dict(conservador=0, esperado=50, otimista=100)))]
    (f1,) = simular([_caso()], mel, 1, "esperado")
    (f2,) = simular([_caso()], mel, 2, "esperado")
    assert f1["lead"] == 43.0 and f1["horas_piso"] == 6.0
    assert f2["horas_piso"] == 5.5


def test_tobe_teto_e_reducao_nao_cortam_resposta_de_terceiro():
    from simular_tobe import simular
    c = _caso()
    c["ocorrencias"][1]["espera_antes_terceiros_du"] = 12.0  # dos 30 du antes de t4, 12 são prazo de resposta da concessionária
    teto = [dict(id="M1", fase=1, efeito=dict(tipo="teto_espera", atividades=["t4"], parte="toda",
                                               cenarios=dict(conservador=10, esperado=5, otimista=0)))]
    (m,) = simular([c], teto, 1, "esperado")
    assert m["lead"] == 48.0 - (30.0 - 17.0) - (10.0 - 5.0)  # 12 de terceiro + 5 de teto; a 2ª ocorrência vai a 5
    red = [dict(id="M1", fase=1, efeito=dict(tipo="reduz_espera_pct", atividades=["t4"],
                                              cenarios=dict(conservador=0, esperado=50, otimista=100)))]
    (m,) = simular([c], red, 1, "otimista")
    assert m["lead"] == 48.0 - 18.0 - 10.0
    su = [dict(id="M1", fase=1, efeito=dict(tipo="teto_espera", atividades=["t4"], parte="sem_unidade",
                                             cenarios=dict(conservador=10, esperado=5, otimista=0)))]
    c["ocorrencias"][1]["espera_antes_terceiros_du"] = 25.0  # o tempo sem unidade coincide com a resposta de terceiro
    (m,) = simular([c], su, 1, "otimista")
    assert m["lead"] == 48.0 - 5.0


def test_tobe_cauda_so_reduz_em_caso_encerrado():
    from simular_tobe import simular
    mel = [dict(id="M1", fase=1, efeito=dict(tipo="reduz_cauda_pct", cenarios=dict(conservador=0, esperado=50, otimista=100)))]
    aberto, fechado = _caso(), {**_caso(), "encerrado": True}
    (a,) = simular([aberto], mel, 1, "otimista")
    (f,) = simular([fechado], mel, 1, "otimista")
    assert a["lead"] == 48.0 and f["lead"] == 43.0


def test_conformidade_prazo_max_nao_conta_origem_posterior_ao_ato_e_aceita_ultima_rodada():
    from conformidade import avaliar
    t = {"tipo": "prazo_max", "de": "t7", "ate": "t8", "max": 40, "unidade": "dc"}
    # razões finais só depois da deliberação (rodada dos embargos): intervalo negativo não é conformidade
    assert avaliar(t, _ev(("t8", "2024-01-10", None), ("t7", "2024-03-01", None)))[0] == "nao_aplicavel"
    ev = _ev(("t7", "2024-01-02", None), ("t7", "2024-05-02", None), ("t8", "2024-05-20", None))
    assert avaliar(t, ev)[0] == "nao_conforme"  # da 1ª rodada: 139 dias
    assert avaliar({**t, "de_ocorrencia": "ultima"}, ev)[0] == "conforme"  # da última rodada: 18 dias


def test_tobe_conformidade_simulada_reproduz_a_medida_na_fase_zero():
    from simular_tobe import eventos
    from conformidade import avaliar
    c = dict(cauda_du=0.0, ocorrencias=[
        dict(atividade="t7", inicio="2024-01-02", espera_antes_du=0.0, execucao_du=0.0),
        dict(atividade="t8", inicio="2024-03-01", espera_antes_du=43.0, execucao_du=0.0)])
    t = {"tipo": "prazo_max", "de": "t7", "ate": "t8", "max": 40, "unidade": "dc"}
    assert avaliar(t, eventos(c))[0] == "nao_conforme"
    c["ocorrencias"][1]["espera_antes_du"] = 20.0  # teto de 20 du: cabe nos 40 dias corridos
    assert avaliar(t, eventos(c))[0] == "conforme"


# ------------------------------------------------------------------ fase 4: priorização da automação

def test_priorizacao_regua_e_nota_composta():
    from priorizacao_automacao import nota, nota_composta
    from comum import PRIORIZACAO_CRITERIOS
    assert nota(4.9, (5, 10, 25, 50)) == 1 and nota(5, (5, 10, 25, 50)) == 2 and nota(50, (5, 10, 25, 50)) == 5
    assert nota(None, (5, 10, 25, 50)) is None
    assert nota_composta({c: 5 for c in PRIORIZACAO_CRITERIOS}) == 100
    assert nota_composta({c: 1 for c in PRIORIZACAO_CRITERIOS}) == 20
    # critério sem medida não vira nota baixa presumida: a nota composta fica vazia
    assert nota_composta({**{c: 5 for c in PRIORIZACAO_CRITERIOS}, "volume": None}) is None


def test_priorizacao_volume_estimado_corrige_piso_pela_fracao_com_deliberacao():
    from priorizacao_automacao import volume_estimado
    assert volume_estimado(10, 50, 1.0) == 20.0  # metade dos processos chega à deliberação
    assert volume_estimado(9, 50, 0.9) == 20.0   # a regra pega 90% dos que chegam
    assert volume_estimado(10, None, 1.0) is None and volume_estimado(0, 50, 1.0) is None


def test_priorizacao_fracao_automatizavel_pondera_pelas_horas():
    from priorizacao_automacao import fracao_automatizavel
    from comum import FRACAO_AUTOMATIZAVEL
    h = {"t1": 30.0, "t2": 10.0}
    esp = fracao_automatizavel(h, {"t1": "alto", "t2": "baixo"}, 1)
    assert esp == pytest.approx((30 * FRACAO_AUTOMATIZAVEL["alto"][1] + 10 * FRACAO_AUTOMATIZAVEL["baixo"][1]) / 40)
    assert fracao_automatizavel(h, {}, 1) == pytest.approx(FRACAO_AUTOMATIZAVEL["baixo"][1])  # sem avaliação = baixo
    assert fracao_automatizavel({}, {}, 1) == 0.0


def test_priorizacao_custo_incremental_e_payback():
    from priorizacao_automacao import custo_construcao_h, payback_anos
    from comum import HORAS_CAPACIDADE, HORAS_CONFIG_ATIVIDADE, HORAS_PLATAFORMA, VARIABILIDADE_FATOR
    cap = {"classificação e triagem"}
    iso = custo_construcao_h(cap, 2, 1.0)
    inc = custo_construcao_h(cap, 2, 1.0, incremental=True)
    assert inc == pytest.approx(2 * HORAS_CONFIG_ATIVIDADE * (1 + VARIABILIDADE_FATOR))
    assert iso == pytest.approx(HORAS_PLATAFORMA + HORAS_CAPACIDADE["classificação e triagem"] + inc)
    assert payback_anos(100, 60, 10) == 2.0
    assert payback_anos(100, 10, 10) is None  # retorno não cobre o custo anual: nunca se paga


def test_fichas_trabalho_tem_limpeza_de_dados_pessoais_importada():
    """A gravação de saida/fichas_trabalho.jsonl chama limpar_pessoais; sem o import, a etapa caía no fim da rodada."""
    import fichas_trabalho
    assert fichas_trabalho.limpar_pessoais is limpar_pessoais


def test_fichas_importadas_de_agente_passam_pela_mesma_ancoragem():
    """Resposta gravada por agente (--importar) recebe a mesma âncora literal que a resposta da API."""
    texto = "O relatório fixa o prazo de 30 (trinta) dias para sanar as não conformidades."
    f = legado(ancorar({"prazos": [{"dias": 30, "beneficiario": "concessionaria", "natureza": "cumprimento",
                                    "evidencia": "prazo de 30 (trinta) dias para sanar"},
                                   {"dias": 10, "beneficiario": "concessionaria", "natureza": "cumprimento",
                                    "evidencia": "prazo de 10 dias para defesa"}]}, texto))
    assert f["prazo_concedido_dias"] == 30
    assert len(f["nao_ancorados"]) == 1
