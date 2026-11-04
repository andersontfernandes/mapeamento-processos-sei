"""Relatório executivo em PDF de um processo organizacional: resumo, modelo AS-IS, conformidade, TO-BE e especificação
das atividades, para a chefia do órgão.

Lê só saídas já validadas (modelo, fatos, avaliação, normas, conformidade, linha de base, melhorias, simulação e
controles). Nenhum número é digitado aqui: os valores vêm dos arquivos de saída. Entregável institucional: o texto não
menciona a ferramenta de análise nem caminhos locais.

Uso: python relatorio_pdf.py P06 [--saida ../docs/Relatorio_P06.pdf]"""
from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle, BaseDocTemplate, Frame)

from comum import DESCRICAO_BASE, ORGAO, SAIDA

AZUL = colors.HexColor("#1F3A5F")
CINZA = colors.HexColor("#5A6270")
CLARO = colors.HexColor("#EEF2F7")
VERDE = colors.HexColor("#2E7D4F")
VERMELHO = colors.HexColor("#B23A3A")
AMARELO = colors.HexColor("#B7851F")

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontSize=16, textColor=AZUL, spaceBefore=6, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=12.5, textColor=AZUL, spaceBefore=10, spaceAfter=4)
H3 = ParagraphStyle("H3", parent=ss["Heading3"], fontSize=10.5, textColor=AZUL, spaceBefore=6, spaceAfter=2)
P = ParagraphStyle("P", parent=ss["BodyText"], fontSize=9.5, leading=13, alignment=TA_LEFT, spaceAfter=4)
PEQ = ParagraphStyle("PEQ", parent=P, fontSize=8, leading=10.2, spaceAfter=0)
PEQB = ParagraphStyle("PEQB", parent=PEQ, fontName="Helvetica-Bold", textColor=colors.white)
NOTA = ParagraphStyle("NOTA", parent=P, fontSize=8.5, leading=11, textColor=CINZA)
DEST = ParagraphStyle("DEST", parent=P, fontSize=10, leading=14, backColor=CLARO, borderPadding=6, spaceBefore=4,
                      spaceAfter=8)


def neutro(s) -> str:
    """Texto para o entregável: sem sigla da ferramenta de análise; escapado para o Paragraph."""
    s = "" if s is None else str(s)
    s = re.sub(r"\b[Aa] IA\b", "a automação", s)
    s = re.sub(r"\bpela IA\b", "pela automação", s)
    s = re.sub(r"\bda IA\b", "da automação", s)
    s = re.sub(r"\bIA\b", "automação", s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def num(v, casas=0) -> str:
    if v is None:
        return "—"
    s = f"{v:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def faixa(a, b, casas=1) -> str:
    lo, hi = sorted([a or 0, b or 0])
    return f"{num(lo, casas)}–{num(hi, casas)}"


def tabela(linhas, larguras, cab=True, zebra=True):
    dados = [[c if not isinstance(c, str) else Paragraph(c, PEQB if (cab and i == 0) else PEQ) for c in l]
             for i, l in enumerate(linhas)]
    t = Table(dados, colWidths=larguras, repeatRows=1 if cab else 0)
    est = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C9D1DC")),
           ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if cab:
        est.append(("BACKGROUND", (0, 0), (-1, 0), AZUL))
    if zebra:
        for i in range(1 if cab else 0, len(linhas)):
            if i % 2 == 0:
                est.append(("BACKGROUND", (0, i), (-1, i), CLARO))
    t.setStyle(TableStyle(est))
    return t


# ------------------------------------------------------------------------------------------------ BPMN
NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL", "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
      "dc": "http://www.omg.org/spec/DD/20100524/DC", "di": "http://www.omg.org/spec/DD/20100524/DI"}


def desenho_bpmn(arq: Path, largura: float, nomes_modelo: dict | None = None) -> Drawing:
    raiz = ET.parse(arq).getroot()
    nomes, tipos = {}, {}
    for el in raiz.iter():
        tag = el.tag.split("}")[1]
        if el.get("id"):
            nomes[el.get("id")] = el.get("name") or ""
            tipos[el.get("id")] = tag
    formas = {s.get("bpmnElement"): s.find("dc:Bounds", NS) for s in raiz.iter(f"{{{NS['bpmndi']}}}BPMNShape")}
    arestas = [(e.get("bpmnElement"), [(float(w.get("x")), float(w.get("y"))) for w in e.findall("di:waypoint", NS)])
               for e in raiz.iter(f"{{{NS['bpmndi']}}}BPMNEdge")]
    rotulo_fluxo = {f.get("id"): f.get("name") or "" for f in raiz.iter(f"{{{NS['bpmn']}}}sequenceFlow")}
    xs = [float(b.get("x")) + float(b.get("width")) for b in formas.values() if b is not None]
    ys = [float(b.get("y")) + float(b.get("height")) for b in formas.values() if b is not None]
    W, H = max(xs) + 10, max(ys) + 10
    k = largura / W
    d = Drawing(largura, H * k)
    Y = lambda y: (H - y) * k  # noqa: E731

    def texto(cx, cy, s, tam=7, larg=None, cor=colors.black):
        palavras, linhas, atual = s.split(), [], ""
        lim = int((larg or 120) * k / (tam * 0.5)) if larg else 999
        for p_ in palavras:
            if len(atual) + len(p_) + 1 > lim and atual:
                linhas.append(atual)
                atual = p_
            else:
                atual = (atual + " " + p_).strip()
        if atual:
            linhas.append(atual)
        y0 = cy + (len(linhas) - 1) * tam * 0.55
        for i, l in enumerate(linhas):
            d.add(String(cx, y0 - i * tam * 1.1, l, fontSize=tam, textAnchor="middle", fillColor=cor))

    for el, b in formas.items():  # raias primeiro
        if b is None or tipos.get(el) not in ("lane", "participant"):
            continue
        x, y, w, h = (float(b.get(a)) for a in ("x", "y", "width", "height"))
        if tipos[el] == "lane":
            d.add(Rect(x * k, Y(y + h), w * k, h * k, fillColor=colors.white, strokeColor=CINZA, strokeWidth=0.5))
            d.add(Rect(x * k, Y(y + h), 18 * k, h * k, fillColor=CLARO, strokeColor=CINZA, strokeWidth=0.5))
            nm = nomes[el]
            sig = re.search(r"\(([^)]+)\)", nm)
            from reportlab.graphics.shapes import Group
            g_ = Group(String(0, 0, (sig.group(1) if sig else nm)[:16], fontSize=6.5, textAnchor="middle",
                              fillColor=AZUL))
            g_.transform = (0, 1, -1, 0, x * k + 9 * k + 2.3, Y(y + h / 2))
            d.add(g_)
    nomes.update(nomes_modelo or {})
    ignorar = {"textAnnotation", "association"}
    formas = {k_: v_ for k_, v_ in formas.items() if tipos.get(k_) not in ignorar}
    arestas = [(f_, p_) for f_, p_ in arestas if tipos.get(f_) not in ignorar]
    for fid, pts in arestas:
        if len(pts) < 2:
            continue
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            d.add(Line(x1 * k, Y(y1), x2 * k, Y(y2), strokeColor=CINZA, strokeWidth=0.8))
        (x1, y1), (x2, y2) = pts[-2], pts[-1]
        dx, dy = x2 - x1, y2 - y1
        n = max((dx * dx + dy * dy) ** 0.5, 1e-6)
        ux, uy = dx / n, dy / n
        a = 7
        bx, by = x2 - ux * a, y2 - uy * a
        d.add(Polygon([x2 * k, Y(y2), (bx - uy * a * 0.5) * k, Y(by + ux * a * 0.5),
                       (bx + uy * a * 0.5) * k, Y(by - ux * a * 0.5)], fillColor=CINZA, strokeColor=CINZA))
        r = rotulo_fluxo.get(fid)
        if r:
            d.add(String(pts[0][0] * k + 4, Y(pts[0][1]) + 3, r, fontSize=6.5, fillColor=AZUL))
    for el, b in formas.items():
        if b is None or tipos.get(el) in ("lane", "participant"):
            continue
        x, y, w, h = (float(b.get(a)) for a in ("x", "y", "width", "height"))
        t = tipos.get(el, "")
        cx, cy = (x + w / 2) * k, Y(y + h / 2)
        if t == "task":
            d.add(Rect(x * k, Y(y + h), w * k, h * k, rx=6 * k, ry=6 * k, fillColor=CLARO, strokeColor=AZUL,
                       strokeWidth=0.9))
            texto(cx, cy - 1, nomes[el], tam=5.8, larg=w - 4)
        elif "Gateway" in t:
            d.add(Polygon([cx, Y(y), (x + w) * k, cy, cx, Y(y + h), x * k, cy], fillColor=colors.white,
                          strokeColor=AMARELO, strokeWidth=0.9))
            d.add(String(cx, cy - 3, "X", fontSize=8, textAnchor="middle", fillColor=AMARELO))
            if nomes[el]:
                texto(cx, Y(y) + 8, nomes[el], tam=6, larg=150)
        else:
            cor = VERDE if t == "startEvent" else VERMELHO if t == "endEvent" else AMARELO
            larg_borda = 2 if t == "endEvent" else 1
            from reportlab.graphics.shapes import Circle
            d.add(Circle(cx, cy, w / 2 * k, fillColor=colors.white, strokeColor=cor, strokeWidth=larg_borda))
            if "intermediate" in t.lower() or "Catch" in t:
                d.add(Circle(cx, cy, w / 2 * k - 2, fillColor=None, strokeColor=cor, strokeWidth=0.6))
            if nomes[el]:
                texto(cx, Y(y + h) - 14, nomes[el], tam=6, larg=150)
    return d


# ------------------------------------------------------------------------------------------------ montagem
def carregar(cod: str) -> dict:
    j = lambda p: json.loads(p.read_text(encoding="utf-8")) if p.exists() else None  # noqa: E731
    b, f3 = SAIDA / "bpmn", SAIDA / "fase3"
    return dict(modelo=j(b / f"modelo_{cod}.json"), vinculos=j(b / f"vinculos_{cod}.json"),
                fatos=j(b / f"fatos_{cod}.json"), avaliacao=j(b / f"avaliacao_{cod}.json"),
                normas=j(f3 / f"normas_{cod}.json"), conformidade=j(f3 / f"conformidade_{cod}.json"),
                linha_base=j(f3 / f"linha_base_{cod}.json"), melhorias=j(f3 / f"melhorias_{cod}.json"),
                resultado=j(f3 / f"resultado_tobe_{cod}.json"), controles=j(f3 / f"controles_{cod}.json"),
                procedimento=j(SAIDA / "fase2" / f"procedimento_{cod}.json"), bpmn=b / f"{cod}.bpmn")


def fato(d, fid):
    for f in d["fatos"]["fatos"]:
        if f["id"] == fid:
            return f["valor"]
    return None


def capa(story, d, cod, numero):
    m = d["modelo"]
    story += [Spacer(1, 5 * cm), Paragraph(f"{ORGAO}", ParagraphStyle("c0", parent=H2, fontSize=13)),
              Paragraph("Mapeamento e melhoria de processo", ParagraphStyle("c1", parent=H1, fontSize=24, leading=28)),
              Spacer(1, 0.3 * cm),
              Paragraph(neutro(m["nome"]), ParagraphStyle("c2", parent=H2, fontSize=15, textColor=CINZA)),
              Spacer(1, 1 * cm),
              Paragraph(f"<b>Processo analisado:</b> {neutro(numero)}", P),
              Paragraph(f"<b>Base:</b> {neutro(DESCRICAO_BASE)}", P),
              Paragraph(f"<b>Escopo:</b> {neutro(m['escopo'])}", P),
              Paragraph(f"<b>Data:</b> {date.today().strftime('%d/%m/%Y')}", P),
              Spacer(1, 4 * cm),
              Paragraph("Documento de trabalho para validação com as unidades. Horas de trabalho, custos e ganhos são "
                        "estimativas a calibrar com os servidores; com um único processo, os números descrevem o caso e "
                        "não uma média do tipo de processo.", NOTA),
              PageBreak()]


def resumo(story, d):
    a, lb, conf = d["avaliacao"], d["linha_base"], d["conformidade"]
    story.append(Paragraph("1. Resumo executivo", H1))
    story.append(Paragraph(neutro(a["sintese"]), P))
    lead, esp, exe = fato(d, "critico.lead"), fato(d, "critico.espera_total"), fato(d, "critico.execucao_total")
    hp, ht = fato(d, "critico.horas_piso"), fato(d, "critico.horas_teto")
    req = conf["requisitos"] if conf else {}
    nconf = sum(1 for r in req.values() if r.get("nao_conforme"))
    conf_ = sum(1 for r in req.values() if r.get("conforme"))
    cards = [["Tempo total do processo", "Espera entre atividades", "Execução das atividades",
              "Trabalho estimado (hipótese)", "Requisitos legais conformes / não conformes"],
             [f"{num(lead)} dias úteis", f"{num(esp)} du", f"{num(exe)} du", f"{faixa(hp, ht, 0)} h",
              f"{conf_} / {nconf} de {len(req)}"]]
    t = Table([[Paragraph(f"<font size=7.5 color='#5A6270'>{neutro(x)}</font>", PEQ) for x in cards[0]],
               [Paragraph(f"<font size=13 color='#1F3A5F'><b>{x}</b></font>", PEQ) for x in cards[1]]],
              colWidths=[3.4 * cm] * 5)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CLARO), ("BOX", (0, 0), (-1, -1), 0.3, CINZA),
                           ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.white), ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [Spacer(1, 4), t, Spacer(1, 8)]
    g = a["gargalo"]
    story.append(Paragraph("Principal gargalo", H2))
    story.append(Paragraph(f"<b>{neutro(g['onde'])}</b>", DEST))
    story.append(Paragraph(neutro(g["evidencia"]), P))
    if d["resultado"]:
        story.append(Paragraph("Ganho projetado com o processo redesenhado", H2))
        story += tabela_cenarios(d)
    story.append(Paragraph("Oportunidades priorizadas", H2))
    linhas = [["#", "Oportunidade", "Impacto", "Esforço"]]
    for i, o in enumerate(a["oportunidades"], 1):
        linhas.append([str(i), f"<b>{neutro(o['titulo'])}</b><br/>{neutro(o['descricao'])}", neutro(o["impacto"]),
                       neutro(o["esforco"])])
    story.append(tabela(linhas, [0.7 * cm, 13.3 * cm, 1.6 * cm, 1.6 * cm]))


def tabela_cenarios(d):
    r = d["resultado"]
    base = r["linha_base"]["lead"]["mediana"]
    linhas = [["Fase", "Conservador", "Esperado", "Otimista", "Horas de trabalho (esperado)"]]
    linhas.append(["Atual (AS-IS)", f"{num(base)} du", f"{num(base)} du", f"{num(base)} du", "—"])
    for fase in sorted(r["fases"], key=int):
        f = r["fases"][fase]
        cel = [f"{num(f[c]['lead']['mediana'])} du (−{num(f[c]['ganho_lead_mediano_pct'], 1)}%)"
               for c in ("conservador", "esperado", "otimista")]
        linhas.append([f"Fase {fase}"] + cel + [f"−{num(f['esperado']['ganho_horas_media_pct'], 1)}%"])
    return [tabela(linhas, [3 * cm, 3.4 * cm, 3.4 * cm, 3.4 * cm, 4.1 * cm]),
            Paragraph("Lead time mediano do processo em dias úteis, simulado sobre a linha do tempo real do caso. "
                      "Fase 1: gestão de prazos e marcos; fase 2: painel, alertas e modelos de documento; fase 3: "
                      "minutas assistidas com revisão do servidor. Com um único caso, os percentuais indicam ordem de "
                      "grandeza.", NOTA)]


def asis(story, d):
    m, v, a = d["modelo"], d["vinculos"]["atividades"], d["avaliacao"]
    story.append(NextPageTemplate("paisagem"))
    story.append(PageBreak())
    story.append(Paragraph("2. Processo atual (AS-IS)", H1))
    story.append(Paragraph(neutro(m["escopo"]) + ". Raias: " + "; ".join(neutro(r["nome"]) for r in m["raias"]) + ".",
                           P))
    story.append(desenho_bpmn(d["bpmn"], 26.5 * cm, {e["id"]: e.get("nome", "") for e in m["elementos"]}))
    story.append(Paragraph("Modelo em notação BPMN 2.0 (arquivo .bpmn disponível para edição em ferramenta de "
                           "modelagem). O laço \"Há outras unidades a vistoriar?\" representa as rodadas sucessivas de "
                           "vistoria, relatório e encaminhamento observadas no processo.", NOTA))
    story.append(NextPageTemplate("retrato"))
    story.append(PageBreak())
    story.append(Paragraph("Tempo e trabalho por atividade", H2))
    lt = d["fatos"]["linha_do_tempo"]
    lt = next(iter(lt.values())) if isinstance(lt, dict) else lt
    agg = {}
    for o in lt:
        x = agg.setdefault(o["atividade"], dict(n=0, exe=0.0, esp=0.0, hp=0.0, ht=0.0, pecas=0))
        x["n"] += 1
        x["exe"] += o.get("execucao_du") or 0
        x["esp"] += o.get("espera_antes_du") or 0
        x["hp"] += o.get("horas_piso") or 0
        x["ht"] += o.get("horas_teto") or 0
        x["pecas"] += len(o.get("pecas") or [])
    tarefas = [e for e in m["elementos"] if e["tipo"] == "tarefa"]
    raia = {r["id"]: re.search(r"\(([^)]+)\)", r["nome"]).group(1) if "(" in r["nome"] else r["id"] for r in m["raias"]}
    linhas = [["Atividade", "Unidade", "Ocorrências", "Peças", "Execução (du)", "Espera antes (du)",
               "Horas (hipótese)", "Valor"]]
    for e in tarefas:
        x = agg.get(e["id"], dict(n=0, exe=0, esp=0, hp=0, ht=0, pecas=0))
        linhas.append([f"{e['id']} · {neutro(e['nome'])}", raia[e["raia"]], num(x["n"]), num(x["pecas"]),
                       num(x["exe"]), num(x["esp"]), faixa(x["hp"], x["ht"], 0),
                       neutro(a["atividades"].get(e["id"], {}).get("valor", ""))])
    story.append(tabela(linhas, [5.4 * cm, 1.6 * cm, 1.6 * cm, 1.2 * cm, 1.7 * cm, 1.8 * cm, 1.9 * cm, 2.3 * cm]))
    story.append(Paragraph("du = dias úteis. Execução: da primeira à última peça da ocorrência. Espera: do fim da "
                           "ocorrência anterior ao início desta. Horas: faixa entre a leitura da peça e laudas × "
                           "complexidade, a calibrar com estudo de tempo.", NOTA))
    story.append(Paragraph("Leitura das métricas", H2))
    story.append(Paragraph(neutro(a["leitura_metricas"]), P))
    story.append(Paragraph("Desperdícios identificados", H2))
    linhas = [["Tipo", "Evidência", "Atividades", "Severidade"]]
    for x in a["desperdicios"]:
        linhas.append([neutro(x["tipo"]), neutro(x["evidencia"]), ", ".join(x["atividades"]), neutro(x["severidade"])])
    story.append(tabela(linhas, [2.4 * cm, 11.2 * cm, 1.9 * cm, 1.8 * cm]))
    story.append(PageBreak())


def conformidade(story, d):
    n, c = d["normas"], d["conformidade"]
    if not (n and c):
        return
    story.append(Paragraph("3. Conformidade legal", H1))
    story.append(Paragraph(f"Requisitos extraídos de {len(n['normas'])} dispositivos normativos (lei de criação da "
                           "agência, regulamento, regimento interno, instrução normativa de fiscalização, lei estadual "
                           "de processo administrativo e lei federal de concessões), com o trecho literal de cada "
                           "dispositivo conferido contra o texto oficial. Cada requisito foi testado na linha do tempo "
                           "do processo.", P))
    linhas = [["Req.", "Exigência", "Critic.", "Resultado"]]
    cor = []
    for rid, r in c["requisitos"].items():
        if r.get("conforme"):
            res, k = "Conforme", VERDE
        elif r.get("nao_conforme"):
            res, k = "Não conforme", VERMELHO
        elif r.get("sem_evidencia"):
            res, k = "Sem evidência", AMARELO
        elif r.get("nao_aplicavel"):
            res, k = "Não aplicável", CINZA
        else:
            res, k = "Verificação manual", CINZA
        linhas.append([rid.replace("R-P06-", "R"), neutro(r["exigencia"]), neutro(r.get("criticidade", "")),
                       f"<font color='{k.hexval().replace('0x', '#')}'><b>{res}</b></font>"])
    story.append(tabela(linhas, [1.1 * cm, 11.9 * cm, 1.6 * cm, 2.7 * cm]))
    det = {r["id"]: r for r in n["requisitos"]}
    nc = [rid for rid, r in c["requisitos"].items() if r.get("nao_conforme")]
    if nc:
        story.append(Paragraph("Fundamento das não conformidades", H2))
        idx = {x["id"]: x for x in n["normas"]}
        for rid in nc:
            r = det.get(rid, {})
            fund = "; ".join(f"{neutro(idx[i]['norma'])}, {neutro(idx[i]['dispositivo'])}" for i in r.get("normas", [])
                             if i in idx)
            story.append(Paragraph(f"<b>{rid.replace('R-P06-', 'R')}</b> — {neutro(r.get('exigencia'))} "
                                   f"<i>Parâmetro:</i> {neutro(r.get('parametro'))}. <i>Base:</i> {fund}.", P))
    story.append(Paragraph("Com um único processo, cada resultado vale para o caso; a taxa de conformidade do tipo de "
                           "processo exige a análise de outros processos. Interpretações de prazo a confirmar com a "
                           "Procuradoria.", NOTA))
    story.append(PageBreak())


def tobe(story, d):
    mel = d["melhorias"]
    if not mel:
        return
    story.append(Paragraph("4. Processo redesenhado (TO-BE)", H1))
    nomes_fase = {1: "Fase 1 — gestão de prazos e marcos", 2: "Fase 2 — painel, alertas e modelos de documento",
                  3: "Fase 3 — minutas assistidas com revisão do servidor"}
    por_fase = {}
    for x in mel["melhorias"]:
        por_fase.setdefault(x["fase"], []).append(x)
    for fase in sorted(por_fase):
        story.append(Paragraph(nomes_fase.get(fase, f"Fase {fase}"), H2))
        linhas = [["Id", "Melhoria", "Ativ.", "Base"]]
        for x in por_fase[fase]:
            base = "hipótese a validar" if x.get("hipotese") else "requisito / referência"
            ctrl = x.get("controle_humano")
            linhas.append([x["id"].replace("M-P06-", "M"),
                           f"<b>{neutro(x.get('titulo'))}</b><br/>{neutro(x.get('descricao'))}"
                           + (f"<br/><i>Decisão que fica com o servidor:</i> {neutro(ctrl)}" if ctrl else ""),
                           ", ".join(x.get("atividades") or []), base])
        story.append(tabela(linhas, [1.1 * cm, 12.6 * cm, 1.4 * cm, 2.2 * cm]))
    r = d["resultado"]
    if r:
        story.append(Paragraph("Simulação", H2))
        story += tabela_cenarios(d)
        story.append(Paragraph("Sensibilidade", H3))
        sens = r["sensibilidade"]["sem_cada_melhoria"]
        linhas = [["Melhoria retirada", "Fase", "Aumento do lead (du)", "Aumento de horas"]]
        for s_ in sens:
            linhas.append([s_["melhoria"].replace("M-P06-", "M"), str(s_["fase"]), num(s_["lead_mediano_du"]),
                           num(s_["horas_medias"], 1)])
        story.append(tabela(linhas, [4 * cm, 2 * cm, 4 * cm, 4 * cm]))
        story.append(Paragraph("<b>Atenção:</b> retirando uma melhoria por vez, as da fase 1 aparecem sem efeito porque "
                               "as da fase 2 atuam nas mesmas esperas. O ganho depende, sobretudo, do prazo interno para "
                               "o parecer jurídico (M3 e M8), que exige acordo e capacidade da Procuradoria.", P))
    story.append(Paragraph("Prazos legais concedidos à concessionária e o tempo de resposta de terceiros não foram "
                           "reduzidos na simulação.", NOTA))
    story.append(PageBreak())


def controles(story, d):
    c = d["controles"]
    if not c:
        return
    story.append(Paragraph("5. Controles e metas", H1))
    linhas = [["Indicador", "Linha de base", "Metas (fase 1 / 2 / 3)", "Responsável e alerta"]]
    for x in c["indicadores"]:
        lb = x.get("linha_base") or {}
        metas = " / ".join(num(m_["valor"], 1 if isinstance(m_["valor"], float) and m_["valor"] % 1 else 0)
                           for m_ in sorted(x.get("metas") or [], key=lambda m_: m_.get("fase", 0)))
        al = x.get("alerta") or {}
        linhas.append([f"<b>{neutro(x['nome'])}</b><br/>{neutro(x.get('definicao'))[:420]}",
                       f"{num(lb.get('valor'), 1 if isinstance(lb.get('valor'), float) and lb.get('valor') % 1 else 0)} {neutro(lb.get('unidade', ''))}",
                       metas or "—",
                       f"{neutro(x.get('responsavel'))}<br/><i>Alerta:</i> {neutro(al.get('regra', ''))[:260]}"])
    story.append(tabela(linhas, [7.3 * cm, 2.2 * cm, 2.6 * cm, 5.2 * cm]))
    q = c.get("controles_qualidade_ia") or []
    if q:
        story.append(Paragraph("Controles de qualidade das minutas automatizadas", H2))
        linhas = [["Id", "Verificação", "Amostragem", "Critério de aceite", "Responsável"]]
        for x in q:
            linhas.append([neutro(x["id"]), neutro(x.get("verificacao")), neutro(x.get("amostragem")),
                           neutro(x.get("criterio_aceite")), neutro(x.get("responsavel"))])
        story.append(tabela(linhas, [1.4 * cm, 5.6 * cm, 3.4 * cm, 4.4 * cm, 2.5 * cm]))
    story.append(PageBreak())


def especificacao(story, d):
    m, v, a = d["modelo"], d["vinculos"]["atividades"], d["avaliacao"]["atividades"]
    story.append(Paragraph("6. Especificação das atividades", H1))
    story.append(Paragraph("Para cada atividade do processo: o que a dispara, o que entrega, o trabalho observado nas "
                           "peças, o que pode ser automatizado e o que permanece como decisão do servidor.", P))
    raia = {r["id"]: r["nome"] for r in m["raias"]}
    for e in [e for e in m["elementos"] if e["tipo"] == "tarefa"]:
        vi, av = v.get(e["id"], {}), a.get(e["id"], {})
        linhas = [["Campo", "Especificação"],
                  ["Unidade responsável", neutro(raia[e["raia"]])],
                  ["Gatilho", neutro(e.get("gatilho") or vi.get("gatilho"))],
                  ["Entrega", neutro(e.get("saida") or vi.get("saida"))],
                  ["Trabalho observado", neutro(vi.get("descritivo"))],
                  ["Observações", neutro(vi.get("observacoes"))],
                  ["Classificação de valor", f"{neutro(av.get('valor'))} — {neutro(av.get('justificativa_valor'))}"],
                  ["Melhoria de fluxo", neutro(av.get("melhoria_lean"))],
                  ["Potencial de automação", f"{neutro(av.get('potencial_ia'))} — {neutro(av.get('aplicacao_ia'))}"],
                  ["Decisão humana", neutro(av.get("controle_humano"))],
                  ["Peças vinculadas", str(len(vi.get("docs") or []))]]
        story.append(KeepTogether([Paragraph(f"{e['id']} · {neutro(e['nome'])}", H2),
                                   tabela(linhas, [3.6 * cm, 13.7 * cm], zebra=False)]))
    story.append(PageBreak())


def validacao(story, d):
    a = d["avaliacao"]
    story.append(Paragraph("7. Indicadores sugeridos e pontos a validar", H1))
    story.append(Paragraph("Indicadores sugeridos", H2))
    for x in a["indicadores_sugeridos"]:
        story.append(Paragraph("• " + neutro(x if isinstance(x, str) else x.get("nome") or x), P))
    story.append(Paragraph("Perguntas para validação com as unidades", H2))
    for i, x in enumerate(a["perguntas_validacao"], 1):
        story.append(Paragraph(f"{i}. " + neutro(x if isinstance(x, str) else x.get("pergunta") or x), P))
    story.append(Paragraph("Método e ressalvas", H2))
    story.append(Paragraph(
        "O mapeamento foi reconstruído a partir do registro do próprio processo no SEI: andamentos, documentos "
        "juntados e texto integral das peças, obtidos da Pesquisa Pública. Cada peça teve o trabalho descrito com "
        "trecho literal do documento como evidência, e uma amostra foi revisada de forma independente. Tempos são "
        "calculados em dias úteis com o calendário de feriados do Estado. Os requisitos legais citam o texto literal "
        "das normas. Ressalvas: (i) estudo de um único processo, sem comparação com outros do mesmo tipo; (ii) horas "
        "de trabalho e custos são estimativas a calibrar com estudo de tempo junto aos servidores; (iii) datas são "
        "as de juntada no SEI, não as de vistoria ou de assinatura; (iv) respostas da concessionária que tramitaram em "
        "processos relacionados não fazem parte da base; (v) o modelo e as perguntas acima devem ser validados com a "
        "Câmara de Saneamento, a Secretaria Executiva e a Procuradoria.", P))


def rodape(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(CINZA)
    w, h = doc.pagesize
    canvas.drawString(1.8 * cm, 1 * cm, f"{ORGAO} · Mapeamento e melhoria de processo · Fiscalização técnica de campo")
    canvas.drawRightString(w - 1.8 * cm, 1 * cm, f"{doc.page}")
    canvas.restoreState()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("codigo")
    ap.add_argument("--saida", type=Path)
    args = ap.parse_args()
    cod = args.codigo
    d = carregar(cod)
    numero = next(iter(d["fatos"]["linha_do_tempo"])) if isinstance(d["fatos"]["linha_do_tempo"], dict) else cod
    destino = args.saida or (SAIDA.parent / "docs" / f"Relatorio_{cod}.pdf")
    doc = BaseDocTemplate(str(destino), pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.6 * cm,
                          bottomMargin=1.6 * cm, title=f"Mapeamento e melhoria de processo — {cod}", author=ORGAO)
    fr = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    pw, ph = landscape(A4)
    fl = Frame(1.5 * cm, 1.5 * cm, pw - 3 * cm, ph - 3 * cm, id="fl")
    doc.addPageTemplates([PageTemplate("retrato", [fr], onPage=rodape, pagesize=A4),
                          PageTemplate("paisagem", [fl], onPage=rodape, pagesize=landscape(A4))])
    story = []
    capa(story, d, cod, numero)
    resumo(story, d)
    asis(story, d)
    conformidade(story, d)
    tobe(story, d)
    controles(story, d)
    especificacao(story, d)
    validacao(story, d)
    doc.build(story)
    print(destino)


if __name__ == "__main__":
    main()
