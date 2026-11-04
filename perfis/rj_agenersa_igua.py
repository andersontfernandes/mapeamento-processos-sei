"""Perfil do estudo de caso do aluno: um processo de fiscalização da AGENERSA (SEI-480002/001314/2024, Iguá).

Mesmo órgão do caso de referência: herda tudo de rj_agenersa.py e só restringe o escopo ao código P06.
Uso: export PERFIL=rj_agenersa_igua"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("perfil_rj_agenersa_base", Path(__file__).with_name("rj_agenersa.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
globals().update({k: v for k, v in vars(_base).items() if not k.startswith("_")})

# origem da base: um único processo indicado por um colega, lido da Pesquisa Pública do SEI-RJ em 04/11/2026
DESCRICAO_BASE = "processo SEI-480002/001314/2024 (Pesquisa Pública do SEI-RJ)"

# um caso só: sem coorte da fase 2, TO-BE e controles apenas da fiscalização
CODIGOS_NOVOS_FASE2 = set()
ORDEM_CODIGOS = ["P06"]
CODIGOS_FASE3 = ["P06"]
FAMILIA_BENCHMARK = {"P06": "fiscalizacao"}
VOLUME_REGRAS = {"P06": _base.VOLUME_REGRAS["P06"]}
