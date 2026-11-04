"""Fase 2 — classificador de atividade: cada peça PRÓPRIA de cada processo da coorte recebe a atividade canônica
do modelo do seu código (saida/bpmn/modelo_<Pxx>.json) ou "fora_do_modelo".

É o passo que transforma peças soltas em ocorrências comparáveis entre casos. Regras:
  - só peças da agência (unidade AGENERSA/...) são rotuladas; as de fora entram como contexto da sequência;
  - candidatas de uma peça = atividades cuja raia é a unidade da peça (mesma regra de na_raia da linha do tempo);
    peça sem candidata fica "fora_da_raia" sem consulta ao modelo de linguagem;
  - o modelo vê a sequência inteira do processo (data, unidade, tipo, tarefa e entregável da ficha, ação e
    pedidos da análise do relator) e as atividades com gatilho e saída; responde em JSON validado por esquema;
  - rótulo fora das candidatas da peça é descartado (vira "fora_do_modelo", motivo registrado).
Gabarito: os vínculos peça → atividade do piloto (auditados). `--avaliar` roda só os casos do piloto e mede a
concordância nas peças próprias vinculadas; critério da fase 2: ≥ 85%.

Modelo: Claude Haiku 5.5 (API da Anthropic; ANTHROPIC_API_KEY). Cache por processo em dados/classificador/.
Saídas: saida/fase2/atribuicoes_<Pxx>.csv; com --avaliar, saida/fase2/avaliacao_classificador.json"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic
import pandas as pd

from comum import DADOS, DESCRICAO_ORGAO, ORGAO, SAIDA, documentos
from fatos import na_raia
from fichas_atividades import limpar_pessoais

MODELO = "claude-haiku-5-5"
VERSAO = "classif-v1"
DIR = SAIDA / "bpmn"
OUT = SAIDA / "fase2"
CACHE = DADOS / "classificador"
FORA = "fora_do_modelo"

SISTEMA = """Você é analista de processos de uma agência reguladora (""" + DESCRICAO_ORGAO + """). Recebe o modelo canônico de um
procedimento interno (atividades, com a unidade responsável, o gatilho e a saída) e a sequência real de peças de UM
processo SEI. Sua tarefa: dizer, para cada peça marcada ROTULAR, qual atividade do modelo ela executa.

Regras:
- Escolha só entre as candidatas listadas na própria peça, ou "fora_do_modelo" quando a peça faz algo que nenhuma
  candidata descreve (outra demanda, ato administrativo alheio ao procedimento, etapa que o modelo não prevê).
- Peças de trâmite (despacho de encaminhamento, e-mail, recibo) pertencem à atividade que a unidade está
  executando naquele momento: a que a peça abre, conclui ou comunica.
- A ordem importa: use as peças vizinhas e as peças externas (respostas, petições) para situar a peça. Uma
  atividade pode se repetir (laço, nova rodada de pedidos).
- Baseie-se no que está escrito (tipo, tarefa, entregável, ação). Não invente conteúdo.
- confiança: alta = a peça é inequívoca; media = depende da posição na sequência; baixa = palpite.
- motivo: uma frase curta."""


def carregar_contexto():
    docs = documentos(parse_dates=["data_inclusao"])
    docs = docs[docs.categoria != "processo_relacionado"]
    fichas = {}
    for ln in open(SAIDA / "fichas_trabalho.jsonl", encoding="utf-8"):
        d = json.loads(ln)
        f = d["ficha"]
        fichas[(d["processo"], str(d["sei_doc_id"]))] = (f.get("tarefa") or "", f.get("entregavel") or "")
    ext = pd.read_parquet(DADOS / "relator" / "extractions.parquet", columns=["processo", "sei_doc_id",
                                                                                    "extraction_json"])
    rel = {}
    for p, s, j in zip(ext.processo, ext.sei_doc_id, ext.extraction_json):
        x = json.loads(j)
        ped = x.get("pedidos_e_determinacoes") or []
        rel[(p, str(s))] = (str(x.get("acao_processual") or ""), "; ".join(map(str, ped))[:240])
    return docs, fichas, rel


def montar(cod: str, numero: str, docs, fichas, rel):
    mod = json.loads((DIR / f"modelo_{cod}.json").read_text(encoding="utf-8"))
    # gatilho e saída genéricos do modelo valem primeiro; os dos vínculos descrevem o caso-piloto e só suprem o
    # modelo que não os tem (tipos do piloto modelados antes da fase 2)
    arq_v = DIR / f"vinculos_{cod}.json"
    vin = json.loads(arq_v.read_text(encoding="utf-8"))["atividades"] if arq_v.exists() else {}
    vin = {**vin, **{e["id"]: e for e in mod["elementos"] if e.get("gatilho")}}
    raias = {r["id"]: (r["id"] + " " + r["nome"]).upper() for r in mod["raias"]}
    tarefas = [e for e in mod["elementos"] if e["tipo"] == "tarefa"]
    ativ_txt = "\n".join(
        f"- {e['id']} [{raias[e['raia']].title()}] {e['nome']} | gatilho: {vin.get(e['id'], {}).get('gatilho') or '-'}"
        f" | saída: {vin.get(e['id'], {}).get('saida') or '-'}" for e in tarefas)
    dp = docs[docs.numero_processo == numero].sort_values(["data_inclusao", "numero"])
    linhas, pecas = [], []
    for r in dp.itertuples():
        u = str(r.unidade or "")
        propria = u.startswith(ORGAO + "/")
        cand = [e["id"] for e in tarefas if propria and na_raia(u, raias[e["raia"]])]
        tarefa, entreg = fichas.get((numero, r.numero), ("", ""))
        acao, ped = rel.get((numero, r.numero), ("", ""))
        desc = " · ".join(x for x in [f"tarefa: {tarefa}" if tarefa else "", f"entregável: {entreg}" if entreg else "",
                                      f"ação: {acao}" if acao else "", f"pedidos: {ped}" if ped else ""] if x)
        i = len(pecas)
        pecas.append(dict(i=i, ref=f"{numero}:{r.numero}", unidade=u, tipo=r.tipo, propria=propria, cand=cand))
        marca = (f"ROTULAR — candidatas: {', '.join(cand)}" if cand else
                 ("própria, fora das raias do modelo" if propria else "externa (contexto)"))
        linhas.append(f"[{i}] {str(r.data_inclusao)[:10]} · {u.split('/')[-1] if propria else u} · {r.tipo} · {marca}"
                      + (f"\n     {desc}" if desc else ""))
    usuario = (f"Procedimento {cod} — {mod['nome']}\nEscopo: {mod.get('escopo', '')}\n\nAtividades do modelo:\n"
               f"{ativ_txt}\n\nProcesso {numero} — peças em ordem de juntada:\n" + "\n".join(linhas)
               + "\n\nRotule todas as peças marcadas ROTULAR.")
    ids = [e["id"] for e in tarefas] + [FORA]
    return usuario, pecas, ids


def esquema(ids):
    return {"type": "object", "additionalProperties": False, "required": ["rotulos"],
            "properties": {"rotulos": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["peca", "atividade", "confianca", "motivo"],
                "properties": {"peca": {"type": "integer"}, "atividade": {"type": "string", "enum": ids},
                               "confianca": {"type": "string", "enum": ["alta", "media", "baixa"]},
                               "motivo": {"type": "string"}}}}}}


def classificar(cliente, cod, numero, docs, fichas, rel) -> pd.DataFrame:
    usuario, pecas, ids = montar(cod, numero, docs, fichas, rel)
    arq = CACHE / f"{numero.replace('/', '_')}.json"
    alvo = [p for p in pecas if p["cand"]]
    if arq.exists() and (c := json.loads(arq.read_text(encoding="utf-8"))).get("versao") == VERSAO \
            and c.get("modelo") == MODELO and c.get("usuario") == usuario:
        rot = c["rotulos"]
    elif alvo:
        # processo longo (150+ peças) passa de 16 mil tokens de saída: streaming com teto maior
        with cliente.messages.stream(model=MODELO, max_tokens=48000, system=SISTEMA,
                                     messages=[{"role": "user", "content": usuario}],
                                     output_config={"format": {"type": "json_schema", "schema": esquema(ids)}}) as st:
            r = st.get_final_message()
        if r.stop_reason != "end_turn":
            raise RuntimeError(f"{numero}: stop_reason {r.stop_reason}")
        rot = json.loads(next(b.text for b in r.content if b.type == "text"))["rotulos"]
        arq.write_text(json.dumps(dict(versao=VERSAO, modelo=MODELO, usuario=usuario, rotulos=rot,
                                       uso=r.usage.model_dump()), ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        rot = []
    por_i = {x["peca"]: x for x in rot}
    out = []
    for p in pecas:
        if not p["propria"]:
            continue
        x = por_i.get(p["i"])
        if not p["cand"]:
            ativ, conf, mot = "fora_da_raia", "", "unidade sem raia no modelo"
        elif x is None:
            ativ, conf, mot = FORA, "", "sem rótulo na resposta"
        elif x["atividade"] != FORA and x["atividade"] not in p["cand"]:
            ativ, conf, mot = FORA, "baixa", f"rótulo {x['atividade']} fora das candidatas da unidade"
        else:
            ativ, conf, mot = x["atividade"], x["confianca"], x["motivo"]
        out.append(dict(codigo=cod, processo=numero, ref=p["ref"], unidade=p["unidade"], tipo=p["tipo"],
                        atividade=ativ, confianca=conf, motivo=limpar_pessoais(mot)))  # vai para o git
    return pd.DataFrame(out)


def gabarito(cod: str) -> dict:
    """ref → atividade, das peças próprias vinculadas no piloto (só as da raia, como na linha do tempo)."""
    mod = json.loads((DIR / f"modelo_{cod}.json").read_text(encoding="utf-8"))
    raias = {r["id"]: (r["id"] + " " + r["nome"]).upper() for r in mod["raias"]}
    tarefas = {e["id"]: e for e in mod["elementos"] if e["tipo"] == "tarefa"}
    docs = documentos()
    uni = dict(zip(docs.numero_processo + ":" + docs.numero, docs.unidade.fillna("")))
    vin = json.loads((DIR / f"vinculos_{cod}.json").read_text(encoding="utf-8"))["atividades"]
    return {r: t for t, a in vin.items() if t in tarefas for r in a.get("docs", [])
            if na_raia(uni.get(r, ""), raias[tarefas[t]["raia"]])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--avaliar", action="store_true", help="só os casos do piloto, contra os vínculos auditados")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--gabarito", action="store_true",
                    help="coorte só com casos do piloto: grava as atribuições a partir dos vínculos auditados, sem "
                         "consultar o modelo de linguagem (estudo de caso)")
    args = ap.parse_args()
    coorte = pd.read_csv(SAIDA / "coorte_fase2.csv")
    coorte = coorte[[(DIR / f"modelo_{c}.json").exists() for c in coorte.processo_principal]]
    if args.gabarito:
        if not coorte.no_piloto.all():
            raise SystemExit("--gabarito só vale quando toda a coorte está no piloto")
        OUT.mkdir(parents=True, exist_ok=True)
        docs = documentos()
        docs = docs.assign(ref=docs.numero_processo + ":" + docs.numero)
        for cod, g in coorte.groupby("processo_principal"):
            gab = gabarito(cod)
            d = docs[docs.numero_processo.isin(g.numero) & docs.unidade.str.startswith(ORGAO, na=False)]
            tab = pd.DataFrame(dict(codigo=cod, processo=d.numero_processo, ref=d.ref, unidade=d.unidade, tipo=d.tipo,
                                    atividade=d.ref.map(gab).fillna("fora_do_modelo"), confianca="alta",
                                    motivo=d.ref.map(lambda r: "vínculo auditado do piloto" if r in gab
                                                     else "peça sem vínculo no piloto")))
            tab.sort_values(["processo", "ref"]).to_csv(OUT / f"atribuicoes_{cod}.csv", index=False,
                                                        encoding="utf-8-sig")
            print(cod, tab.processo.nunique(), "processos;", tab.atividade.value_counts().to_dict())
        return
    if args.avaliar:
        coorte = coorte[coorte.no_piloto]
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    docs, fichas, rel = carregar_contexto()
    cliente = anthropic.Anthropic()
    res, erros = [], []
    with ThreadPoolExecutor(args.workers) as ex:
        fut = {ex.submit(classificar, cliente, r.processo_principal, r.numero, docs, fichas, rel): r.numero
               for r in coorte.itertuples()}
        for f in as_completed(fut):
            try:
                res.append(f.result())
            except Exception as e:  # noqa: BLE001
                erros.append(f"{fut[f]}: {e}")
    tab = pd.concat(res, ignore_index=True)
    for e in erros:
        print("ERRO", e)
    if args.avaliar:
        rel_ = {}
        for cod, g in tab.groupby("codigo"):
            gab = gabarito(cod)
            m = g[g.ref.isin(gab)]
            ok = (m.atividade == m.ref.map(gab))
            rel_[cod] = dict(pecas_no_gabarito=len(m), concordancia=round(ok.mean(), 3) if len(m) else None,
                             erros=[dict(ref=r.ref, tipo=r.tipo, previsto=r.atividade, gabarito=gab[r.ref],
                                         motivo=r.motivo) for r in m[~ok].itertuples()],
                             fora_do_gabarito_rotuladas=int((~g.ref.isin(gab) & g.atividade.str.match(r"^t\d")).sum()))
        tot = sum(v["pecas_no_gabarito"] for v in rel_.values())
        acc = sum(v["concordancia"] * v["pecas_no_gabarito"] for v in rel_.values() if v["concordancia"] is not None)
        rel_["_total"] = dict(pecas_no_gabarito=tot, concordancia=round(acc / tot, 3) if tot else None)
        (OUT / "avaliacao_classificador.json").write_text(json.dumps(rel_, ensure_ascii=False, indent=1),
                                                         encoding="utf-8")
        for k, v in rel_.items():
            print(k, v["pecas_no_gabarito"], v["concordancia"])
        return
    for cod, g in tab.groupby("codigo"):
        g.sort_values(["processo", "ref"]).to_csv(OUT / f"atribuicoes_{cod}.csv", index=False, encoding="utf-8-sig")
        print(cod, g.processo.nunique(), "processos;", g.atividade.value_counts().to_dict())


if __name__ == "__main__":
    main()
