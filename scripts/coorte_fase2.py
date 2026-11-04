"""Fase 2 — coorte por processo organizacional: do caso ao procedimento.

Entra todo processo do código com trilha nativa do SEI, classificação de confiança média ou alta e texto
suficiente (peças substantivas com texto ≥ 60%). O código entra se tiver pelo menos 5 casos.
  lote 1 = códigos que já têm modelo canônico (saida/bpmn/modelo_<Pxx>.json): trilha nativa, ≥ 5 casos
  lote 2 = tipos novos (NOVOS, do perfil): inventário sem modelo e N01 (acompanhamento ambiental e de mananciais, a demanda
           recorrente fora do inventário); entram processos migrados (trilha parcial) e os que só existem no banco
           do relator (trilha "sem": conteúdo e execução das peças, sem posse nem espera entre unidades)
Demais LACUNA ficam fora: tipos com menos de 5 casos (bens reversíveis, aquisição de gás, gestão documental).
Processo em andamento entra (dá ocorrências de atividade), mas lead time só se mede nos encerrados.
Processo só do relator que é cópia de outro da coorte (processo físico migrado que reaparece com número novo: ≥ 90%
dos textos iguais, mínimo 3) sai, para não contar o mesmo caso duas vezes (saida/fase2/duplicados.csv).

Depois de exportar o texto (exportar_relator.py --processos saida/coorte_fase2.csv), rodar de novo: a cobertura
passa a ser a do texto não vazio (dados/relator/cobertura_texto.csv), mais estrita que o status de download.

Saída: saida/coorte_fase2.csv"""
from __future__ import annotations

import hashlib
import json

import pandas as pd

from comum import CODIGOS_NOVOS_FASE2, DADOS, SAIDA, TIPOS_FORA_CATALOGO
from selecionar_piloto import COBERTURA_MIN

MIN_CASOS = 5
# tipos que entram além dos com modelo (perfil): inventário sem modelo e demanda fora do inventário
# (TIPOS_FORA_CATALOGO; na AGENERSA, N01 = acompanhamento ambiental e de mananciais, LACUNA recorrente)
NOVOS = CODIGOS_NOVOS_FASE2
NOME_FORA = {c: nome for c, (_, nome) in TIPOS_FORA_CATALOGO.items()}


DUP_FRAC, DUP_MIN = 0.9, 3


def duplicatas(textos: dict[str, set], trilha: dict[str, str]) -> dict[str, str]:
    """Processo sem trilha cujos textos estão (≥ DUP_FRAC) em outro processo → número do original.
    O original é o de trilha (nativa/migrada) se houver; entre dois sem trilha, o de mais textos."""
    out = {}
    for a, ha in textos.items():
        if trilha.get(a) != "sem" or len(ha) < DUP_MIN:
            continue
        for b, hb in textos.items():
            if b == a or b in out:
                continue
            maior = trilha.get(b) != "sem" or (len(hb), b) > (len(ha), a)
            if maior and len(ha & hb) / len(ha) >= DUP_FRAC:
                out[a] = b
                break
    return out


def _hashes(numeros) -> dict[str, set]:
    t = pd.read_parquet(DADOS / "relator" / "doc_text_piloto.parquet", columns=["processo", "texto"])
    t = t[t.processo.isin(set(numeros)) & (t.texto.str.strip().str.len() > 300)]
    return {p: {hashlib.md5(" ".join(x.split()).encode()).hexdigest() for x in g.texto} for p, g in t.groupby("processo")}


def _fora(cod, lacuna):
    """LACUNA cuja sugestão começa pelo texto de um tipo fora do catálogo → código desse tipo."""
    if cod == "LACUNA":
        for c, (prefixo, _) in TIPOS_FORA_CATALOGO.items():
            if str(lacuna).startswith(prefixo):
                return c
    return cod


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-casos", type=int, default=MIN_CASOS,
                    help="mínimo de casos por código (1 = estudo de caso de um processo só)")
    min_casos = ap.parse_args().min_casos
    d = pd.read_csv(SAIDA / "processos_classificados.csv")
    cob = DADOS / "relator" / "cobertura_texto.csv"
    if cob.exists():  # cobertura medida no texto exportado substitui a do status de download
        c = pd.read_csv(cob).rename(columns={"processo": "numero", "cobertura_substantivas": "cob_texto"})
        d = d.merge(c[["numero", "cob_texto"]], on="numero", how="left")
        d["cobertura_substantivas"] = d["cob_texto"].fillna(d["cobertura_substantivas"])
    d["processo_principal"] = [_fora(c_, l_) for c_, l_ in zip(d.processo_principal, d.lacuna_sugerida)]
    for c_, nome in NOME_FORA.items():
        d.loc[d.processo_principal == c_, "nome_processo"] = nome
    d["trilha"] = d.nativo_sei.map({True: "nativa", False: "migrada"})
    d["origem"] = "sei2"
    com_modelo = {p.stem.split("_")[1] for p in (SAIDA / "bpmn").glob("modelo_*.json")} - NOVOS
    # códigos com modelo: regra original (trilha nativa, ≥ 5 casos)
    m1 = (d.nativo_sei & (d.cobertura_substantivas >= COBERTURA_MIN) & (d.confianca != "baixa")
          & d.processo_principal.isin(com_modelo))
    a = d[m1].copy()
    a = a[a.groupby("processo_principal").numero.transform("size") >= min_casos]
    a["lote"] = 1
    # tipos novos: todo processo do SEI 2 de confiança média/alta (migrado entra pelo conteúdo) ...
    b = d[d.processo_principal.isin(NOVOS) & (d.confianca != "baixa")
          & (d.cobertura_substantivas >= COBERTURA_MIN)].copy()
    # ... e os que só existem no relator (sem trilha), se a classificação não for de confiança baixa e não tiver
    # sido rejeitada na verificação independente (saida/fase2/verificacao_classificacao.csv)
    rel = SAIDA / "fase2" / "classificacao_relator.csv"
    if rel.exists():
        r = pd.read_csv(rel)
        r["processo_principal"] = [_fora(c_, t_) for c_, t_ in zip(r.principal, r.tipo_novo)]
        r = r[r.processo_principal.isin(NOVOS) & (r.confianca != "baixa")]
        ver = SAIDA / "fase2" / "verificacao_classificacao.csv"
        if ver.exists():
            v = pd.read_csv(ver).set_index("numero")
            r["processo_principal"] = [v.loc[n, "codigo_verificado"] if n in v.index else c_
                                       for n, c_ in zip(r.numero, r.processo_principal)]
            r = r[r.processo_principal.isin(NOVOS)]
        if cob.exists():
            cc = pd.read_csv(cob).set_index("processo").cobertura_substantivas
            r = r[~r.numero.isin(cc.index) | (r.numero.map(cc) >= COBERTURA_MIN)]  # sem texto exportado ainda: fica
        cat = {c_["id"]: c_["nome"] for c_ in json.loads((SAIDA / "catalogo_processos.json").read_text(encoding="utf-8"))}
        b = pd.concat([b, pd.DataFrame(dict(numero=r.numero, processo_principal=r.processo_principal,
                                            nome_processo=r.processo_principal.map(lambda c_: cat.get(c_, NOME_FORA.get(c_))),
                                            encerrado=False, lead_du=float("nan"), n_docs=r.n_docs,
                                            cobertura_substantivas=float("nan"), confianca=r.confianca,
                                            trilha="sem", origem="relator"))], ignore_index=True)
    b["lote"] = 2
    co = pd.concat([a, b], ignore_index=True)
    dup = duplicatas(_hashes(co.numero), dict(zip(co.numero, co.trilha)))
    (SAIDA / "fase2").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(dict(numero=list(dup), original=list(dup.values()))).to_csv(
        SAIDA / "fase2" / "duplicados.csv", index=False, encoding="utf-8-sig")
    co = co[~co.numero.isin(dup)]
    piloto = set(pd.read_csv(SAIDA / "piloto.csv").numero)
    co["no_piloto"] = co.numero.isin(piloto)
    out = co[["numero", "processo_principal", "nome_processo", "lote", "origem", "trilha", "no_piloto", "encerrado",
              "lead_du", "n_docs", "cobertura_substantivas", "confianca"]].sort_values(["lote", "processo_principal", "numero"])
    out.to_csv(SAIDA / "coorte_fase2.csv", index=False, encoding="utf-8-sig")
    print(out.groupby(["lote", "processo_principal", "trilha"]).size().unstack(fill_value=0))


if __name__ == "__main__":
    main()
