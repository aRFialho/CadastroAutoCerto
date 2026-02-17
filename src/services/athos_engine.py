"""
AthosEngine
Orquestrador do Robô Athos.

Responsável por:
- Receber sql_rows + whitelist_rows (lidos do Excel pelo AthosRunner)
- Normalizar SQL (SqlTriple)
- Preparar whitelist (set de EANs)
- Executar regras na ordem definida
- Retornar outputs por regra + relatório consolidado

OBS:
- Nesta fase: regras ainda são placeholders (não aplicam lógica).
- Próximos arquivos: cada regra será implementada separadamente e plugada aqui.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from ..utils.logger import get_logger
from .athos_rules_base import (
    ActionLine,
    ItemType,
    RuleKey,
    RuleOutput,
    SqlTriple,
    dedupe_actions,
    group_by_pai,
    norm_str,
    norm_upper,
    parse_sql_export,
)

logger = get_logger("athos_engine")


@dataclass
class AthosEngineContext:
    """
    Contexto compartilhado entre regras.
    """
    # dados
    triples: List[SqlTriple]
    groups_by_pai: Dict[str, List[SqlTriple]]
    whitelist_eans: Set[str]

    # configurações (vai crescer conforme a gente avançar)
    # regra especial de marcas (envio imediato -> não atualizar, só reportar)
    blocked_brands_envio_imediato: Set[str]


@dataclass
class AthosEngineResult:
    """
    Resultado do engine (antes de escrever Excel).
    """
    outputs: Dict[RuleKey, RuleOutput]
    consolidated_report: List[ActionLine]


# =========================================================
# Whitelist
# =========================================================

def _extract_possible_ean_fields(row: Dict[str, Any]) -> List[str]:
    """
    Tenta extrair possíveis campos de EAN de uma linha do Excel da whitelist.
    Como a whitelist pode mudar, isso é bem tolerante:
    - procura colunas com nomes comuns
    - se não achar, pega o primeiro valor "parecido" com EAN
    """
    if not row:
        return []

    # nomes comuns (case-insensitive)
    key_candidates = [
        "EAN", "CODBARRA", "COD_BARRA", "CODIGO_BARRA", "CODBARRA_PRODUTO",
        "CODIGO", "COD", "SKU",
    ]

    # map normalizado
    keys = list(row.keys())
    norm_map = {norm_upper(k): k for k in keys}

    out: List[str] = []

    # 1) tenta por nome de coluna
    for c in key_candidates:
        cu = norm_upper(c)
        if cu in norm_map:
            v = row.get(norm_map[cu])
            s = norm_str(v)
            if s:
                out.append(s)

    # 2) fallback: pega qualquer célula numérica/string que pareça EAN (>= 8 chars)
    if not out:
        for v in row.values():
            s = norm_str(v)
            if not s:
                continue
            s_digits = "".join(ch for ch in s if ch.isdigit())
            if len(s_digits) >= 8:
                out.append(s_digits)

    return out


def parse_whitelist_rows(whitelist_rows: List[Dict[str, Any]]) -> Set[str]:
    """
    Retorna set de EANs da whitelist.
    """
    eans: Set[str] = set()
    for r in whitelist_rows:
        for e in _extract_possible_ean_fields(r):
            e = norm_str(e)
            if not e:
                continue
            # normaliza: só dígitos (EAN geralmente numérico)
            e_digits = "".join(ch for ch in e if ch.isdigit())
            if e_digits:
                eans.add(e_digits)
            else:
                # se for código alfanumérico (caso raro), mantém raw
                eans.add(e)
    return eans


# =========================================================
# Regras (placeholders por enquanto)
# =========================================================

class BaseRule:
    key: RuleKey

    def apply(self, ctx: AthosEngineContext, out: RuleOutput) -> None:
        raise NotImplementedError


class RuleForaDeLinha(BaseRule):
    key = RuleKey.FORA_DE_LINHA

    def apply(self, ctx: AthosEngineContext, out: RuleOutput) -> None:
        # placeholder: sem alterações ainda
        return


class RuleEstoqueCompartilhado(BaseRule):
    key = RuleKey.ESTOQUE_COMPARTILHADO

    def apply(self, ctx: AthosEngineContext, out: RuleOutput) -> None:
        # placeholder
        return


class RuleEnvioImediato(BaseRule):
    key = RuleKey.ENVIO_IMEDIATO

    def apply(self, ctx: AthosEngineContext, out: RuleOutput) -> None:
        # placeholder
        return


class RuleSemGrupo(BaseRule):
    key = RuleKey.SEM_GRUPO

    def apply(self, ctx: AthosEngineContext, out: RuleOutput) -> None:
        # placeholder
        return


class RuleOutlet(BaseRule):
    key = RuleKey.OUTLET

    def apply(self, ctx: AthosEngineContext, out: RuleOutput) -> None:
        # placeholder
        return


RULES_REGISTRY: List[BaseRule] = [
    RuleForaDeLinha(),
    RuleEstoqueCompartilhado(),
    RuleEnvioImediato(),
    RuleSemGrupo(),
    RuleOutlet(),
]


# =========================================================
# Engine
# =========================================================

class AthosEngine:
    """
    Engine principal: executa regras na ordem e devolve outputs.
    """

    RULE_ORDER: List[RuleKey] = [
        RuleKey.FORA_DE_LINHA,
        RuleKey.ESTOQUE_COMPARTILHADO,
        RuleKey.ENVIO_IMEDIATO,
        RuleKey.SEM_GRUPO,
        RuleKey.OUTLET,
    ]

    def __init__(self) -> None:
        pass

    def build_context(
        self,
        sql_rows: List[Dict[str, Any]],
        whitelist_rows: List[Dict[str, Any]],
    ) -> AthosEngineContext:
        triples = parse_sql_export(sql_rows)
        groups = group_by_pai(triples)
        whitelist = parse_whitelist_rows(whitelist_rows)

        # marcas bloqueadas (envio imediato -> não atualizar, só reportar)
        blocked = {
            "MOVEIS VILA RICA",
            "COLIBRI MOVEIS",
            "MADETEC",
            "CAEMMUN",
            "LINEA BRASIL",
        }

        ctx = AthosEngineContext(
            triples=triples,
            groups_by_pai=groups,
            whitelist_eans=whitelist,
            blocked_brands_envio_imediato=blocked,
        )

        logger.info(f"[AthosEngine] Triples: {len(triples)}")
        logger.info(f"[AthosEngine] Groups by PAI: {len(groups)}")
        logger.info(f"[AthosEngine] Whitelist EANs: {len(whitelist)}")
        return ctx

    def run(
        self,
        sql_rows: List[Dict[str, Any]],
        whitelist_rows: List[Dict[str, Any]],
    ) -> AthosEngineResult:
        ctx = self.build_context(sql_rows, whitelist_rows)

        # cria outputs por regra
        outputs: Dict[RuleKey, RuleOutput] = {k: RuleOutput() for k in self.RULE_ORDER}

        # roda regras na ordem
        for rule_key in self.RULE_ORDER:
            rule = self._get_rule(rule_key)
            if not rule:
                logger.warning(f"[AthosEngine] Regra não registrada: {rule_key}")
                continue
            logger.info(f"[AthosEngine] Aplicando regra: {rule_key.value}")
            rule.apply(ctx, outputs[rule_key])

        # consolida relatório
        consolidated: List[ActionLine] = []
        for rk in self.RULE_ORDER:
            consolidated.extend(outputs[rk].report)

        consolidated = dedupe_actions(consolidated)

        return AthosEngineResult(outputs=outputs, consolidated_report=consolidated)

    def _get_rule(self, key: RuleKey) -> Optional[BaseRule]:
        for r in RULES_REGISTRY:
            if r.key == key:
                return r
        return None
