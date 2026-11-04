"""Etapa 3b — ficha de trabalho por documento produzido pela AGENERSA nos processos-piloto.

Lê o texto exportado do relator (dados/relator/doc_text_piloto.parquet) e a análise map já existente, e pede
a um LLM (OpenRouter; modelo "claude-*" vai direto à API da Anthropic) a ficha: natureza do trabalho, tarefa, entregável, insumos, ferramentas, cálculos,
testes, competências, complexidade, fração autoral, horas estimadas e sinais de perda.

Peças externas (petições, anexos, e-mails e registros de entrada) não recebem ficha: são insumo, não
trabalho da agência. Cache por documento em dados/fichas/ (rodada retomável). Ficha em cache de outro modelo com a
mesma versão de prompt é reaproveitada (cada ficha registra o modelo que a gerou); --refazer-outros-modelos refaz.

Uso: python fichas_trabalho.py [--modelo google/gemini-3.6-flash | claude-haiku-5-5] [--workers 6] [--limite N]
Saída: saida/fichas_trabalho.csv (uma linha por documento) + saida/fichas_trabalho.jsonl (ficha completa)"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

from comum import DADOS, DESCRICAO_ORGAO, ORGAO, SAIDA, documentos
from fichas_atividades import limpar_pessoais

REL = DADOS / "relator"
CACHE = DADOS / "fichas"
PROMPT_VERSAO = "ficha-v2"
MAX_CHARS = 60_000  # acima disso, início + fim do texto
CATEGORIAS_COM_FICHA = {
    "parecer", "relatorio", "relatorio_fiscalizacao", "nota_tecnica", "informacao", "manifestacao_pge",
    "voto", "deliberacao", "decisao", "despacho_decisorio", "ato_normativo", "ata", "notificacao_autuacao",
    "despacho", "despacho_encaminhamento", "despacho_publicacao", "minuta", "oficio", "comunicacao_interna",
    "termo_encerramento", "publicacao", "outro",
}

NATUREZAS = ["encaminhamento", "comunicacao", "instrucao_processual", "analise_juridica", "analise_tecnica_engenharia",
             "analise_economico_financeira", "fiscalizacao_campo", "auditoria_conferencia", "relatoria_decisao",
             "publicacao_registro"]
TIPOS_INSUMO = ["documento_do_processo", "documento_da_regulada", "base_externa", "norma_ou_contrato",
                "vistoria_ou_campo", "sistema_ou_base_interna", "precedente_ou_jurisprudencia"]
AREAS = ["juridico_regulatoria", "economico_financeira_tarifaria", "engenharia_saneamento", "engenharia_gas_seguranca",
         "auditoria_controle", "dados_estatistica", "redacao_oficial", "gestao_processual", "atendimento_usuario",
         "ambiental", "contabil"]
SINAIS = ["pedido_complementacao", "devolucao_por_vicio", "refazimento", "diligencia_externa", "prazo_concedido",
          "reiteracao", "aguardando_outra_unidade", "sobrestamento"]

NATUREZAS_PRAZO = ["rito", "diligencia", "prorrogacao", "cumprimento", "interno"]

SISTEMA = f"""Você é analista de processos de uma agência reguladora ({DESCRICAO_ORGAO}). Recebe UM documento de um processo
SEI produzido por uma unidade da agência e descreve o TRABALHO QUE O AUTOR DESTE DOCUMENTO FEZ, para um mapeamento
de processos (AS-IS) e de competências. Regras obrigatórias:

1. Só o que o texto diz. Cada item traz "evidencia": um trecho COPIADO LITERALMENTE do documento (10 a 160 caracteres,
   sem reescrever, sem reticências no meio). Item sem trecho literal que o sustente NÃO entra.
2. Trabalho próprio × reproduzido. Cálculos, testes, verificações e análises que o documento apenas TRANSCREVE, RESUME
   ou CITA de outra peça ou unidade (ex.: voto que reproduz o cálculo da CAPET; relatório que resume parecer da
   Procuradoria) vão em "trabalho_reproduzido", NUNCA em "trabalho_proprio". Na dúvida, é reproduzido.
3. Fonte consultada × mencionada. Só entra em "fontes_externas_consultadas" a base que o próprio autor consultou para
   produzir o documento; fonte que só aparece em anexo ou em trecho transcrito não entra.
4. Ferramenta só com prova. Cada ferramenta/técnica precisa de trecho que mostre o autor usando-a (não basta o tema).
5. Nada de destino ou finalidade que o texto não declare.

Responda APENAS um JSON:
{{
 "natureza_trabalho": um de {NATUREZAS},
 "tarefa": "atividade no fluxo, verbo no infinitivo + objeto, até 8 palavras",
 "entregavel": "o que o documento entrega",
 "conclusao_de_merito": "posição tomada pelo autor (ex.: 'opina pelo indeferimento', 'diverge do cálculo da CAPET', 'afasta a penalidade') ou null",
 "insumos": [{{"tipo": um de {TIPOS_INSUMO}, "descricao": "curta", "evidencia": "trecho literal"}}],
 "documentos_examinados": [{{"descricao": "peça examinada pelo autor (nº, unidade)", "evidencia": "trecho literal"}}],
 "fontes_externas_consultadas": [{{"fonte": "...", "evidencia": "trecho literal"}}],
 "trabalho_proprio": {{
   "calculos": [{{"descricao": "cálculo feito pelo autor, com valores", "evidencia": "trecho literal"}}],
   "testes": [{{"descricao": "verificação de conformidade feita pelo autor", "evidencia": "trecho literal"}}],
   "ferramentas": [{{"nome": "ex.: cálculo tarifário paramétrico, fluxo de caixa, conferência documental, vistoria in loco, análise normativa, análise de precedentes, planilha", "evidencia": "trecho literal"}}]
 }},
 "trabalho_reproduzido": [{{"autor_ou_unidade": "...", "descricao": "o que foi reproduzido"}}],
 "competencias": [{{"area": um de {AREAS}, "nivel": "basico"|"intermediario"|"especialista", "evidencia": "trecho literal do trabalho PRÓPRIO que exige a competência"}}],
 "composicao_texto": {{"pct_autoral": 0-100, "pct_transcricao": 0-100, "pct_padrao": 0-100, "justificativa": "uma frase"}},
     (autoral = redação original do autor; transcrição = cópia/resumo extenso de outras peças, ementas, citações longas;
      padrão = cabeçalho, assinatura, fecho, fórmulas de praxe; os três somam 100)
 "complexidade": 1 a 5, "justificativa_complexidade": "uma frase",
     (1 expediente: encaminhar, dar ciência, juntar, publicar, certificar — sem análise;
      2 comunicação ou instrução simples: ofício/notificação padrão, despacho com uma determinação ou prazo;
      3 análise de poucas peças com conclusão, ou aplicação de fórmula/regra conhecida sem controvérsia;
      4 análise cruzada de várias peças ou dados com cálculo próprio, ou enfrentamento de posições divergentes;
      5 modelagem, cenários, revisão metodológica ou auditoria com bases externas. Peça que só reproduz análise alheia
      tem a complexidade do trabalho PRÓPRIO, não da análise reproduzida.)
 "horas_estimadas": número (trabalho de um servidor experiente para produzir o documento, incluindo leitura dos
     insumos que o próprio autor examinou; NÃO inclui espera), "justificativa_horas": "uma frase",
 "sinais_perda": [{{"tipo": um de {SINAIS}, "evidencia": "trecho literal"}}]
     (pedido_complementacao: pede dados/documentos que faltavam; devolucao_por_vicio: devolve por erro/insuficiência;
      refazimento: cancela, substitui, retifica ou refaz peça anterior, nova proposta após rejeição; reiteracao: repete
      pedido não atendido; aguardando_outra_unidade: espera manifestação interna; diligencia_externa: pede informação a
      terceiro; sobrestamento. Prazo de rito — defesa, razões finais, recurso — NÃO é perda.),
 "prazos": [{{"dias": inteiro, "beneficiario": "concessionaria"|"usuario"|"orgao_externo"|"unidade_interna",
     "natureza": um de {NATUREZAS_PRAZO}, "evidencia": "trecho literal"}}],
 "encaminha_para": {{"destino": "...", "finalidade": "...", "evidencia": "trecho literal"}} ou null
}}"""


def _norm_ev(s: str) -> str:
    s = re.sub(r"[\u2018\u2019\u201c\u201d\"'«»]", "", str(s or "")).lower()
    return re.sub(r"[\s\W_]+", " ", s).strip()


def ancorar(ficha: dict, texto: str) -> dict:
    """Marca cada item com evidência: ancorado se o trecho (normalizado) está no texto do documento."""
    t = _norm_ev(texto)

    def ok(ev):
        partes = [p for p in re.split(r"\.\.\.|…", str(ev or "")) if len(_norm_ev(p)) >= 8]
        return bool(partes) and all(_norm_ev(p) in t for p in partes)

    def marca(x):
        if isinstance(x, dict):
            if "evidencia" in x:
                x["ancorado"] = ok(x.get("evidencia"))
            for v in x.values():
                marca(v)
        elif isinstance(x, list):
            for v in x:
                marca(v)

    marca(ficha)
    return ficha


def legado(f: dict) -> dict:
    """Campos usados pelas etapas seguintes, preenchidos só com itens ancorados."""
    A = lambda xs: [x for x in (xs or []) if isinstance(x, dict) and x.get("ancorado")]  # noqa: E731
    tp = f.get("trabalho_proprio") or {}
    comp = f.get("composicao_texto") or {}
    externos = [p for p in A(f.get("prazos")) if p.get("beneficiario") != "unidade_interna"
                and p.get("natureza") != "prorrogacao"]
    enc = f.get("encaminha_para") if isinstance(f.get("encaminha_para"), dict) else None
    f.update(
        n_documentos_analisados=len(A(f.get("documentos_examinados"))),
        fontes_externas=[x.get("fonte") for x in A(f.get("fontes_externas_consultadas"))],
        ferramentas=[x.get("nome") for x in A(tp.get("ferramentas"))],
        calculos=[x.get("descricao") for x in A(tp.get("calculos"))],
        testes_auditoria=[x.get("descricao") for x in A(tp.get("testes"))],
        nao_ancorados=[x for k in ("insumos", "competencias", "sinais_perda", "documentos_examinados",
                                    "fontes_externas_consultadas", "prazos")
                       for x in (f.get(k) or []) if isinstance(x, dict) and not x.get("ancorado")]
        + [x for k in ("calculos", "testes", "ferramentas") for x in (tp.get(k) or [])
           if isinstance(x, dict) and not x.get("ancorado")],
        insumos=A(f.get("insumos")),
        competencias=A(f.get("competencias")),
        sinais_perda=[dict(x, descricao=x.get("evidencia")) for x in A(f.get("sinais_perda"))],
        fracao_autoral=(comp.get("pct_autoral") or 0) / 100,
        prazo_concedido_dias=externos[0]["dias"] if externos else None,
        encaminha_para=(f"{enc.get('destino')}: {enc.get('finalidade')}" if enc and enc.get("ancorado") else None),
    )
    return f


def _texto(t: str) -> str:
    t = re.sub(r"\n{3,}", "\n\n", t or "")
    if len(t) <= MAX_CHARS:
        return t
    return t[: int(MAX_CHARS * 0.7)] + "\n\n[... trecho omitido ...]\n\n" + t[-int(MAX_CHARS * 0.3):]


def _json(s: str) -> dict:
    s = s.strip()
    s = re.sub(r"^```(?:json)?|```$", "", s, flags=re.M).strip()
    i, j = s.find("{"), s.rfind("}")
    return json.loads(s[i: j + 1])


def chamar_anthropic(modelo: str, usuario: str) -> tuple[dict, dict]:
    import anthropic
    cliente = anthropic.Anthropic(max_retries=5)
    for tentativa in range(3):
        r = cliente.messages.create(model=modelo, max_tokens=16000, system=SISTEMA,
                                    messages=[{"role": "user", "content": usuario}])
        txt = next((b.text for b in r.content if b.type == "text"), "")
        try:
            if r.stop_reason != "end_turn":
                raise ValueError(f"stop_reason {r.stop_reason}")
            return _json(txt), {"prompt_tokens": r.usage.input_tokens, "completion_tokens": r.usage.output_tokens}
        except (json.JSONDecodeError, ValueError):
            if tentativa == 2:
                raise
    raise RuntimeError("sem resposta")


def chamar(modelo: str, usuario: str, chave: str) -> tuple[dict, dict]:
    if modelo.startswith("claude-"):
        return chamar_anthropic(modelo, usuario)
    corpo = {"model": modelo, "temperature": 0.1, "response_format": {"type": "json_object"},
             "messages": [{"role": "system", "content": SISTEMA}, {"role": "user", "content": usuario}]}
    for tentativa in range(5):
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions", json=corpo, timeout=180,
                              headers={"Authorization": f"Bearer {chave}"})
            if r.status_code in (429, 500, 502, 503):
                time.sleep(4 * (tentativa + 1))
                continue
            r.raise_for_status()
            dado = r.json()
            conteudo = dado["choices"][0]["message"]["content"]
            if not conteudo:
                raise ValueError("resposta vazia")
            return _json(conteudo), dado.get("usage", {})
        except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError):
            if tentativa == 4:
                raise
            time.sleep(4 * (tentativa + 1))
    raise RuntimeError("sem resposta")


def universo() -> set:
    """Processos com ficha: piloto e, se existir, a coorte da fase 2 (o arquivo de saída sempre cobre os dois,
    para nenhuma execução apagar fichas de outra)."""
    u = set(pd.read_csv(SAIDA / "piloto.csv").numero)
    if (SAIDA / "coorte_fase2.csv").exists():
        u |= set(pd.read_csv(SAIDA / "coorte_fase2.csv").numero)
    return u


def montar_tarefas(limite: int | None):
    alvo = universo()
    cls = pd.read_csv(SAIDA / "processos_classificados.csv").set_index("numero")
    docs = documentos()
    docs = docs[docs.numero_processo.isin(alvo) & docs.categoria.isin(CATEGORIAS_COM_FICHA)
                & docs.unidade.str.startswith(ORGAO, na=False)]
    txt = pd.read_parquet(REL / "doc_text_piloto.parquet")
    ext = pd.read_parquet(REL / "extractions.parquet")
    ext = ext[ext.processo.isin(alvo)].set_index(["processo", "sei_doc_id"])
    m = docs.merge(txt, left_on=["numero_processo", "numero"], right_on=["processo", "sei_doc_id"], how="inner")
    m = m[m.texto.str.strip().str.len() > 50]
    coorte = (pd.read_csv(SAIDA / "coorte_fase2.csv").set_index("numero") if (SAIDA / "coorte_fase2.csv").exists()
              else pd.DataFrame())

    def info(n):
        """Assunto, código e nome: classificação do SEI 2; processo só do relator vem da coorte (sem assunto)."""
        x = cls.loc[n] if n in cls.index else None
        cod = coorte.loc[n, "processo_principal"] if n in coorte.index else x.processo_principal
        nome = coorte.loc[n, "nome_processo"] if n in coorte.index else x.nome_processo
        return pd.Series(dict(assunto=x.assunto if x is not None else "(processo sem trilha no SEI 2)",
                              processo_principal=cod, nome_processo=nome))

    tarefas = []
    for r in m.itertuples():
        c = info(r.numero_processo)
        try:
            j = json.loads(ext.loc[(r.numero_processo, r.numero), "extraction_json"])
            refs = len((j.get("entidades") or {}).get("documentos_referenciados") or [])
        except KeyError:
            refs = 0
        usuario = (f"Processo SEI {r.numero_processo} — assunto: {c.assunto}\n"
                   f"Processo organizacional: {c.processo_principal} {c.nome_processo}\n"
                   f"Documento SEI {r.numero} · tipo: {r.tipo} · unidade autora: {r.unidade} · incluído em "
                   f"{str(r.data_inclusao)[:10]} · {len(r.texto)} caracteres · documentos referenciados (análise "
                   f"prévia): {refs}\n\n=== TEXTO ===\n{_texto(r.texto)}")
        tarefas.append(dict(processo=r.numero_processo, sei_doc_id=r.numero, tipo=r.tipo, categoria=r.categoria,
                            unidade=r.unidade, data_inclusao=str(r.data_inclusao)[:10], n_chars=len(r.texto),
                            estadia_idx=r.estadia_idx, usuario=usuario, _texto=r.texto))
    return tarefas[:limite] if limite else tarefas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", default="google/gemini-3.6-flash")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limite", type=int)
    ap.add_argument("--refazer-outros-modelos", action="store_true")
    ap.add_argument("--exportar", type=Path, help="grava o prompt de cada peça em PASTA/<chave>.txt e sai (sem API)")
    ap.add_argument("--importar", type=Path,
                    help="lê as respostas PASTA/<chave>.json (mesmo JSON que a API devolveria), ancora e grava no "
                         "cache; use --modelo para registrar quem respondeu (ex.: agente:claude-haiku-5-5)")
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    tarefas = montar_tarefas(args.limite)
    chave_arq = lambda t: f"{t['processo'].replace('/', '_')}__{t['sei_doc_id']}"  # noqa: E731
    if args.exportar:
        args.exportar.mkdir(parents=True, exist_ok=True)
        for t in tarefas:
            (args.exportar / f"{chave_arq(t)}.txt").write_text(
                f"=== SISTEMA ===\n{SISTEMA}\n\n=== USUÁRIO ===\n{t['usuario']}", encoding="utf-8")
        print(f"{len(tarefas)} prompts em {args.exportar}")
        return
    if args.importar:
        for t in tarefas:
            resp = args.importar / f"{chave_arq(t)}.json"
            if not resp.exists():
                continue
            ficha = legado(ancorar(_json(resp.read_text(encoding="utf-8")), t["_texto"]))
            dado = {k: v for k, v in t.items() if k != "usuario" and not k.startswith("_")} | {
                "ficha": ficha, "modelo": args.modelo, "prompt_versao": PROMPT_VERSAO}
            (CACHE / f"{chave_arq(t)}.json").write_text(json.dumps(dado, ensure_ascii=False, indent=1),
                                                        encoding="utf-8")
    chave = os.environ.get("OPENROUTER_API_KEY")
    var = "ANTHROPIC_API_KEY" if args.modelo.startswith("claude-") else "OPENROUTER_API_KEY"
    if not args.importar and not os.environ.get(var):
        raise SystemExit(f"{var} não definida")
    uso = {"prompt_tokens": 0, "completion_tokens": 0}
    erros = []

    def fazer(t):
        arq = CACHE / f"{t['processo'].replace('/', '_')}__{t['sei_doc_id']}.json"
        if arq.exists():
            dado = json.loads(arq.read_text(encoding="utf-8"))
            if dado.get("prompt_versao") == PROMPT_VERSAO and (dado.get("modelo") == args.modelo
                                                               or not args.refazer_outros_modelos):
                return dado, {}
        ficha, u = chamar(args.modelo, t["usuario"], chave)
        ficha = legado(ancorar(ficha, t["_texto"]))
        dado = {k: v for k, v in t.items() if k != "usuario" and not k.startswith("_")} | {
            "ficha": ficha, "modelo": args.modelo, "prompt_versao": PROMPT_VERSAO}
        arq.write_text(json.dumps(dado, ensure_ascii=False, indent=1), encoding="utf-8")
        return dado, u

    resultados = []
    with ThreadPoolExecutor(args.workers) as ex:
        futuros = {ex.submit(fazer, t): t for t in tarefas}
        for i, f in enumerate(as_completed(futuros), 1):
            try:
                dado, u = f.result()
                resultados.append(dado)
                for k in uso:
                    uso[k] += u.get(k, 0)
            except Exception as e:  # noqa: BLE001
                erros.append((futuros[f]["processo"], futuros[f]["sei_doc_id"], repr(e)[:200]))
            if i % 25 == 0:
                print(f"{i}/{len(tarefas)}", flush=True)

    # vai para o git: tira nome de usuário, endereço, CPF, e-mail e telefone citados nas peças
    resultados = [limpar_pessoais(d) for d in resultados]
    with open(SAIDA / "fichas_trabalho.jsonl", "w", encoding="utf-8") as fj:
        for d in sorted(resultados, key=lambda x: (x["processo"], x["data_inclusao"])):
            fj.write(json.dumps(d, ensure_ascii=False) + "\n")
    linhas = []
    for d in resultados:
        f = d["ficha"]
        linhas.append({**{k: d[k] for k in ["processo", "sei_doc_id", "tipo", "categoria", "unidade", "data_inclusao",
                                              "n_chars", "estadia_idx", "modelo"]},
                       "natureza_trabalho": f.get("natureza_trabalho"), "tarefa": f.get("tarefa"),
                       "entregavel": f.get("entregavel"), "complexidade": f.get("complexidade"),
                       "fracao_autoral": f.get("fracao_autoral"), "horas_llm": f.get("horas_estimadas"),
                       "n_documentos_analisados": f.get("n_documentos_analisados"),
                       "tipos_insumo": "; ".join(sorted({i.get("tipo", "") for i in f.get("insumos") or []})),
                       "fontes_externas": "; ".join(f.get("fontes_externas") or []),
                       "ferramentas": "; ".join(f.get("ferramentas") or []),
                       "calculos": "; ".join(f.get("calculos") or []),
                       "testes_auditoria": "; ".join(f.get("testes_auditoria") or []),
                       "competencias": "; ".join(f"{c.get('area')}:{c.get('nivel')}" for c in f.get("competencias") or []),
                       "sinais_perda": "; ".join(s.get("tipo", "") for s in f.get("sinais_perda") or []),
                       "prazo_concedido_dias": f.get("prazo_concedido_dias"),
                       "encaminha_para": f.get("encaminha_para")})
    pd.DataFrame(linhas).sort_values(["processo", "data_inclusao"]).to_csv(
        SAIDA / "fichas_trabalho.csv", index=False, encoding="utf-8-sig")
    print(f"fichas: {len(resultados)} · erros: {len(erros)} · tokens novos: {uso}")
    for e in erros[:10]:
        print("  erro", *e)


if __name__ == "__main__":
    main()
