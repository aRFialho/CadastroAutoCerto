from __future__ import annotations
from .base import RuleContext, grupo3_bucket, RuleName, ItemTipo, AthosAction, is_imediata, apply_imediata, apply_prazo, safe_group3, parse_int_safe


def apply(ctx: RuleContext) -> None:
    for pai_key, group_rows in ctx.by_pai.items():
        esc_rows = [r for r in group_rows if grupo3_bucket(r.nome_grupo3) == RuleName.ESTOQUE_COMPARTILHADO.value]
        if not esc_rows:
            continue

        kit_prazos = []
        for r in esc_rows:
            if not r.codbarra_kit or ctx.is_locked(r.codbarra_kit):
                continue

            if is_imediata(r.prazo_produto):
                a = AthosAction(rule=RuleName.ESTOQUE_COMPARTILHADO, tipo=ItemTipo.KIT, codbarra=r.codbarra_kit)
                apply_imediata(a)
                a.marca = r.fabricante_kit or ""
                a.grupo3_origem_pa = safe_group3(r.nome_grupo3)
                a.add_msg("PRAZO HERDADO DO PA (Imediata)")
                ctx.upsert_action(a)
                ctx.lock(a.codbarra, RuleName.ESTOQUE_COMPARTILHADO)
                ctx.report(RuleName.ESTOQUE_COMPARTILHADO, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", "PRAZO HERDADO DO PA (Imediata)")
                continue

            p = parse_int_safe(r.prazo_produto)
            if p is None:
                continue

            kit_prazos.append(p)
            a = AthosAction(rule=RuleName.ESTOQUE_COMPARTILHADO, tipo=ItemTipo.KIT, codbarra=r.codbarra_kit)
            apply_prazo(a, p)
            a.marca = r.fabricante_kit or ""
            a.grupo3_origem_pa = safe_group3(r.nome_grupo3)
            a.add_msg(f"PRAZO HERDADO DO PA: {p} DIAS")
            ctx.upsert_action(a)
            ctx.lock(a.codbarra, RuleName.ESTOQUE_COMPARTILHADO)
            ctx.report(RuleName.ESTOQUE_COMPARTILHADO, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", f"PRAZO HERDADO DO PA: {p} DIAS")

        if pai_key != "__SEM_PAI__" and kit_prazos and not ctx.is_locked(pai_key):
            maior = max(kit_prazos)
            a = AthosAction(rule=RuleName.ESTOQUE_COMPARTILHADO, tipo=ItemTipo.PAI, codbarra=pai_key)
            apply_prazo(a, maior)
            any_row = next((rr for rr in esc_rows if rr.fabricante_pai), None)
            a.marca = any_row.fabricante_pai if any_row else ""
            a.grupo3_origem_pa = RuleName.ESTOQUE_COMPARTILHADO.value
            a.add_msg(f"MAIOR PRAZO DOS KITS: {maior} DIAS")
            ctx.upsert_action(a)
            ctx.lock(a.codbarra, RuleName.ESTOQUE_COMPARTILHADO)
            ctx.report(RuleName.ESTOQUE_COMPARTILHADO, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", f"MAIOR PRAZO DOS KITS: {maior} DIAS")
