# AS-IS dos processos-piloto (reconstruído do SEI)

Gerado por `scripts/asis_piloto.py`. Horas = modelo por conteúdo (laudas autorais × complexidade + leitura de insumos + fontes externas), hipótese a calibrar. du = dias úteis. Nos fluxos, cada caixa é uma passagem em que a unidade juntou documento; vermelho = espera dominante (≥ 20 du com trabalho < 5% da capacidade); amarelo = a peça registra sinal de perda (complementação, diligência, prazo, reiteração).

## P06 — Fiscalização técnica de campo (programada e por demanda)

| Processo SEI | Caso | Lead time (du) | Documentos | Laudas produzidas | Horas (modelo) | Eficiência do ciclo | Tempo em espera dominante |
|---|---|---|---|---|---|---|---|
| SEI-480002/001314/2024 | estudo de caso | 636 | 75 | 336 | 491 | 12.9% | 89% |

**Onde está o trabalho:** Fiscalização de campo 92%; Análise jurídica 3%; Análise técnica de engenharia 3%; Comunicação 2%; Encaminhamento 0%.
**Competências exigidas (por horas):** Engenharia de saneamento (intermediário); Auditoria e controle (intermediário); Jurídico-regulatória (especialista); Ambiental (intermediário); Gestão processual (intermediário); Redação oficial (básico).
**Insumos:** vistoria ou campo (44); documento do processo (11); documento da regulada (10); norma ou contrato (6).
**Ferramentas e técnicas mais usadas:** vistoria in loco (35); conferência documental (7); registro fotográfico (4); checklist de conformidade (anexo) (4); análise normativa (3); vistoria in loco com checklist (2).
**Exemplos de cálculo:** nível do poço de sucção de 1,3 m medido na vistoria, com o tanque de cerca de 3 m de profundidade; nível do poço de sucção de 1,48 m medido na vistoria, indicado como 30% da capacidade; potência em operação: 3 motores de 150 cv, total de 450 cv; balanço de vazões registrado nos medidores: água bruta, água de barragem e água tratada, em l/s.
**Sinais de perda nas peças:** pedido de complementação (16); prazo concedido (7); reiteração (4); diligência externa (2).

### SEI-480002/001314/2024 — caso estudo de caso

nan

```mermaid
flowchart LR
  t0["CASAN<br/>Fiscalizar ETA Rio Bonito e verificar recomendações anterio…<br/>457.9 h · 68 du"]
  class t0 perda
  t1["SCEXEC<br/>Manifestação 55<br/>0.5 h · 55 du"]
  class t1 espera
  t2["CASAN<br/>consolidar análise técnica das fiscalizações programadas 20…<br/>14.8 h · 0 du"]
  class t2 perda
  t3["CASAN<br/>rebater tese da concessionária sobre escopo da fiscalização<br/>2.3 h · 2 du"]
  class t3 perda
  t4["SCEXEC<br/>dar ciência e encaminhar manifestação da regulada<br/>0.1 h · 0 du"]
  t5["SCEXEC<br/>encaminhar autos à Procuradoria para análise jurídica<br/>0.3 h · 2 du"]
  class t5 perda
  t6["PROC<br/>opinar sobre a legitimidade da fiscalização<br/>13.8 h · 203 du"]
  class t6 espera
  t7["SCEXEC<br/>dar ciência do parecer à concessionária<br/>1.1 h · 0 du"]
  t0 --> t1
  t1 --> t2
  t2 --> t3
  t3 --> t4
  t4 --> t5
  t5 --> t6
  t6 --> t7
  classDef espera fill:#f8d7da,stroke:#b02a37
  classDef perda fill:#fff3cd,stroke:#b58105
```
