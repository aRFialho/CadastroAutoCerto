from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set

from .athos_models import AthosAction, AthosReportLine, RuleName, ORDERED_RULES
from .athos_rule_modules.base import RuleContext, to_row
from .athos_rule_modules import (
    fora_de_linha,
    estoque_compartilhado,
    envio_imediato,
    sem_grupo,
    outlet,
)


@dataclass
class AthosOutputs:
    actions_by_rule: Dict[RuleName, List[AthosAction]]
    report_lines: List[AthosReportLine]


def process_rows(
    sql_rows: List[Dict[str, Any]],
    whitelist_imediatos: Set[str],
    supplier_prazo_lookup: Optional[Callable[[str], Optional[int]]] = None,
) -> AthosOutputs:
    rows = [to_row(r) for r in sql_rows]
    ctx = RuleContext(
        rows=rows,
        whitelist_imediatos=whitelist_imediatos,
        supplier_prazo_lookup=supplier_prazo_lookup,
    )

    fora_de_linha.apply(ctx)
    estoque_compartilhado.apply(ctx)
    envio_imediato.apply(ctx)
    sem_grupo.apply(ctx)
    outlet.apply(ctx)

    final_actions_by_rule: Dict[RuleName, List[AthosAction]] = {}
    for rn in ORDERED_RULES:
        final_actions_by_rule[rn] = list(ctx.actions_by_rule[rn].values())

    return AthosOutputs(
        actions_by_rule=final_actions_by_rule,
        report_lines=ctx.report_lines,
    )
