from __future__ import annotations
from .base import RuleContext, grupo3_bucket, RuleName


def apply(ctx: RuleContext) -> None:
    for r in ctx.rows:
        g3 = grupo3_bucket(r.nome_grupo3)
        if g3 != RuleName.FORA_DE_LINHA.value:
            continue
        if not r.codbarra_produto:
            continue
        if ctx.estoque_pa(r) <= 0:
            ctx.emit_for_pa_kit_pai(
                RuleName.FORA_DE_LINHA,
                r,
                produto_inativo="T",
                msg_pa="PRODUTO INATIVADO",
                msg_kit="PRODUTO INATIVADO",
                msg_pai="PRODUTO INATIVADO",
            )
