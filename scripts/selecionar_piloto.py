"""Etapa 2b — junta indicadores e classificação e seleciona os processos-piloto.

Critérios (docs/METODO.md e docs/RESULTADOS_FASE0.md):
  elegível  = nativo do SEI (trilha completa) · encerrado (ciclo fechado) · 10 a 150 documentos ·
              ≥ 3 unidades ativas · ao menos uma peça de análise (parecer, relatório, nota técnica) ·
              nenhum documento sem estadia · classificação com confiança alta ou média ·
              ≥ 60% das peças substantivas com texto no banco do relator
  prioridade = processos organizacionais da Onda 1 do diagnóstico, depois os demais por ranking
  por processo organizacional: 1 caso típico (lead time mais próximo da mediana do grupo) e, onde
               houver ao menos 4 elegíveis, 1 caso crítico (mais espera dominante e iteração)

Saídas: saida/processos_classificados.csv, saida/piloto.csv"""
from __future__ import annotations

import numpy as np
import pandas as pd

from comum import DADOS, PECA_CARACTERISTICA, SAIDA
from dados_processos import RANKING  # catálogo do perfil (comum põe CATALOGO no sys.path)
from oficina_dados import ONDAS

MAX_CODIGOS = 8  # processos organizacionais cobertos no piloto
COBERTURA_MIN = 0.6  # fração das peças substantivas com texto disponível no banco do relator
SUBSTANTIVAS = {"parecer", "relatorio", "relatorio_fiscalizacao", "nota_tecnica", "voto", "deliberacao",
                "decisao", "despacho_decisorio", "notificacao_autuacao", "informacao", "manifestacao_pge", "ata"}
# peça que caracteriza o processo organizacional (o caso típico precisa tê-la): PECA_CARACTERISTICA, do perfil
RELATOR = DADOS / "relator" / "documentos.parquet"


def cobertura_texto() -> pd.DataFrame:
    """Por processo: fração dos documentos e das peças substantivas com texto no banco do relator."""
    docs = pd.read_csv(SAIDA / "documentos.csv", low_memory=False, dtype={"numero": str})
    docs = docs[docs.categoria != "processo_relacionado"]
    rel = pd.read_parquet(RELATOR, columns=["processo", "sei_doc_id", "download_status"])
    m = docs.merge(rel, left_on=["numero_processo", "numero"], right_on=["processo", "sei_doc_id"], how="left")
    m["ok"] = m.download_status.eq("ok")
    m["subst"] = m.categoria.isin(SUBSTANTIVAS)
    g = m.groupby("numero_processo")
    return pd.DataFrame({"cobertura_texto": g.ok.mean().round(3),
                         "cobertura_substantivas": g.apply(lambda x: x.loc[x.subst, "ok"].mean() if x.subst.any() else 0.0,
                                                           include_groups=False).round(3),
                         "restritos": g.download_status.apply(lambda s: int(s.eq("restricted").sum()))}
                        ).reset_index().rename(columns={"numero_processo": "numero"})


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--caso", action="append", default=[],
                    help="número SEI indicado pelo aluno: entra como 'estudo de caso' mesmo fora da elegibilidade")
    args = ap.parse_args()
    ind = pd.read_csv(SAIDA / "processos_indicadores.csv")
    cls = pd.read_csv(SAIDA / "classificacao_processos.csv")
    df = ind.merge(cls, on="numero", how="left", validate="1:1")
    df = df.merge(cobertura_texto(), on="numero", how="left")
    df[["cobertura_texto", "cobertura_substantivas"]] = df[["cobertura_texto", "cobertura_substantivas"]].fillna(0)
    rank = {r["id"]: r["rank"] for r in RANKING}
    nome = {r["id"]: r["nome"] for r in RANKING}
    onda = {pid: o for o, _, ids in ONDAS for pid in ids}
    df["nome_processo"] = df["processo_principal"].map(nome)
    df["rank_diagnostico"] = df["processo_principal"].map(rank)
    df["onda"] = df["processo_principal"].map(onda)
    df["elegivel_piloto"] = (df.nativo_sei & df.encerrado & df.n_docs.between(10, 150)
                             & (df.n_unidades_ativas >= 3) & ((df.n_pareceres + df.n_relatorios) >= 1)
                             & (df.docs_sem_estadia == 0) & (df.processo_principal != "LACUNA")
                             & (df.confianca != "baixa") & (df.cobertura_substantivas >= COBERTURA_MIN))
    df.to_csv(SAIDA / "processos_classificados.csv", index=False, encoding="utf-8-sig")

    el = df[df.elegivel_piloto].copy()
    el["log_lead"] = np.log1p(el.lead_du)
    el["riqueza"] = el.n_pareceres + el.n_relatorios + el.n_unidades_ativas
    el["criticidade"] = el.du_em_espera_dominante + 30 * el.retornos_iteracao + el.espera_externa_du
    total = df.groupby("processo_principal").size()

    def chave(pid):
        o = onda.get(pid)
        return (0 if o == "Onda 1" else 1, rank.get(pid, 99))

    codigos = sorted(el.processo_principal.unique(), key=chave)[:MAX_CODIGOS]
    escolha = []
    for pid in codigos:
        g = el[el.processo_principal == pid].copy()
        flag = PECA_CARACTERISTICA.get(pid)
        if flag and g[flag].any():
            g = g[g[flag]]
        g["dist"] = (g.log_lead - g.log_lead.median()).abs()
        tip = g.sort_values(["dist", "riqueza"], ascending=[True, False]).iloc[0]
        escolha.append((tip, "típico", f"lead time {tip.lead_du:.0f} du, mediana do grupo "
                                        f"{np.expm1(g.log_lead.median()):.0f} du ({len(g)} elegíveis de {total[pid]})"))
        resto = g[g.numero != tip.numero]
        if len(g) >= 4 and len(resto):
            cri = resto.sort_values("criticidade").iloc[-1]
            escolha.append((cri, "crítico", f"{cri.du_em_espera_dominante:.0f} du em espera dominante, "
                                            f"{cri.retornos_iteracao} retornos, {cri.espera_externa_du:.0f} du aguardando terceiros"))
    criterios = {"encerrado": "não encerrado", "nativo_sei": "não nativo do SEI"}
    for num in sorted(set(args.caso) - {r.numero for r, _, _ in escolha}):
        r = df[df.numero == num]
        if r.empty:
            raise SystemExit(f"--caso {num}: processo não está em processos_indicadores.csv")
        r = r.iloc[0]
        falhas = [txt for col, txt in criterios.items() if not r[col]]
        escolha.append((r, "estudo de caso", "indicado pelo aluno" + (f" ({'; '.join(falhas)})" if falhas else "")))
    linhas = []
    for r, papel, motivo in escolha:
        linhas.append(dict(numero=r.numero, processo_principal=r.processo_principal, nome_processo=r.nome_processo,
                           onda=r.onda, rank_diagnostico=r.rank_diagnostico, papel=papel, motivo=motivo,
                           assunto=r.assunto, interessado=r.interessado, lead_du=r.lead_du, n_docs=r.n_docs,
                           n_unidades_ativas=r.n_unidades_ativas, sequencia_ativa=r.sequencia_ativa,
                           n_pareceres=r.n_pareceres, n_relatorios=r.n_relatorios, retornos_iteracao=r.retornos_iteracao,
                           du_em_espera_dominante=r.du_em_espera_dominante, espera_externa_du=r.espera_externa_du,
                           tem_deliberacao=r.tem_deliberacao, confianca_classificacao=r.confianca,
                           cobertura_texto=r.cobertura_texto, cobertura_substantivas=r.cobertura_substantivas))
    pil = pd.DataFrame(linhas)
    pil.to_csv(SAIDA / "piloto.csv", index=False, encoding="utf-8-sig")
    print(f"elegíveis: {int(df.elegivel_piloto.sum())} de {len(df)}; piloto: {len(pil)} processos "
          f"em {pil.processo_principal.nunique()} processos organizacionais")


if __name__ == "__main__":
    main()
