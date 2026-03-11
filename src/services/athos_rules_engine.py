from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

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
    selected_rules: Optional[Iterable[RuleName | str]] = None,
) -> AthosOutputs:
    rows = [to_row(r) for r in sql_rows]
    ctx = RuleContext(
        rows=rows,
        whitelist_imediatos=whitelist_imediatos,
        supplier_prazo_lookup=supplier_prazo_lookup,
    )

    allowed_rules: Set[RuleName] = set(ORDERED_RULES)
    if selected_rules is not None:
        allowed_rules = set()
        for raw in selected_rules:
            if isinstance(raw, RuleName):
                allowed_rules.add(raw)
                continue
            txt = str(raw or '').strip()
            if not txt:
                continue
            normalized = txt.upper().replace('_', ' ')
            mapped = None
            for rn in ORDERED_RULES:
                if normalized in {rn.name.upper().replace('_', ' '), str(rn.value).upper()}:
                    mapped = rn
                    break
            if mapped is not None:
                allowed_rules.add(mapped)

    pipeline = [
        (RuleName.FORA_DE_LINHA, fora_de_linha.apply),
        (RuleName.ESTOQUE_COMPARTILHADO, estoque_compartilhado.apply),
        (RuleName.ENVIO_IMEDIATO, envio_imediato.apply),
        (RuleName.NENHUM_GRUPO, sem_grupo.apply),
        (RuleName.OUTLET, outlet.apply),
    ]

    for rule_name, fn in pipeline:
        if rule_name in allowed_rules:
            fn(ctx)

    final_actions_by_rule: Dict[RuleName, List[AthosAction]] = {}
    for rn in ORDERED_RULES:
        final_actions_by_rule[rn] = list(ctx.actions_by_rule[rn].values()) if rn in allowed_rules else []

    return AthosOutputs(
        actions_by_rule=final_actions_by_rule,
        report_lines=ctx.report_lines,
    )
