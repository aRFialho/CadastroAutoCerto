from __future__ import annotations
from typing import Dict, Optional
from .base import (
    RuleContext, RuleName, ItemTipo, AthosAction,
    SPECIAL_IMEDIATO_BRANDS, DMOV_BRANDS, IMEDIATA_TEXT,
    grupo3_bucket, norm_upper, safe_group3,
)

IMEDIATO_IGNORED_BRANDS = {"JOMARCA", "BOBINONDA", "DMOV - MP"}
IMEDIATA_BRANDS = {"KONFORT", "CASA DO PUFF", "DIVINI DECOR", "LUMIL", "MADERATTO"}


def _is_imediato_ignored_row(r) -> bool:
    return (
        norm_upper(r.fabricante_produto) in IMEDIATO_IGNORED_BRANDS
        or norm_upper(r.fabricante_kit) in IMEDIATO_IGNORED_BRANDS
        or norm_upper(r.fabricante_pai) in IMEDIATO_IGNORED_BRANDS
    )


def apply(ctx: RuleContext) -> None:
    for r in ctx.rows:
        if grupo3_bucket(r.nome_grupo3) != RuleName.ENVIO_IMEDIATO.value:
            continue
        if _is_imediato_ignored_row(r):
            continue
        if not r.codbarra_produto or ctx.is_locked(r.codbarra_produto):
            continue
        if r.codbarra_produto not in ctx.whitelist_imediatos:
            a = AthosAction(rule=RuleName.ENVIO_IMEDIATO, tipo=ItemTipo.PA, codbarra=r.codbarra_produto)
            a.grupo3 = "APAGAR"
            a.marca = r.fabricante_produto or ""
            a.grupo3_origem_pa = safe_group3(r.nome_grupo3)
            a.add_msg("RETIRADO DO GRUPO3 ENVIO IMEDIATO")
            ctx.upsert_action(a)
            ctx.lock(a.codbarra, RuleName.ENVIO_IMEDIATO)
            ctx.report(RuleName.ENVIO_IMEDIATO, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", "RETIRADO DO GRUPO3 ENVIO IMEDIATO")

    for pai_key, group_rows in ctx.by_pai.items():
        grp = [
            r for r in group_rows
            if grupo3_bucket(r.nome_grupo3) == RuleName.ENVIO_IMEDIATO.value
            and r.codbarra_produto
            and not _is_imediato_ignored_row(r)
        ]
        if not grp:
            continue
        special_pas = [r for r in grp if norm_upper(r.fabricante_produto) in SPECIAL_IMEDIATO_BRANDS]
        if not special_pas:
            continue
        all_le_zero = all(ctx.estoque_decisao(rr) <= 0 for rr in grp)
        if not all_le_zero:
            continue
        for rr in grp:
            if rr.codbarra_produto:
                ctx.blocked_codbar.add(rr.codbarra_produto)
            if rr.codbarra_kit:
                ctx.blocked_codbar.add(rr.codbarra_kit)
            if rr.codbarra_pai:
                ctx.blocked_codbar.add(rr.codbarra_pai)
        for rr in special_pas:
            ctx.report(RuleName.ENVIO_IMEDIATO, rr.codbarra_produto or "", ItemTipo.PA, rr.fabricante_produto or "", safe_group3(rr.nome_grupo3), "Colocar cód Fabricante, mudar para Estoque Compartilhado")

    for pai_key, group_rows in ctx.by_pai.items():
        grp_pa = [
            r for r in group_rows
            if grupo3_bucket(r.nome_grupo3) == RuleName.ENVIO_IMEDIATO.value
            and r.codbarra_produto
            and r.codbarra_produto in ctx.whitelist_imediatos
            and not _is_imediato_ignored_row(r)
        ]
        if not grp_pa:
            continue

        marca_group = norm_upper(grp_pa[0].fabricante_produto)
        pa_row_by_code: Dict[str, any] = {}
        pa_stock_by_code: Dict[str, float] = {}
        for r in grp_pa:
            if r.codbarra_produto:
                pa_row_by_code[r.codbarra_produto] = r
                pa_stock_by_code[r.codbarra_produto] = ctx.estoque_pa(r)

        all_pa_gt_zero = bool(pa_stock_by_code) and all(v > 0 for v in pa_stock_by_code.values())
        all_pa_le_zero = bool(pa_stock_by_code) and all(v <= 0 for v in pa_stock_by_code.values())
        any_pa_gt_zero = bool(pa_stock_by_code) and any(v > 0 for v in pa_stock_by_code.values())

        kits_by_code: Dict[str, any] = {}
        for rr in group_rows:
            if grupo3_bucket(rr.nome_grupo3) != RuleName.ENVIO_IMEDIATO.value:
                continue
            if _is_imediato_ignored_row(rr):
                continue
            if rr.codbarra_kit:
                kits_by_code[rr.codbarra_kit] = rr
        uniq_kits = list(kits_by_code.values())

        def emit_action(rule: RuleName, tipo: ItemTipo, codbarra: str, *, marca: str, grupo3_origem: str, estoque_seg: Optional[int], dias: Optional[int], site: Optional[str], msg: str) -> None:
            if not codbarra or ctx.is_locked(codbarra):
                return
            a = AthosAction(rule=rule, tipo=tipo, codbarra=codbarra)
            a.estoque_seguranca = estoque_seg
            a.dias_entrega = dias
            a.site_disponibilidade = site
            a.marca = marca or ""
            a.grupo3_origem_pa = grupo3_origem or ""
            a.add_msg(msg)
            ctx.upsert_action(a)
            ctx.lock(a.codbarra, rule)
            ctx.report(rule, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", msg)

        def kit_pa_code(k) -> Optional[str]:
            if k.codbarra_produto and k.codbarra_produto in pa_stock_by_code:
                return k.codbarra_produto
            if len(pa_stock_by_code) == 1:
                return next(iter(pa_stock_by_code.keys()))
            return None

        def forn(r, tipo: ItemTipo) -> int:
            return ctx.prazo_fornecedor(r, tipo)

        if marca_group in DMOV_BRANDS:
            for pa_cod, pa_r in pa_row_by_code.items():
                if pa_stock_by_code.get(pa_cod, 0) > 0:
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod, marca=pa_r.fabricante_produto or "", grupo3_origem=safe_group3(pa_r.nome_grupo3), estoque_seg=1000, dias=3, site="3", msg="INCLUIDO 1000 ESTOQUE SEG")
                else:
                    p = forn(pa_r, ItemTipo.PA)
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod, marca=pa_r.fabricante_produto or "", grupo3_origem=safe_group3(pa_r.nome_grupo3), estoque_seg=1000, dias=p, site=str(p), msg="INCLUIDO 1000 ESTOQUE SEG")
            for k in uniq_kits:
                pa_cod = kit_pa_code(k)
                pa_disp = pa_stock_by_code.get(pa_cod, None) if pa_cod else None
                if pa_disp is not None and pa_disp > 0:
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "", marca=k.fabricante_kit or "", grupo3_origem=safe_group3(k.nome_grupo3), estoque_seg=0, dias=3, site="3", msg="PRAZO DEFINIDO 3 DIAS")
                else:
                    p = forn(k, ItemTipo.KIT)
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "", marca=k.fabricante_kit or "", grupo3_origem=safe_group3(k.nome_grupo3), estoque_seg=0, dias=p, site=str(p), msg=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)")
            if pai_key != "__SEM_PAI__":
                if all_pa_gt_zero:
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PAI, pai_key, marca=grp_pa[0].fabricante_pai or "", grupo3_origem=RuleName.ENVIO_IMEDIATO.value, estoque_seg=0, dias=3, site="3", msg="PRAZO DEFINIDO 3 DIAS")
                else:
                    p_pai = max((forn(r, ItemTipo.PAI) for r in grp_pa), default=0)
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PAI, pai_key, marca=grp_pa[0].fabricante_pai or "", grupo3_origem=RuleName.ENVIO_IMEDIATO.value, estoque_seg=0, dias=p_pai, site=str(p_pai), msg=f"PRAZO DEFINIDO {p_pai} DIAS (FORNECEDOR)")
            continue

        if marca_group in IMEDIATA_BRANDS:
            if all_pa_gt_zero:
                for pa_cod, pa_r in pa_row_by_code.items():
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod, marca=pa_r.fabricante_produto or "", grupo3_origem=safe_group3(pa_r.nome_grupo3), estoque_seg=0, dias=0, site=IMEDIATA_TEXT, msg=IMEDIATA_TEXT)
                for k in uniq_kits:
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "", marca=k.fabricante_kit or "", grupo3_origem=safe_group3(k.nome_grupo3), estoque_seg=0, dias=0, site=IMEDIATA_TEXT, msg=IMEDIATA_TEXT)
                if pai_key != "__SEM_PAI__":
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PAI, pai_key, marca=grp_pa[0].fabricante_pai or "", grupo3_origem=RuleName.ENVIO_IMEDIATO.value, estoque_seg=0, dias=0, site=IMEDIATA_TEXT, msg=IMEDIATA_TEXT)
                continue
            if all_pa_le_zero:
                for pa_cod, pa_r in pa_row_by_code.items():
                    p = forn(pa_r, ItemTipo.PA)
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod, marca=pa_r.fabricante_produto or "", grupo3_origem=safe_group3(pa_r.nome_grupo3), estoque_seg=1000, dias=p, site=str(p), msg="INCLUIDO 1000 ESTOQUE SEG")
                for k in uniq_kits:
                    p = forn(k, ItemTipo.KIT)
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "", marca=k.fabricante_kit or "", grupo3_origem=safe_group3(k.nome_grupo3), estoque_seg=0, dias=p, site=str(p), msg=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)")
                if pai_key != "__SEM_PAI__":
                    p_pai = max((forn(r, ItemTipo.PAI) for r in grp_pa), default=0)
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PAI, pai_key, marca=grp_pa[0].fabricante_pai or "", grupo3_origem=RuleName.ENVIO_IMEDIATO.value, estoque_seg=0, dias=p_pai, site=str(p_pai), msg=f"PRAZO DEFINIDO {p_pai} DIAS (FORNECEDOR)")
                continue
            if any_pa_gt_zero:
                if pai_key != "__SEM_PAI__":
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PAI, pai_key, marca=grp_pa[0].fabricante_pai or "", grupo3_origem=RuleName.ENVIO_IMEDIATO.value, estoque_seg=0, dias=0, site=IMEDIATA_TEXT, msg=IMEDIATA_TEXT)
                for pa_cod, pa_r in pa_row_by_code.items():
                    if pa_stock_by_code.get(pa_cod, 0) > 0:
                        emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod, marca=pa_r.fabricante_produto or "", grupo3_origem=safe_group3(pa_r.nome_grupo3), estoque_seg=0, dias=0, site=IMEDIATA_TEXT, msg=IMEDIATA_TEXT)
                    else:
                        p = forn(pa_r, ItemTipo.PA)
                        emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod, marca=pa_r.fabricante_produto or "", grupo3_origem=safe_group3(pa_r.nome_grupo3), estoque_seg=0, dias=p, site=str(p), msg=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)")
                for k in uniq_kits:
                    pa_cod = kit_pa_code(k)
                    pa_disp = pa_stock_by_code.get(pa_cod, None) if pa_cod else None
                    if pa_disp is not None and pa_disp > 0:
                        emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "", marca=k.fabricante_kit or "", grupo3_origem=safe_group3(k.nome_grupo3), estoque_seg=0, dias=0, site=IMEDIATA_TEXT, msg=IMEDIATA_TEXT)
                    else:
                        p = forn(k, ItemTipo.KIT)
                        emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "", marca=k.fabricante_kit or "", grupo3_origem=safe_group3(k.nome_grupo3), estoque_seg=0, dias=p, site=str(p), msg=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)")
                continue

        if all_pa_gt_zero:
            for pa_cod, pa_r in pa_row_by_code.items():
                emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod, marca=pa_r.fabricante_produto or "", grupo3_origem=safe_group3(pa_r.nome_grupo3), estoque_seg=0, dias=1, site="1", msg="PRAZO DEFINIDO 1 DIA")
            for k in uniq_kits:
                emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "", marca=k.fabricante_kit or "", grupo3_origem=safe_group3(k.nome_grupo3), estoque_seg=0, dias=1, site="1", msg="PRAZO DEFINIDO 1 DIA")
            if pai_key != "__SEM_PAI__":
                emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PAI, pai_key, marca=grp_pa[0].fabricante_pai or "", grupo3_origem=RuleName.ENVIO_IMEDIATO.value, estoque_seg=0, dias=1, site="1", msg="PRAZO DEFINIDO 1 DIA")
            continue
        if all_pa_le_zero:
            for pa_cod, pa_r in pa_row_by_code.items():
                p = forn(pa_r, ItemTipo.PA)
                emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod, marca=pa_r.fabricante_produto or "", grupo3_origem=safe_group3(pa_r.nome_grupo3), estoque_seg=1000, dias=p, site=str(p), msg="INCLUIDO 1000 ESTOQUE SEG")
            for k in uniq_kits:
                p = forn(k, ItemTipo.KIT)
                emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "", marca=k.fabricante_kit or "", grupo3_origem=safe_group3(k.nome_grupo3), estoque_seg=0, dias=p, site=str(p), msg=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)")
            if pai_key != "__SEM_PAI__":
                p_pai = max((forn(r, ItemTipo.PAI) for r in grp_pa), default=0)
                emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PAI, pai_key, marca=grp_pa[0].fabricante_pai or "", grupo3_origem=RuleName.ENVIO_IMEDIATO.value, estoque_seg=0, dias=p_pai, site=str(p_pai), msg=f"PRAZO DEFINIDO {p_pai} DIAS (FORNECEDOR)")
            continue
        if any_pa_gt_zero:
            if pai_key != "__SEM_PAI__":
                emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PAI, pai_key, marca=grp_pa[0].fabricante_pai or "", grupo3_origem=RuleName.ENVIO_IMEDIATO.value, estoque_seg=0, dias=1, site="1", msg="PRAZO DEFINIDO 1 DIA")
            for pa_cod, pa_r in pa_row_by_code.items():
                if pa_stock_by_code.get(pa_cod, 0) > 0:
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod, marca=pa_r.fabricante_produto or "", grupo3_origem=safe_group3(pa_r.nome_grupo3), estoque_seg=0, dias=1, site="1", msg="PRAZO DEFINIDO 1 DIA")
                else:
                    p = forn(pa_r, ItemTipo.PA)
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod, marca=pa_r.fabricante_produto or "", grupo3_origem=safe_group3(pa_r.nome_grupo3), estoque_seg=0, dias=p, site=str(p), msg=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)")
            for k in uniq_kits:
                pa_cod = kit_pa_code(k)
                pa_disp = pa_stock_by_code.get(pa_cod, None) if pa_cod else None
                if pa_disp is not None and pa_disp > 0:
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "", marca=k.fabricante_kit or "", grupo3_origem=safe_group3(k.nome_grupo3), estoque_seg=0, dias=1, site="1", msg="PRAZO DEFINIDO 1 DIA")
                else:
                    p = forn(k, ItemTipo.KIT)
                    emit_action(RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "", marca=k.fabricante_kit or "", grupo3_origem=safe_group3(k.nome_grupo3), estoque_seg=0, dias=p, site=str(p), msg=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)")
            continue
