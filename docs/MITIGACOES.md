# Mitigações das falhas da auditoria — rastreabilidade

30/10/2026 · auditoria em `docs/AUDITORIA.md` · condição 1 da fase 2: "a ampliação usa o mesmo pipeline com as
travas; nenhuma avaliação sem elas".

Cada falha encontrada na auditoria tem uma regra corrigida no código e uma verificação que impede a volta do
erro. **Automática** = teste ou validador que roda em toda execução de `scripts/pipeline.py` e barra a
sequência. **Amostra** = depende de auditoria por leitura a cada lote. **Residual** = limite que não se remove
com código; fica declarado nos entregáveis.

## Camada A — trilha e tempos

| # | Falha encontrada | Causa | Mitigação | Onde | Verificação | Tipo |
|---|---|---|---|---|---|---|
| A1 | "Fila de relatoria" falsa: permanência da unidade lida como espera | permanência corre em paralelo com outras unidades e passa do marco | linha do tempo: execução (1ª → última peça própria) e espera antes (fim da atividade anterior → início desta), repartida pela posse | `fatos.py` | `test_fatos_consistentes` (espera ≥ 0; soma por unidade = total); validador só aceita "du" que seja valor de fato citado | Automática |
| A2 | Posse ficava com quem já tinha concluído | posse = unidade da última remessa | posse = unidade que abriu por último entre as que têm o processo aberto; ninguém aberto = SEM UNIDADE | `trilhas.montar_posse` | `test_posse_*` (3 sintéticos) + `test_posse_sem_lacuna_nem_sobreposicao` (saída real) + auditoria A | Automática |
| A3 | Terceiros fechava a janela na juntada, não na resposta | data da juntada usada como data da resposta | data real da peça (análise do relator); sem data real → indeterminado | `trilhas.janelas_espera_externa` | `test_resposta_sem_data_real_e_indeterminada` | Automática |
| A4 | Resposta por peticionamento em processo relacionado ignorada | só peças externas contavam | processo relacionado e anexo recebido por unidade de protocolo contam como resposta | idem | `test_peticionamento_em_processo_relacionado_responde`, `test_anexo_da_propria_unidade_nao_e_resposta` | Automática |
| A5 | Ofício que não pedia nada abria janela; ofício de outro órgão também | todo ofício abria janela | só ofício da agência com prazo a terceiro (ficha); prazo limita a janela (+5 du), excesso indeterminado; ofício sem ficha → indeterminado | idem + `prazos_dos_oficios` | `test_oficio_sem_prazo_nao_abre_janela`, `test_oficio_de_outro_orgao_nao_abre_janela`, `test_oficio_sem_ficha_e_indeterminado`, `test_excesso_alem_do_prazo_mais_5_e_indeterminado` | Automática |
| A6 | Pedido de prorrogação do terceiro contado como resposta (condição 3 da fase 2) | qualquer peça externa fechava a janela | peça cujo pedido é prorrogação/dilação não fecha a janela; prazo de natureza "prorrogação" não define a janela | `trilhas.datas_reais`, `RE_PRORROGACAO`, `prazos_dos_oficios`, `fichas_trabalho.legado` | `test_pedido_de_prorrogacao_nao_fecha_a_janela`, `test_regex_de_prorrogacao`, `test_legado_..._prorrogacao` | Automática |
| A7 | Totais de terceiros sem lastro conferível | só o total por processo era gravado | uma linha por ofício (resposta, prazo, situação, du) em `saida/janelas_terceiros.csv` | `trilhas.main` | `test_janelas_de_terceiros_cobrem_os_totais` | Automática |
| A8 | "Atraso de juntada" media cópia, não atraso | data escrita em anexo é a do conteúdo | métrica retirada dos fatos e do site | `fatos.py`, `gerar_site.py` | `test_metrica_de_juntada_saiu_das_conclusoes`, `test_site_..._campos_antigos` | Automática |
| A9 | Data escrita na peça podia ser lida mês-dia (05-03-2024 → 3 de maio) | `pd.to_datetime` sem formato | leitura explícita: ISO ou dia primeiro; fora de 2000–2035 é descartada | `trilhas.data_da_peca` | `test_data_da_peca_le_dia_primeiro` (hoje 0 datas ambíguas no acervo; preventivo para a fase 2) | Automática |
| A10 | Data real só existe para parte das peças externas (~56%) | a análise do relator nem sempre lê a data | sem data real o tempo vai para "indeterminado", nunca para terceiros | — | exibido separado nos fatos e no site | Residual |

## Camada B — fichas de trabalho por peça

| # | Falha encontrada | Mitigação | Onde | Verificação | Tipo |
|---|---|---|---|---|---|
| B1 | Item sem lastro no texto (0,9% na v1) | ficha-v2: todo item com trecho literal; código confere o trecho no texto; só item ancorado alimenta as etapas seguintes | `fichas_trabalho.ancorar`, `legado` | `test_ancoragem_...`, `test_legado_...`, `test_fichas_sao_v2_e_legado_so_ancorado`; auditoria B (números sem âncora ≤ 1%) | Automática |
| B2 | Trabalho reproduzido (citação, transcrição) contado como próprio | separação próprio × reproduzido e composição do texto na ficha-v2 | `SISTEMA` (prompt) | auditoria por amostra | Amostra |
| B3 | Ferramenta "usada" que era fórmula de expediente | ferramenta só com evidência que não seja expediente, nome não genérico | `fichas_atividades.EXPEDIENTE`, `GENERICAS` | `test_expediente_nao_vira_ferramenta` | Automática |
| B4 | Refazimento/reiteração invisível na leitura peça a peça | peça própria que repete ≥ 60% de outra anterior da mesma categoria vira sinal de perda | `fichas_atividades.repeticoes_por_caso` | `test_repeticao_de_peca_da_mesma_categoria` | Automática |
| B5 | Dados pessoais de terceiros nas evidências | limpeza de nome de usuário, endereço, CPF, e-mail e telefone nas fichas **e em tudo o que vai ao site** | `fichas_atividades.limpar_pessoais`, `gerar_site.main` | `test_limpeza_de_dados_pessoais`, `test_site_sem_dados_pessoais_nem_campos_antigos` | Automática |
| B6 | Imprecisão residual (~11%) em classificação de prazos e fontes citadas | não sustentam conclusão do site; reavaliada a cada lote | — | auditoria por amostra (30 fichas/lote) | Amostra |

## Camadas C, D, E — classificação, modelos, descritivos

| # | Falha encontrada | Mitigação | Onde | Verificação | Tipo |
|---|---|---|---|---|---|
| C1 | Fronteira P06 × P07 × P21 × P35 | reclassificação às cegas por lote; confiança baixa fora da coorte | `selecionar_piloto.py` | amostra (kappa ≥ 0,8) | Amostra |
| D1 | Frequência, dias, horas, notas e situação escritos pelos agentes nos modelos | modelo do agente fica só com nomes, fluxo e decisões; números calculados da linha do tempo e das fichas | `gerar_bpmn.metricas_das_fichas` | `test_modelo_sem_numeros_dos_agentes`; auditoria D (frequência diverge = 0) | Automática |
| D2 | Horas e tempos de outra unidade atribuídos à atividade | só peças da unidade da raia medem a atividade; as demais ficam como trâmite associado | `fichas_atividades.main` | `test_tramite_de_outra_unidade_fica_fora_do_tempo_e_das_horas` | Automática |
| D3 | Setas sobre elementos no BPMN | roteamento por trilhos e corredor de laços | `gerar_bpmn.py` | `test_bpmn_sem_seta_atravessando_elemento` | Automática |
| E1 | Tempos medidos escritos nos descritivos dos vínculos | frases com "du" saem das observações; descritivo só pode citar prazo que está na peça (ficha) | `fichas_atividades.main`, `validar_avaliacao.validar` | `test_validador_barra_tempo_medido_no_descritivo` | Automática |

## Camada F — avaliações AS-IS

| # | Falha encontrada | Mitigação | Onde | Verificação | Tipo |
|---|---|---|---|---|---|
| F1 | Número sem lastro ou recalculado pelo agente | tabela de fatos por código como única fonte; cada bloco cita os fatos; "du" tem que ser valor de fato citado; demais números, de fato ou da ficha | `fatos.py`, `validar_avaliacao.py` | `test_validador_aceita_...`, `test_validador_barra[...]` (6 casos) | Automática |
| F2 | Data citada sem lastro | data completa tem que existir nos fatos, na juntada, no texto das peças ou na análise do relator (inclui apensos e datas por extenso) | `validar_avaliacao.datas_conhecidas` | `test_validador_barra[data]` | Automática |
| F3 | Mediana da carteira sem dizer se é dos nativos ou de todos (migrados distorcem) | os dois fatos existem; a frase tem que dizer qual | idem | `test_validador_barra[mediana]`, `test_fatos_consistentes` | Automática |
| F4 | Avaliação com números de uma versão anterior dos fatos (regeneração concorrente; regra de tempo alterada sem rever conclusões) | carimbo: impressão digital dos valores dos fatos gravada na avaliação validada; o site só é gerado com carimbo atual; trava de execução única | `validar_avaliacao.carimbar`, `pipeline.py` | `test_carimbo_invalida_quando_fato_muda`; portão `validar_avaliacoes --exigir-carimbo` | Automática |
| F5 | Sentido errado / imprecisão na leitura dos fatos (0,5% e 6,5% na rodada 3) | não se detecta por código | verificação independente dos blocos de conclusão a cada lote | Amostra |

## Limites que permanecem (declarados nos entregáveis)

- Peças restritas não têm texto; afirmações sobre elas se apoiam no tipo e em peças que as relatam. A cobertura
  por processo (peças substantivas com texto **não vazio**) sai em `dados/relator/cobertura_texto.csv`; processo
  abaixo de 60% fica fora da coorte.
- Quem assina não é necessariamente quem preparou a peça.
- Tempo de trabalho é faixa (piso–teto) até o estudo de tempo com as unidades.

## Como a fase 2 usa isso

Por lote de processos:
1. `python exportar_relator.py --texto-piloto --processos <coorte.csv>` → texto e `cobertura_texto.csv`
   (processo com cobertura < 60% sai do lote).
2. `python pipeline.py --fichas` → fichas v2 → trilha → fatos → modelos → portões. Para no primeiro portão que
   falhar.
3. Avaliação por agente **depois** dos fatos; `validar_avaliacao.py` até 0 problema; `--carimbar`.
4. `python pipeline.py --de validar_avaliacoes` → portões finais e site.
5. Auditoria por amostra (30 fichas e os blocos de conclusão), com os critérios de `docs/AUDITORIA.md`; lote só
   entra no consolidado se passar.

Ao mudar qualquer regra de tempo: rodar o pipeline; o portão das avaliações falha pelo carimbo e aponta
exatamente o que precisa ser revisto.

## Controles acrescentados na fase 2

| Risco | Controle | Teste |
|---|---|---|
| Classificação de tipo novo errada (65,5% de concordância na reclassificação às cegas) | Só entra na coorte o processo em que classificador e auditor concordam | `coorte_fase2.py` + `verificacao_classificacao.csv` |
| Mesmo caso contado duas vezes (processo físico migrado que reaparece com número novo) | Processo só do relator com ≥ 90% dos textos iguais a outro sai | `test_coorte_tira_copia_de_processo_migrado`, `test_coorte_sem_processo_duplicado` |
| Fichas de dois modelos (crédito do primeiro acabou) | Cada ficha guarda o modelo; comparação no mesmo documento (`comparar_modelos_fichas.py`); procedimento conta fichas por modelo | `fichas_por_modelo` em `procedimento_<cod>.json` |
| Classificador de atividade otimista no piloto | Auditoria às cegas fora do piloto, por código; código abaixo de 85% vira "indicativo" | `test_auditoria_do_classificador_atinge_criterio`, `test_situacao_do_codigo_pela_auditoria` |
| Rótulo fora das candidatas ou peça fora da raia | Esquema com enum; rótulo fora da raia vira `fora_do_modelo` | `test_atribuicao_so_com_rotulo_valido_e_na_raia` |
| Expediente inflando a não conformidade | Conformidade medida só nas peças substantivas; expediente à parte | `fora_do_modelo_pct_substantivas` |
| % do ramo de decisão inventado ou desalinhado do procedimento | % calculado só de transições observadas; ramos que levam à mesma atividade ficam sem %; mínimo de 3 transições | `test_probabilidade_dos_ramos_pela_transicao_observada`, `test_bpmn_da_coorte_mostra_percentuais_que_batem_com_o_procedimento` |
| Rótulo com % ilegível no diagrama | Largura do rótulo acompanha o texto; posição livre ao redor; medida em `checar_bpmn.py` | `test_bpmn_rotulo_de_fluxo_nao_cobre_forma_nem_rotulo` |
| Site expõe o modelo de linguagem de cada ficha | `fichas_por_modelo` sai dos dados do site | `gerar_site.py` |
| Distribuição incoerente | q1 ≤ mediana ≤ q3 ≤ máx; casos + ausentes = total; % das transições bate com as contagens | `test_procedimento_consistente` |
| Classificador guiado pelo caso-piloto (gatilho e saída dos vínculos descreviam só o piloto: P08 "restituir sem parecer") | Gatilho e saída genéricos do modelo valem primeiro; vínculos só suprem o modelo sem esses campos | `classificar_atividades.montar` + reauditoria às cegas do P08 |
| Número da avaliação de tipo sem piloto sem lastro | Fatos `coorte.*` copiados do procedimento; validador aceita só esses e as contagens do procedimento | `test_fatos_da_coorte_batem_com_o_procedimento`, `test_validador_sem_caso_piloto_usa_numeros_da_coorte` |
| Avaliação incompleta depois de mudar o modelo | Validador exige uma entrada por tarefa do modelo e nenhuma a mais | `test_validador_exige_entrada_para_cada_tarefa_do_modelo` |
| Recarimbo das avaliações do piloto sem revisão | Os fatos da coorte só se somam: antes de recarimbar, conferido que nenhum fato antigo mudou de valor (0 diferenças em 8 códigos) | `test_avaliacao_ancorada_e_carimbada` |
| Ordem de itens empatados mudava a cada rodada (conjuntos) | Empate desfeito pelo nome nas listas de frequência do procedimento | duas rodadas com o mesmo hash |

## Controles da fase 3 (conformidade, benchmarking, TO-BE)

| Falha possível | Mitigação | Teste ou portão |
|---|---|---|
| Trecho de norma escrito de memória | Todo trecho é conferido literalmente contra o texto integral da base do Especialista | `verificar_normas.py` (portão no pipeline) |
| Requisito que testa atividade inexistente ou norma não levantada | Ids de atividade e de norma conferidos contra o modelo e o inventário | `test_requisitos_testam_atividades_do_modelo` |
| Teste de prazo mal especificado (ordem, notificação repetida, prazo não lido) | Motor com regras explícitas; prazo não lido é "sem evidência", não violação | `test_conformidade_*` (sintéticos) |
| Prazo máximo contado de peça posterior ao ato (intervalo negativo virava conformidade) ou da 1ª rodada quando o prazo reabre a cada rodada | Só conta `de` anterior ao ato; `de_ocorrencia: ultima` nos prazos que reabrem (deliberação após razões finais, parecer jurídico após o técnico) | `test_conformidade_prazo_max_nao_conta_origem_posterior_ao_ato_e_aceita_ultima_rodada` |
| Meta legal de 100% que o TO-BE não alcança | Conformidade simulada por fase (linha do tempo refeita, mesmos testes; fase 0 reproduz a medida); meta de requisito de prazo só da simulação, exigência legal à parte | `test_tobe_conformidade_simulada_reproduz_a_medida_na_fase_zero`, `validar_controles.py` |
| Citação de benchmarking inexistente ou exagerada | Conferência independente de DOI, metadados, trecho literal e resultado; 13 correções aplicadas, 0 exclusões | `test_benchmark_verificado_sem_caso_excluido` |
| TO-BE tratando prazo de defesa como desperdício | Todo prazo concedido vira requisito `prazo_min`; o validador recusa teto ou redução abaixo dele | `validar_tobe.py` |
| TO-BE cortando tempo de resposta de terceiro (concessionária, Poder Concedente) | Janelas de terceiros recortadas por ocorrência (`espera_antes_terceiros_du`); teto e redução de espera só alcançam a parte da agência | `test_tobe_teto_e_reducao_nao_cortam_resposta_de_terceiro` |
| Ganho na cauda de processo ainda aberto (tempo até a data de corte) | Redução da cauda só em caso encerrado | `test_tobe_cauda_so_reduz_em_caso_encerrado` |
| Melhoria sem lastro, cenários fora de ordem ou fase sem ganho cumulativo | Validador (fato, requisito, benchmark ou hipótese, monotonia); resultado conferido contra o carimbo da linha de base | `validar_tobe.py` (portão), `test_resultado_tobe_atual_e_coerente` |
| Meta sem lastro ou linha de base digitada à mão | Linha de base igual ao valor do fato citado; meta só com origem conferível (caminho da simulação com o mesmo valor, requisito legal ou caso de benchmark) | `validar_controles.py` (portão) |
| Saída de IA sem revisão ou sem medida de qualidade | Toda melhoria de fase 3 exige `controle_humano` e um controle de qualidade (verificação, amostragem, critério de aceite) | `validar_tobe.py`, `validar_controles.py` |
| Ganho concentrado em poucas melhorias sem que se saiba | Sensibilidade no resultado: efeito de retirar cada melhoria na última fase | `resultado_tobe_<cod>.json` → `sensibilidade` |
| Ganho calculado contra outra base | Linha de base congelada com carimbo; a simulação reproduz o lead time de cada caso (fase 0 = AS-IS) | `test_linha_base_bate_com_os_casos_da_coorte`, `test_tobe_fase_zero_reproduz_o_lead_da_linha_do_tempo` |

## Efeito da regra de prorrogação (A6) nos números publicados

| Processo | Caso | Terceiros antes → depois | Indeterminado antes → depois |
|---|---|---|---|
| P03 | típico | 96 → 89 du | 42 → 42 du |
| P21 | típico | 75 → 71 du | 68 → 68 du |
| P22 | típico | 28 → 23 du | 0 → 0 du |
| P35 | crítico | 136 → 114 du | 103 → 105 du |

Avaliações atualizadas, revalidadas e carimbadas; nenhuma conclusão de gargalo mudou (a espera de terceiros
diminuiu, reforçando que a maior parte do tempo é interna).

## Estudo de caso de um processo (branch caso-igua-fiscalizacao)

| Falha encontrada | Mitigação | Teste ou portão |
|---|---|---|
| `fichas_trabalho.py` chamava `limpar_pessoais` sem importar: a rodada inteira caía no fim, depois de gastar as chamadas | Import de `fichas_atividades.limpar_pessoais` | `test_fichas_trabalho_tem_limpeza_de_dados_pessoais_importada` |
| Sem chave de API, as fichas não tinham como ser geradas | `--exportar` grava o prompt exato de cada peça; `--importar` lê a resposta de um agente e aplica a mesma ancoragem literal e o mesmo `legado` | `test_fichas_importadas_de_agente_passam_pela_mesma_ancoragem`; auditoria às cegas em `saida/auditoria/auditoria_fichas.json` |
| Processo indicado pelo aluno fora da elegibilidade do piloto (não encerrado) | `selecionar_piloto.py --caso NUMERO` inclui o processo com papel "estudo de caso" e registra o critério que falhou no `motivo` | `saida/piloto.csv` |
| Coorte da fase 2 com um caso só (abaixo de `MIN_CASOS`) e sem LLM para rotular atividades | `coorte_fase2.py --min-casos 1`; `classificar_atividades.py --gabarito` grava as atribuições a partir dos vínculos auditados, só quando toda a coorte é do piloto; `procedimento.py` marca o código como `estudo_de_caso` | `saida/fase2/procedimento_P06.json` → `situacao` |
| Saídas por código do caso de referência misturadas às do caso novo (fatos e linha de base liam a coorte de referência) | No branch do estudo de caso, as saídas por código da referência foram retiradas; o `main` as mantém | `linha_base_P06.json` → `casos_nativos` = 1 |
