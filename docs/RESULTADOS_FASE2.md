# Resultados da Fase 2 — do caso ao procedimento

Gerado por `scripts/resumo_fase2.py` a partir das saídas do pipeline. Tempos em dias úteis (du); horas são hipótese até a calibração com servidores.

## Coorte

1 processos em 1 códigos (1 com trilha nativa do SEI, 0 migrados com trilha parcial, 0 só com as peças, sem trâmite). 0 processos repetidos (cópia de processo físico migrado com número novo) foram retirados.

| Código | Processo | Situação | Casos (nativa/migrada/sem) | Lead time dos nativos encerrados | Concordância na auditoria (peças substantivas) |
|---|---|---|---|---|---|
| P06 | Fiscalização técnica de campo (programada e por demanda) | estudo de caso | 1 (1/0/0) | — | — (0 peças) |

Situação: *procedimento* = 5 casos ou mais e concordância ≥ 85% na auditoria às cegas; *indicativo* = abaixo do critério, números com ressalva; *estudo de caso* = menos de 5 casos.

## Controles de qualidade

- Fichas de trabalho: 60 peças; agente:claude-haiku-5-5 60. As que faltavam quando o crédito do primeiro modelo acabou foram feitas com o segundo.

## Procedimento por código

### P06 — Fiscalização técnica de campo (programada e por demanda) (estudo de caso)

1 casos; 1 caminhos distintos (ordem da 1ª ocorrência de cada atividade). Peças substantivas fora do modelo por caso: mediana 2,2%.

Nenhum caminho se repete entre os casos. Núcleo comum (atividades em metade dos casos ou mais, na ordem do modelo): t1 → t2 → t3 → t4 → t5 → t6 → t7 → t8

| Atividade | Casos | Com laço | Execução | Espera antes | Horas (piso) |
|---|---|---|---|---|---|
| t1 Convocar concessionária para vistoria conjunta | 100% | 1 | 8 du (q1 4–q3 12; n 2) | 8,5 du (q1 6,8–q3 10,2; n 2) | 1,6 h (q1 1,2–q3 2,1; n 2) |
| t2 Vistoriar unidade e elaborar relatório | 100% | 1 | 4,5 du (q1 0,8–q3 8,5; n 8) | 10,5 du (q1 2–q3 21,8; n 8) | 24,5 h (q1 20–q3 27,8; n 8) |
| t3 Encaminhar relatórios à concessionária com prazo | 100% | 1 | 0 du (q1 0–q3 0; n 7) | 6 du (q1 3–q3 8,5; n 7) | 0,8 h (q1 0,8–q3 0,8; n 7) |
| t4 Consolidar análise técnica das fiscalizações | 100% | 0 | 0 du (q1 0–q3 0; n 1) | 106 du (q1 106–q3 106; n 1) | 12,2 h (q1 12,2–q3 12,2; n 1) |
| t5 Dar ciência do parecer à concessionária | 100% | 0 | 24 du (q1 24–q3 24; n 1) | 55 du (q1 55–q3 55; n 1) | 0,8 h (q1 0,8–q3 0,8; n 1) |
| t6 Rebater manifestação da concessionária | 100% | 0 | 0 du (q1 0–q3 0; n 1) | 2 du (q1 2–q3 2; n 1) | 8 h (q1 8–q3 8; n 1) |
| t7 Emitir parecer jurídico sobre a fiscalização | 100% | 0 | 0 du (q1 0–q3 0; n 1) | 205 du (q1 205–q3 205; n 1) | 10 h (q1 10–q3 10; n 1) |
| t8 Oficiar concessionária e sobrestar processo | 100% | 0 | 0 du (q1 0–q3 0; n 1) | 0 du (q1 0–q3 0; n 1) | 0,8 h (q1 0,8–q3 0,8; n 1) |

