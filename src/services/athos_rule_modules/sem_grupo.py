from __future__ import annotations
from typing import Any, Optional
from .base import RuleContext, RuleName, ItemTipo, AthosAction, IGNORE_SEM_GRUPO_BRANDS, OUTLET_BRANDS_IMEDIATA, OUTLET_BRANDS_3_DAYS, IMEDIATA_TEXT, grupo3_bucket, norm_upper, safe_group3


def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    s = str(v).strip()
    return (not s) or (s.lower() in ("nan", "none"))


def _has_any_grupo_text(r) -> bool:
    return (not _is_blank(r.grupo_produto)) or (not _is_blank(r.grupo_kit)) or (not _is_blank(r.grupo_pai))


def apply(ctx: RuleContext) -> None:
    def emit_single(rule: RuleName, tipo: ItemTipo, codbarra: str, *, marca: str, grupo3_origem: str, grupo3: Optional[str], estoque_seg: Optional[int], produto_inativo: Optional[str], dias: Optional[int], site: Optional[str], msg: Optional[str]) -> None:
        if not codbarra or ctx.is_locked(codbarra):
            return
        a = AthosAction(rule=rule, tipo=tipo, codbarra=codbarra)
        a.grupo3 = grupo3
        a.estoque_seguranca = estoque_seg
        a.produto_inativo = produto_inativo
        a.dias_entrega = dias
        a.site_disponibilidade = site
        a.marca = marca or ""
        a.grupo3_origem_pa = grupo3_origem or ""
        if msg:
            a.add_msg(msg)
        ctx.upsert_action(a)
        ctx.lock(a.codbarra, rule)
        if msg:
            ctx.report(rule, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", msg)

    for r in ctx.rows:
        if grupo3_bucket(r.nome_grupo3) is not None:
            continue
        if not r.codbarra_produto:
            continue

        in_whitelist = r.codbarra_produto in ctx.whitelist_imediatos
        if not in_whitelist:
            if not (r.fabricante_produto or "").strip():
                continue
            if norm_upper(r.fabricante_produto) in IGNORE_SEM_GRUPO_BRANDS:
                continue
            if _has_any_grupo_text(r):
                continue
        if ctx.is_locked(r.codbarra_produto):
            continue

        disp = ctx.estoque_decisao(r)
        if in_whitelist:
            ctx.emit_for_pa_kit_pai(
                RuleName.NENHUM_GRUPO,
                r,
                grupo3=RuleName.ENVIO_IMEDIATO.value,
                estoque_pa=None,
                estoque_kit=None,
                estoque_pai=None,
                dias_entrega=None,
                site_disp=None,
                msg_pa="MOVIDO PARA GRUPO3 ENVIO IMEDIATO",
                msg_kit="MOVIDO PARA GRUPO3 ENVIO IMEDIATO",
                msg_pai="MOVIDO PARA GRUPO3 ENVIO IMEDIATO",
                attach_grupos=False,
            )
            continue

        if disp > 0:
            marca_group = norm_upper(r.fabricante_produto)
            if marca_group in OUTLET_BRANDS_IMEDIATA:
                dias_pa = 0
                site_pa = IMEDIATA_TEXT
                msg_pa = IMEDIATA_TEXT
            elif marca_group in OUTLET_BRANDS_3_DAYS:
                dias_pa = 3
                site_pa = "3"
                msg_pa = "PRAZO DEFINIDO 3 DIAS"
            else:
                dias_pa = 1
                site_pa = "1"
                msg_pa = "PRAZO DEFINIDO 1 DIA"

            ctx.emit_for_pa_kit_pai(
                RuleName.NENHUM_GRUPO,
                r,
                grupo3=RuleName.OUTLET.value,
                estoque_pa=0,
                estoque_kit=0,
                estoque_pai=None,
                dias_entrega=dias_pa,
                site_disp=site_pa,
                msg_pa=f"MOVIDO PARA GRUPO3 OUTLET | {msg_pa}",
                msg_kit=f"MOVIDO PARA GRUPO3 OUTLET | {msg_pa}",
                msg_pai=None,
                include_pai=False,
                attach_grupos=False,
            )

            pai_key = r.codbarra_pai or "__SEM_PAI__"
            if pai_key != "__SEM_PAI__" and not ctx.is_locked(pai_key):
                grp_rows = ctx.by_pai.get(pai_key, [])
                pa_stocks = {}
                for rr in grp_rows:
                    if not rr.codbarra_produto:
                        continue
                    if rr.codbarra_produto not in pa_stocks:
                        pa_stocks[rr.codbarra_produto] = ctx.estoque_pa(rr)
                all_gt_zero = bool(pa_stocks) and all(v > 0 for v in pa_stocks.values())
                base_pai = next((rr for rr in grp_rows if rr.fabricante_pai or rr.grupo_pai), r)
                if all_gt_zero:
                    dias_pai = dias_pa
                    site_pai = site_pa
                    msg_pai_text = msg_pa
                else:
                    p = ctx.prazo_fornecedor(base_pai, ItemTipo.PAI)
                    dias_pai = p
                    site_pai = str(p)
                    msg_pai_text = f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)"
                emit_single(RuleName.NENHUM_GRUPO, ItemTipo.PAI, pai_key, marca=base_pai.fabricante_pai or "", grupo3_origem=safe_group3(r.nome_grupo3), grupo3=RuleName.OUTLET.value, estoque_seg=0, produto_inativo=None, dias=dias_pai, site=site_pai, msg=f"MOVIDO PARA GRUPO3 OUTLET | {msg_pai_text}")
            continue

        p_pa = ctx.prazo_fornecedor(r, ItemTipo.PA)
        p_kit = ctx.prazo_fornecedor(r, ItemTipo.KIT)
        p_pai = ctx.prazo_fornecedor(r, ItemTipo.PAI)

        emit_single(RuleName.NENHUM_GRUPO, ItemTipo.PA, r.codbarra_produto or "", marca=r.fabricante_produto or "", grupo3_origem=safe_group3(r.nome_grupo3), grupo3=None, estoque_seg=1000, produto_inativo=None, dias=p_pa, site=str(p_pa), msg="INCLUIDO 1000 ESTOQUE SEG")
        if r.codbarra_kit:
            emit_single(RuleName.NENHUM_GRUPO, ItemTipo.KIT, r.codbarra_kit or "", marca=r.fabricante_kit or "", grupo3_origem=safe_group3(r.nome_grupo3), grupo3=None, estoque_seg=0, produto_inativo=None, dias=p_kit, site=str(p_kit), msg=f"PRAZO DEFINIDO {p_kit} DIAS (FORNECEDOR)")
        if r.codbarra_pai:
            emit_single(RuleName.NENHUM_GRUPO, ItemTipo.PAI, r.codbarra_pai or "", marca=r.fabricante_pai or "", grupo3_origem=safe_group3(r.nome_grupo3), grupo3=None, estoque_seg=0, produto_inativo=None, dias=p_pai, site=str(p_pai), msg=f"PRAZO DEFINIDO {p_pai} DIAS (FORNECEDOR)")
