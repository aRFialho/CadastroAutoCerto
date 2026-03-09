# src/services/athos_rules_engine.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set
from collections import defaultdict, Counter

from .athos_models import (
    AthosAction,
    AthosReportLine,
    AthosRow,
    ItemTipo,
    RuleName,
    ORDERED_RULES,
    normalize_ean,
    grupo3_bucket,
    norm_upper,
    parse_int_safe,
    is_imediata,
    apply_prazo,
    apply_imediata,
)

# Marcas da regra especial do ENVIO IMEDIATO (somente relatório)
SPECIAL_IMEDIATO_BRANDS = {
    "MOVEIS VILA RICA",
    "COLIBRI MOVEIS",
    "MADETEC",
    "CAEMMUN",
    "LINEA BRASIL",
}

# ✅ DROSSI tratado como DMOV (3 dias quando disponível > 0)
OUTLET_BRANDS_3_DAYS = {"DMOV", "DMOV2", "DROSSI"}
OUTLET_BRANDS_IMEDIATA = {"KONFORT", "CASA DO PUFF", "DIVINI DECOR"}

# ✅ Marcas DMOV para ENVIO IMEDIATO (inclui DROSSI)
DMOV_BRANDS = {"DMOV2", "DROSSI"}

# Ignorar no "Sem Grupo"
IGNORE_SEM_GRUPO_BRANDS = {"DMOV - MP"}

# ✅ Padrão único do sistema (pedido): "Imediata"
IMEDIATA_TEXT = "Imediata"


@dataclass
class AthosOutputs:
    actions_by_rule: Dict[RuleName, List[AthosAction]]
    report_lines: List[AthosReportLine]


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        try:
            s = str(v).strip().replace(",", ".")
            return float(s)
        except Exception:
            return None


def _to_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _safe_group3(g3: Optional[str]) -> str:
    return (g3 or "").strip()


def _to_row(d: Dict[str, Any]) -> AthosRow:
    def g(*keys: str) -> Any:
        for k in keys:
            if k in d:
                return d[k]
            ku = k.upper()
            if ku in d:
                return d[ku]
            kl = k.lower()
            if kl in d:
                return d[kl]
        return None

    return AthosRow(
        codbarra_produto=normalize_ean(g("CODBARRA_PRODUTO")),
        estoque_real_produto=_to_float(g("ESTOQUE_REAL_PRODUTO")),
        prazo_produto=g("PRAZO_PRODUTO"),
        fabricante_produto=_to_str(g("FABRICANTE_PRODUTO")),
        nome_grupo3=_to_str(g("NOME_GRUPO3")),
        grupo_produto=_to_str(g("GRUPO_PRODUTO")),
        codbarra_kit=normalize_ean(g("CODBARRA_KIT")),
        estoque_real_kit=_to_float(g("ESTOQUE_REAL_KIT")),
        prazo_kit=g("PRAZO_KIT"),
        fabricante_kit=_to_str(g("FABRICANTE_KIT")),
        grupo_kit=_to_str(g("GRUPO_KIT")),
        codbarra_pai=normalize_ean(g("CODBARRA_PAI")),
        prazo_pai=g("PRAZO_PAI"),
        fabricante_pai=_to_str(g("FABRICANTE_PAI")),
        grupo_pai=_to_str(g("GRUPO_PAI")),
    )


def process_rows(
    sql_rows: List[Dict[str, Any]],
    whitelist_imediatos: Set[str],
    supplier_prazo_lookup: Optional[Callable[[str], Optional[int]]] = None,
) -> AthosOutputs:
    rows = [_to_row(r) for r in sql_rows]

    by_pai: Dict[str, List[AthosRow]] = defaultdict(list)
    for r in rows:
        pai = r.codbarra_pai or "__SEM_PAI__"
        by_pai[pai].append(r)

    locked_by: Dict[str, RuleName] = {}
    blocked_codbar: Set[str] = set()

    actions_by_rule: Dict[RuleName, Dict[str, AthosAction]] = {rn: {} for rn in ORDERED_RULES}
    report_lines: List[AthosReportLine] = []

    def lock(ean: str, rule: RuleName) -> None:
        locked_by[ean] = rule

    def is_locked(ean: str) -> bool:
        return ean in locked_by or ean in blocked_codbar

    #
    # ✅ ESTOQUE DE DECISÃO (regra do projeto)
    #
    kit_counts = Counter([r.codbarra_kit for r in rows if r.codbarra_kit])

    def _estoque_pa(r: AthosRow) -> float:
        """Estoque real do PA (sempre o do produto)."""
        return float(r.estoque_real_produto or 0)

    def _estoque_kit(r: AthosRow) -> float:
        """Estoque real do KIT (sempre o do kit)."""
        return float(r.estoque_real_kit or 0)

    def _estoque_decisao(r: AthosRow) -> float:
        """
        Estoque usado nas regras que comparam estoque e podem sofrer com KIT repetido.
        - Se KIT repete: usa ESTOQUE_REAL_KIT
        - Senão: usa ESTOQUE_REAL_PRODUTO
        """
        if r.codbarra_kit and kit_counts.get(r.codbarra_kit, 0) > 1:
            try:
                return float(r.estoque_real_kit or 0)
            except Exception:
                return float(r.estoque_real_produto or 0)
        return float(r.estoque_real_produto or 0)

    def _prazo_fornecedor(r: AthosRow, which: ItemTipo) -> int:
        if which == ItemTipo.PA:
            grupo = r.grupo_produto
            marca = r.fabricante_produto
            prazo_fallback = r.prazo_produto
        elif which == ItemTipo.KIT:
            grupo = r.grupo_kit
            marca = r.fabricante_kit
            prazo_fallback = r.prazo_kit
        else:
            grupo = r.grupo_pai
            marca = r.fabricante_pai
            prazo_fallback = r.prazo_pai

        p = parse_int_safe(grupo)
        if p is not None:
            return int(p)

        m = norm_upper(marca)
        if supplier_prazo_lookup and m:
            try:
                db_p = supplier_prazo_lookup(m)
                if db_p is not None:
                    return int(db_p)
            except Exception:
                pass

        p2 = parse_int_safe(prazo_fallback)
        if p2 is not None:
            return int(p2)

        return 0

    def _normalize_action(a: AthosAction) -> None:
        if a.dias_entrega == 0:
            a.site_disponibilidade = IMEDIATA_TEXT
        if a.site_disponibilidade is not None:
            s = str(a.site_disponibilidade).strip()
            if s.lower() == "imediata" or s.upper() == "IMEDIATA":
                a.site_disponibilidade = IMEDIATA_TEXT

    def upsert_action(action: AthosAction) -> None:
        _normalize_action(action)

        bucket = actions_by_rule[action.rule]
        existing = bucket.get(action.codbarra)
        if existing is None:
            bucket[action.codbarra] = action
            return

        if existing.grupo3 is None and action.grupo3 is not None:
            existing.grupo3 = action.grupo3
        if existing.estoque_seguranca is None and action.estoque_seguranca is not None:
            existing.estoque_seguranca = action.estoque_seguranca
        if existing.produto_inativo is None and action.produto_inativo is not None:
            existing.produto_inativo = action.produto_inativo
        if existing.dias_entrega is None and action.dias_entrega is not None:
            existing.dias_entrega = action.dias_entrega
        if existing.site_disponibilidade is None and action.site_disponibilidade is not None:
            existing.site_disponibilidade = action.site_disponibilidade

        _normalize_action(existing)

        if not existing.marca and action.marca:
            existing.marca = action.marca
        if not existing.grupo3_origem_pa and action.grupo3_origem_pa:
            existing.grupo3_origem_pa = action.grupo3_origem_pa

        for m in action.mensagens:
            if m not in existing.mensagens:
                existing.mensagens.append(m)

    def report(rule: RuleName, codbarra: str, tipo: ItemTipo, marca: str, grupo3: str, acao: str) -> None:
        report_lines.append(
            AthosReportLine(
                planilha=rule.value,
                codbarra=codbarra,
                tipo=tipo.value,
                marca=marca or "",
                grupo3=grupo3 or "",
                acao=acao,
            )
        )

    def emit_for_pa_kit_pai(
        rule: RuleName,
        r: AthosRow,
        *,
        grupo3: Optional[str] = None,
        produto_inativo: Optional[str] = None,
        dias_entrega: Optional[int] = None,
        site_disp: Optional[str] = None,
        estoque_pa: Optional[int] = None,
        estoque_kit: Optional[int] = None,
        estoque_pai: Optional[int] = None,
        msg_pa: Optional[str] = None,
        msg_kit: Optional[str] = None,
        msg_pai: Optional[str] = None,
        include_pa: bool = True,
        include_kit: bool = True,
        include_pai: bool = True,
        attach_grupos: bool = False,
    ) -> None:
        g3_pa = _safe_group3(r.nome_grupo3)

        final_site = site_disp
        if dias_entrega == 0:
            final_site = IMEDIATA_TEXT
        elif final_site is not None:
            s = str(final_site).strip()
            if s.lower() == "imediata" or s.upper() == "IMEDIATA":
                final_site = IMEDIATA_TEXT

        final_msg_pa = IMEDIATA_TEXT if (msg_pa and msg_pa.strip().lower() == "imediata") else msg_pa
        final_msg_kit = IMEDIATA_TEXT if (msg_kit and msg_kit.strip().lower() == "imediata") else msg_kit
        final_msg_pai = IMEDIATA_TEXT if (msg_pai and msg_pai.strip().lower() == "imediata") else msg_pai

        def _attach(a: AthosAction) -> None:
            if not attach_grupos:
                return
            setattr(a, "grupo_produto", r.grupo_produto)
            setattr(a, "grupo_kit", r.grupo_kit)
            setattr(a, "grupo_pai", r.grupo_pai)

        if include_pa and r.codbarra_produto and not is_locked(r.codbarra_produto):
            a = AthosAction(rule=rule, tipo=ItemTipo.PA, codbarra=r.codbarra_produto)
            a.grupo3 = grupo3
            a.produto_inativo = produto_inativo
            a.dias_entrega = dias_entrega
            a.site_disponibilidade = final_site
            a.estoque_seguranca = estoque_pa
            a.marca = r.fabricante_produto or ""
            a.grupo3_origem_pa = g3_pa
            _attach(a)
            if final_msg_pa:
                a.add_msg(final_msg_pa)
                report(rule, a.codbarra, a.tipo, a.marca or "", g3_pa, final_msg_pa)
            upsert_action(a)
            lock(a.codbarra, rule)

        if include_kit and r.codbarra_kit and not is_locked(r.codbarra_kit):
            a = AthosAction(rule=rule, tipo=ItemTipo.KIT, codbarra=r.codbarra_kit)
            a.grupo3 = grupo3
            a.produto_inativo = produto_inativo
            a.dias_entrega = dias_entrega
            a.site_disponibilidade = final_site
            a.estoque_seguranca = estoque_kit
            a.marca = r.fabricante_kit or ""
            a.grupo3_origem_pa = g3_pa
            _attach(a)
            if final_msg_kit:
                a.add_msg(final_msg_kit)
                report(rule, a.codbarra, a.tipo, a.marca or "", g3_pa, final_msg_kit)
            upsert_action(a)
            lock(a.codbarra, rule)

        if include_pai and r.codbarra_pai and not is_locked(r.codbarra_pai):
            a = AthosAction(rule=rule, tipo=ItemTipo.PAI, codbarra=r.codbarra_pai)
            a.grupo3 = grupo3
            a.produto_inativo = produto_inativo
            a.dias_entrega = dias_entrega
            a.site_disponibilidade = final_site
            a.estoque_seguranca = estoque_pai
            a.marca = r.fabricante_pai or ""
            a.grupo3_origem_pa = g3_pa
            _attach(a)
            if final_msg_pai:
                a.add_msg(final_msg_pai)
                report(rule, a.codbarra, a.tipo, a.marca or "", g3_pa, final_msg_pai)
            upsert_action(a)
            lock(a.codbarra, rule)

    #
    # 1) FORA DE LINHA
    #
    for r in rows:
        g3 = grupo3_bucket(r.nome_grupo3)
        if g3 != RuleName.FORA_DE_LINHA.value:
            continue
        if not r.codbarra_produto:
            continue
        if _estoque_pa(r) <= 0:
            emit_for_pa_kit_pai(
                RuleName.FORA_DE_LINHA,
                r,
                produto_inativo="T",
                msg_pa="PRODUTO INATIVADO",
                msg_kit="PRODUTO INATIVADO",
                msg_pai="PRODUTO INATIVADO",
            )

    #
    # 2) ESTOQUE COMPARTILHADO
    #
    for pai_key, group_rows in by_pai.items():
        esc_rows = [r for r in group_rows if grupo3_bucket(r.nome_grupo3) == RuleName.ESTOQUE_COMPARTILHADO.value]
        if not esc_rows:
            continue

        kit_prazos: List[int] = []
        for r in esc_rows:
            if not r.codbarra_kit or is_locked(r.codbarra_kit):
                continue

            if is_imediata(r.prazo_produto):
                a = AthosAction(rule=RuleName.ESTOQUE_COMPARTILHADO, tipo=ItemTipo.KIT, codbarra=r.codbarra_kit)
                apply_imediata(a)
                a.marca = r.fabricante_kit or ""
                a.grupo3_origem_pa = _safe_group3(r.nome_grupo3)
                a.add_msg("PRAZO HERDADO DO PA (Imediata)")
                upsert_action(a)
                lock(a.codbarra, RuleName.ESTOQUE_COMPARTILHADO)
                report(
                    RuleName.ESTOQUE_COMPARTILHADO,
                    a.codbarra, a.tipo, a.marca or "",
                    a.grupo3_origem_pa or "",
                    "PRAZO HERDADO DO PA (Imediata)",
                )
                continue

            p = parse_int_safe(r.prazo_produto)
            if p is None:
                continue

            kit_prazos.append(p)
            a = AthosAction(rule=RuleName.ESTOQUE_COMPARTILHADO, tipo=ItemTipo.KIT, codbarra=r.codbarra_kit)
            apply_prazo(a, p)
            a.marca = r.fabricante_kit or ""
            a.grupo3_origem_pa = _safe_group3(r.nome_grupo3)
            a.add_msg(f"PRAZO HERDADO DO PA: {p} DIAS")
            upsert_action(a)
            lock(a.codbarra, RuleName.ESTOQUE_COMPARTILHADO)
            report(
                RuleName.ESTOQUE_COMPARTILHADO,
                a.codbarra, a.tipo, a.marca or "",
                a.grupo3_origem_pa or "",
                f"PRAZO HERDADO DO PA: {p} DIAS",
            )

        if pai_key != "__SEM_PAI__" and kit_prazos and not is_locked(pai_key):
            maior = max(kit_prazos)
            a = AthosAction(rule=RuleName.ESTOQUE_COMPARTILHADO, tipo=ItemTipo.PAI, codbarra=pai_key)
            apply_prazo(a, maior)
            any_row = next((rr for rr in esc_rows if rr.fabricante_pai), None)
            a.marca = any_row.fabricante_pai if any_row else ""
            a.grupo3_origem_pa = RuleName.ESTOQUE_COMPARTILHADO.value
            a.add_msg(f"MAIOR PRAZO DOS KITS: {maior} DIAS")
            upsert_action(a)
            lock(a.codbarra, RuleName.ESTOQUE_COMPARTILHADO)
            report(
                RuleName.ESTOQUE_COMPARTILHADO,
                a.codbarra, a.tipo, a.marca or "",
                a.grupo3_origem_pa or "",
                f"MAIOR PRAZO DOS KITS: {maior} DIAS",
            )    #
    # 3) ENVIO IMEDIATO
    #
    IMEDIATO_IGNORED_BRANDS = {"JOMARCA", "BOBINONDA", "DMOV - MP"}

    def _is_imediato_ignored_row(r: AthosRow) -> bool:
        return (
            norm_upper(r.fabricante_produto) in IMEDIATO_IGNORED_BRANDS
            or norm_upper(r.fabricante_kit) in IMEDIATO_IGNORED_BRANDS
            or norm_upper(r.fabricante_pai) in IMEDIATO_IGNORED_BRANDS
        )

    # 3.1) remover do grupo3 quem não está na whitelist
    for r in rows:
        if grupo3_bucket(r.nome_grupo3) != RuleName.ENVIO_IMEDIATO.value:
            continue
        if _is_imediato_ignored_row(r):
            continue
        if not r.codbarra_produto or is_locked(r.codbarra_produto):
            continue

        if r.codbarra_produto not in whitelist_imediatos:
            a = AthosAction(rule=RuleName.ENVIO_IMEDIATO, tipo=ItemTipo.PA, codbarra=r.codbarra_produto)
            a.grupo3 = "APAGAR"
            a.marca = r.fabricante_produto or ""
            a.grupo3_origem_pa = _safe_group3(r.nome_grupo3)
            a.add_msg("RETIRADO DO GRUPO3 ENVIO IMEDIATO")
            upsert_action(a)
            lock(a.codbarra, RuleName.ENVIO_IMEDIATO)
            report(
                RuleName.ENVIO_IMEDIATO,
                a.codbarra, a.tipo, a.marca or "",
                a.grupo3_origem_pa or "",
                "RETIRADO DO GRUPO3 ENVIO IMEDIATO",
            )

    # 3.2) regra especial só relatório
    for pai_key, group_rows in by_pai.items():
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

        all_le_zero = all(_estoque_decisao(rr) <= 0 for rr in grp)
        if not all_le_zero:
            continue

        for rr in grp:
            if rr.codbarra_produto:
                blocked_codbar.add(rr.codbarra_produto)
            if rr.codbarra_kit:
                blocked_codbar.add(rr.codbarra_kit)
            if rr.codbarra_pai:
                blocked_codbar.add(rr.codbarra_pai)

        for rr in special_pas:
            report(
                RuleName.ENVIO_IMEDIATO,
                rr.codbarra_produto or "",
                ItemTipo.PA,
                rr.fabricante_produto or "",
                _safe_group3(rr.nome_grupo3),
                "Colocar cód Fabricante, mudar para Estoque Compartilhado",
            )

    IMEDIATA_BRANDS = {"KONFORT", "CASA DO PUFF", "DIVINI DECOR", "LUMIL", "MADERATTO"}

    # 3.3) processamento por pai
    for pai_key, group_rows in by_pai.items():
        grp_pa = [
            r for r in group_rows
            if grupo3_bucket(r.nome_grupo3) == RuleName.ENVIO_IMEDIATO.value
            and r.codbarra_produto
            and r.codbarra_produto in whitelist_imediatos
            and not _is_imediato_ignored_row(r)
        ]
        if not grp_pa:
            continue

        marca_group = norm_upper(grp_pa[0].fabricante_produto)

        # Map PA
        pa_row_by_code: Dict[str, AthosRow] = {}
        pa_stock_by_code: Dict[str, float] = {}
        for r in grp_pa:
            if r.codbarra_produto:
                pa_row_by_code[r.codbarra_produto] = r
                pa_stock_by_code[r.codbarra_produto] = _estoque_pa(r)

        all_pa_gt_zero = bool(pa_stock_by_code) and all(v > 0 for v in pa_stock_by_code.values())
        all_pa_le_zero = bool(pa_stock_by_code) and all(v <= 0 for v in pa_stock_by_code.values())
        any_pa_gt_zero = bool(pa_stock_by_code) and any(v > 0 for v in pa_stock_by_code.values())

        # Collect KITS (unique)
        kits_by_code: Dict[str, AthosRow] = {}
        for rr in group_rows:
            if grupo3_bucket(rr.nome_grupo3) != RuleName.ENVIO_IMEDIATO.value:
                continue
            if _is_imediato_ignored_row(rr):
                continue
            if rr.codbarra_kit:
                kits_by_code[rr.codbarra_kit] = rr
        uniq_kits = list(kits_by_code.values())

        def _emit_action(
            rule: RuleName,
            tipo: ItemTipo,
            codbarra: str,
            *,
            marca: str,
            grupo3_origem: str,
            estoque_seg: Optional[int],
            dias: Optional[int],
            site: Optional[str],
            msg: str,
        ) -> None:
            if not codbarra or is_locked(codbarra):
                return
            a = AthosAction(rule=rule, tipo=tipo, codbarra=codbarra)
            a.estoque_seguranca = estoque_seg
            a.dias_entrega = dias
            a.site_disponibilidade = site
            a.marca = marca or ""
            a.grupo3_origem_pa = grupo3_origem or ""
            a.add_msg(msg)
            upsert_action(a)
            lock(a.codbarra, rule)
            report(rule, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", msg)

        def _kit_pa_code(k: AthosRow) -> Optional[str]:
            if k.codbarra_produto and k.codbarra_produto in pa_stock_by_code:
                return k.codbarra_produto
            if len(pa_stock_by_code) == 1:
                return next(iter(pa_stock_by_code.keys()))
            return None

        def _forn(r: AthosRow, tipo: ItemTipo) -> int:
            return _prazo_fornecedor(r, tipo)

        # =========================
        # ✅ DMOV_BRANDS (DMOV2 + DROSSI)
        # =========================
        if marca_group in DMOV_BRANDS:
            # PA: estoque seg 1000; prazo 3 se >0 senão fornecedor
            for pa_cod, pa_r in pa_row_by_code.items():
                if pa_stock_by_code.get(pa_cod, 0) > 0:
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod,
                        marca=pa_r.fabricante_produto or "",
                        grupo3_origem=_safe_group3(pa_r.nome_grupo3),
                        estoque_seg=1000, dias=3, site="3",
                        msg="INCLUIDO 1000 ESTOQUE SEG",
                    )
                else:
                    p = _forn(pa_r, ItemTipo.PA)
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod,
                        marca=pa_r.fabricante_produto or "",
                        grupo3_origem=_safe_group3(pa_r.nome_grupo3),
                        estoque_seg=1000, dias=p, site=str(p),
                        msg="INCLUIDO 1000 ESTOQUE SEG",
                    )

            # KIT: estoque seg 0; prazo segue PA
            for k in uniq_kits:
                pa_cod = _kit_pa_code(k)
                pa_disp = pa_stock_by_code.get(pa_cod, None) if pa_cod else None
                if pa_disp is not None and pa_disp > 0:
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "",
                        marca=k.fabricante_kit or "",
                        grupo3_origem=_safe_group3(k.nome_grupo3),
                        estoque_seg=0, dias=3, site="3",
                        msg="PRAZO DEFINIDO 3 DIAS",
                    )
                else:
                    p = _forn(k, ItemTipo.KIT)
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "",
                        marca=k.fabricante_kit or "",
                        grupo3_origem=_safe_group3(k.nome_grupo3),
                        estoque_seg=0, dias=p, site=str(p),
                        msg=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                    )

            # PAI: se TODOS PAs >0 -> 3 dias, senão fornecedor
            if pai_key != "__SEM_PAI__":
                if all_pa_gt_zero:
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.PAI, pai_key,
                        marca=grp_pa[0].fabricante_pai or "",
                        grupo3_origem=RuleName.ENVIO_IMEDIATO.value,
                        estoque_seg=0, dias=3, site="3",
                        msg="PRAZO DEFINIDO 3 DIAS",
                    )
                else:
                    p_pai = max((_forn(r, ItemTipo.PAI) for r in grp_pa), default=0)
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.PAI, pai_key,
                        marca=grp_pa[0].fabricante_pai or "",
                        grupo3_origem=RuleName.ENVIO_IMEDIATO.value,
                        estoque_seg=0, dias=p_pai, site=str(p_pai),
                        msg=f"PRAZO DEFINIDO {p_pai} DIAS (FORNECEDOR)",
                    )
            continue

        # =========================
        # IMEDIATA BRANDS
        # =========================
        if marca_group in IMEDIATA_BRANDS:
            # Cenário 1: TODOS PAs > 0 => tudo Imediata
            if all_pa_gt_zero:
                for pa_cod, pa_r in pa_row_by_code.items():
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod,
                        marca=pa_r.fabricante_produto or "",
                        grupo3_origem=_safe_group3(pa_r.nome_grupo3),
                        estoque_seg=0, dias=0, site=IMEDIATA_TEXT,
                        msg=IMEDIATA_TEXT,
                    )
                for k in uniq_kits:
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "",
                        marca=k.fabricante_kit or "",
                        grupo3_origem=_safe_group3(k.nome_grupo3),
                        estoque_seg=0, dias=0, site=IMEDIATA_TEXT,
                        msg=IMEDIATA_TEXT,
                    )
                if pai_key != "__SEM_PAI__":
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.PAI, pai_key,
                        marca=grp_pa[0].fabricante_pai or "",
                        grupo3_origem=RuleName.ENVIO_IMEDIATO.value,
                        estoque_seg=0, dias=0, site=IMEDIATA_TEXT,
                        msg=IMEDIATA_TEXT,
                    )
                continue

            # Cenário 2: TODOS PAs <= 0 => PA=1000 fornecedor; kit/pai fornecedor
            if all_pa_le_zero:
                for pa_cod, pa_r in pa_row_by_code.items():
                    p = _forn(pa_r, ItemTipo.PA)
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod,
                        marca=pa_r.fabricante_produto or "",
                        grupo3_origem=_safe_group3(pa_r.nome_grupo3),
                        estoque_seg=1000, dias=p, site=str(p),
                        msg="INCLUIDO 1000 ESTOQUE SEG",
                    )
                for k in uniq_kits:
                    p = _forn(k, ItemTipo.KIT)
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "",
                        marca=k.fabricante_kit or "",
                        grupo3_origem=_safe_group3(k.nome_grupo3),
                        estoque_seg=0, dias=p, site=str(p),
                        msg=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                    )
                if pai_key != "__SEM_PAI__":
                    p_pai = max((_forn(r, ItemTipo.PAI) for r in grp_pa), default=0)
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.PAI, pai_key,
                        marca=grp_pa[0].fabricante_pai or "",
                        grupo3_origem=RuleName.ENVIO_IMEDIATO.value,
                        estoque_seg=0, dias=p_pai, site=str(p_pai),
                        msg=f"PRAZO DEFINIDO {p_pai} DIAS (FORNECEDOR)",
                    )
                continue

            # Cenário 3: misto (pelo menos 1 >0) => Pai Imediata; PA/KIT seguem seu PA
            if any_pa_gt_zero:
                if pai_key != "__SEM_PAI__":
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.PAI, pai_key,
                        marca=grp_pa[0].fabricante_pai or "",
                        grupo3_origem=RuleName.ENVIO_IMEDIATO.value,
                        estoque_seg=0, dias=0, site=IMEDIATA_TEXT,
                        msg=IMEDIATA_TEXT,
                    )
                for pa_cod, pa_r in pa_row_by_code.items():
                    if pa_stock_by_code.get(pa_cod, 0) > 0:
                        _emit_action(
                            RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod,
                            marca=pa_r.fabricante_produto or "",
                            grupo3_origem=_safe_group3(pa_r.nome_grupo3),
                            estoque_seg=0, dias=0, site=IMEDIATA_TEXT,
                            msg=IMEDIATA_TEXT,
                        )
                    else:
                        p = _forn(pa_r, ItemTipo.PA)
                        _emit_action(
                            RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod,
                            marca=pa_r.fabricante_produto or "",
                            grupo3_origem=_safe_group3(pa_r.nome_grupo3),
                            estoque_seg=0, dias=p, site=str(p),
                            msg=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                        )
                for k in uniq_kits:
                    pa_cod = _kit_pa_code(k)
                    pa_disp = pa_stock_by_code.get(pa_cod, None) if pa_cod else None
                    if pa_disp is not None and pa_disp > 0:
                        _emit_action(
                            RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "",
                            marca=k.fabricante_kit or "",
                            grupo3_origem=_safe_group3(k.nome_grupo3),
                            estoque_seg=0, dias=0, site=IMEDIATA_TEXT,
                            msg=IMEDIATA_TEXT,
                        )
                    else:
                        p = _forn(k, ItemTipo.KIT)
                        _emit_action(
                            RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "",
                            marca=k.fabricante_kit or "",
                            grupo3_origem=_safe_group3(k.nome_grupo3),
                            estoque_seg=0, dias=p, site=str(p),
                            msg=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                        )
                continue

        # =========================
        # OUTRAS MARCAS
        # =========================
        # Cenário 1: TODOS PAs > 0 => 1 dia
        if all_pa_gt_zero:
            for pa_cod, pa_r in pa_row_by_code.items():
                _emit_action(
                    RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod,
                    marca=pa_r.fabricante_produto or "",
                    grupo3_origem=_safe_group3(pa_r.nome_grupo3),
                    estoque_seg=0, dias=1, site="1",
                    msg="PRAZO DEFINIDO 1 DIA",
                )
            for k in uniq_kits:
                _emit_action(
                    RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "",
                    marca=k.fabricante_kit or "",
                    grupo3_origem=_safe_group3(k.nome_grupo3),
                    estoque_seg=0, dias=1, site="1",
                    msg="PRAZO DEFINIDO 1 DIA",
                )
            if pai_key != "__SEM_PAI__":
                _emit_action(
                    RuleName.ENVIO_IMEDIATO, ItemTipo.PAI, pai_key,
                    marca=grp_pa[0].fabricante_pai or "",
                    grupo3_origem=RuleName.ENVIO_IMEDIATO.value,
                    estoque_seg=0, dias=1, site="1",
                    msg="PRAZO DEFINIDO 1 DIA",
                )
            continue

        # Cenário 2: TODOS PAs <=0= 0 => PA=1000 fornecedor
        if all_pa_le_zero:
            for pa_cod, pa_r in pa_row_by_code.items():
                p = _forn(pa_r, ItemTipo.PA)
                _emit_action(
                    RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod,
                    marca=pa_r.fabricante_produto or "",
                    grupo3_origem=_safe_group3(pa_r.nome_grupo3),
                    estoque_seg=1000, dias=p, site=str(p),
                    msg="INCLUIDO 1000 ESTOQUE SEG",
                )
            for k in uniq_kits:
                p = _forn(k, ItemTipo.KIT)
                _emit_action(
                    RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "",
                    marca=k.fabricante_kit or "",
                    grupo3_origem=_safe_group3(k.nome_grupo3),
                    estoque_seg=0, dias=p, site=str(p),
                    msg=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                )
            if pai_key != "__SEM_PAI__":
                p_pai = max((_forn(r, ItemTipo.PAI) for r in grp_pa), default=0)
                _emit_action(
                    RuleName.ENVIO_IMEDIATO, ItemTipo.PAI, pai_key,
                    marca=grp_pa[0].fabricante_pai or "",
                    grupo3_origem=RuleName.ENVIO_IMEDIATO.value,
                    estoque_seg=0, dias=p_pai, site=str(p_pai),
                    msg=f"PRAZO DEFINIDO {p_pai} DIAS (FORNECEDOR)",
                )
            continue

        # Cenário 3: misto => Pai 1 dia; PA/KIT seguem seu PA
        if any_pa_gt_zero:
            if pai_key != "__SEM_PAI__":
                _emit_action(
                    RuleName.ENVIO_IMEDIATO, ItemTipo.PAI, pai_key,
                    marca=grp_pa[0].fabricante_pai or "",
                    grupo3_origem=RuleName.ENVIO_IMEDIATO.value,
                    estoque_seg=0, dias=1, site="1",
                    msg="PRAZO DEFINIDO 1 DIA",
                )
            for pa_cod, pa_r in pa_row_by_code.items():
                if pa_stock_by_code.get(pa_cod, 0) > 0:
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod,
                        marca=pa_r.fabricante_produto or "",
                        grupo3_origem=_safe_group3(pa_r.nome_grupo3),
                        estoque_seg=0, dias=1, site="1",
                        msg="PRAZO DEFINIDO 1 DIA",
                    )
                else:
                    p = _forn(pa_r, ItemTipo.PA)
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.PA, pa_cod,
                        marca=pa_r.fabricante_produto or "",
                        grupo3_origem=_safe_group3(pa_r.nome_grupo3),
                        estoque_seg=0, dias=p, site=str(p),
                        msg=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                    )
            for k in uniq_kits:
                pa_cod = _kit_pa_code(k)
                pa_disp = pa_stock_by_code.get(pa_cod, None) if pa_cod else None
                if pa_disp is not None and pa_disp > 0:
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "",
                        marca=k.fabricante_kit or "",
                        grupo3_origem=_safe_group3(k.nome_grupo3),
                        estoque_seg=0, dias=1, site="1",
                        msg="PRAZO DEFINIDO 1 DIA",
                    )
                else:
                    p = _forn(k, ItemTipo.KIT)
                    _emit_action(
                        RuleName.ENVIO_IMEDIATO, ItemTipo.KIT, k.codbarra_kit or "",
                        marca=k.fabricante_kit or "",
                        grupo3_origem=_safe_group3(k.nome_grupo3),
                        estoque_seg=0, dias=p, site=str(p),
                        msg=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                    )
            continue    #
    # 4) NENHUM GRUPO  ✅ CONFORME REGRAS OFICIAIS
    #

    def _is_blank(v: Any) -> bool:
        if v is None:
            return True
        s = str(v).strip()
        return (not s) or (s.lower() in ("nan", "none"))

    def _has_any_grupo_text(r: AthosRow) -> bool:
        return (not _is_blank(r.grupo_produto)) or (not _is_blank(r.grupo_kit)) or (not _is_blank(r.grupo_pai))

    def _emit_single(
        rule: RuleName,
        tipo: ItemTipo,
        codbarra: str,
        *,
        marca: str,
        grupo3_origem: str,
        grupo3: Optional[str],
        estoque_seg: Optional[int],
        produto_inativo: Optional[str],
        dias: Optional[int],
        site: Optional[str],
        msg: Optional[str],
    ) -> None:
        if not codbarra or is_locked(codbarra):
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
        upsert_action(a)
        lock(a.codbarra, rule)
        if msg:
            report(rule, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", msg)

    for r in rows:
        # Só entra quando não tem GRUPO3
        if grupo3_bucket(r.nome_grupo3) is not None:
            continue

        if not r.codbarra_produto:
            continue

        # Whitelist é fonte da verdade
        in_whitelist = r.codbarra_produto in whitelist_imediatos

        # Filtros só quando NÃO whitelist
        if not in_whitelist:
            if not (r.fabricante_produto or "").strip():
                continue
            if norm_upper(r.fabricante_produto) in IGNORE_SEM_GRUPO_BRANDS:
                continue
            if _has_any_grupo_text(r):
                continue

        if is_locked(r.codbarra_produto):
            continue

        disp = _estoque_decisao(r)

        # ✅ Whitelist: sempre reclassifica para ENVIO IMEDIATO
        if in_whitelist:
            emit_for_pa_kit_pai(
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

        # =========================
        # A) Disponível > 0
        # =========================
        if disp > 0:
            # ✅ DROSSI entra como DMOV (3 dias)
            marca_group = norm_upper(r.fabricante_produto)
            if marca_group in OUTLET_BRANDS_IMEDIATA:
                dias_pa = 0
                site_pa = IMEDIATA_TEXT
                msg_pa = IMEDIATA_TEXT
            elif marca_group in OUTLET_BRANDS_3_DAYS:
                # ✅ OUTLET_BRANDS_3_DAYS já inclui DROSSI
                dias_pa = 3
                site_pa = "3"
                msg_pa = "PRAZO DEFINIDO 3 DIAS"
            else:
                dias_pa = 1
                site_pa = "1"
                msg_pa = "PRAZO DEFINIDO 1 DIA"

            # PA e KIT seguem o mesmo prazo quando PA > 0
            emit_for_pa_kit_pai(
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

            # PAI: depende de TODOS os PAs do mesmo pai
            pai_key = r.codbarra_pai or "__SEM_PAI__"
            if pai_key != "__SEM_PAI__" and not is_locked(pai_key):
                grp_rows = by_pai.get(pai_key, [])
                pa_stocks = {}
                for rr in grp_rows:
                    if not rr.codbarra_produto:
                        continue
                    if rr.codbarra_produto not in pa_stocks:
                        # ✅ BUG F CORRIGIDO: usa _estoque_pa para decisão do PAI
                        pa_stocks[rr.codbarra_produto] = _estoque_pa(rr)

                all_gt_zero = bool(pa_stocks) and all(v > 0 for v in pa_stocks.values())
                base_pai = next((rr for rr in grp_rows if rr.fabricante_pai or rr.grupo_pai), r)

                if all_gt_zero:
                    dias_pai = dias_pa
                    site_pai = site_pa
                    msg_pai_text = msg_pa
                else:
                    p = _prazo_fornecedor(base_pai, ItemTipo.PAI)
                    dias_pai = p
                    site_pai = str(p)
                    msg_pai_text = f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)"

                _emit_single(
                    RuleName.NENHUM_GRUPO,
                    ItemTipo.PAI,
                    pai_key,
                    marca=base_pai.fabricante_pai or "",
                    grupo3_origem=_safe_group3(r.nome_grupo3),
                    grupo3=RuleName.OUTLET.value,
                    estoque_seg=0,
                    produto_inativo=None,
                    dias=dias_pai,
                    site=site_pai,
                    msg=f"MOVIDO PARA GRUPO3 OUTLET | {msg_pai_text}",
                )

            continue

        # =========================
        # B) Disponível <=0 (DECISÃO 2A)
        # =========================
        p_pa = _prazo_fornecedor(r, ItemTipo.PA)
        p_kit = _prazo_fornecedor(r, ItemTipo.KIT)
        p_pai = _prazo_fornecedor(r, ItemTipo.PAI)

        _emit_single(
            RuleName.NENHUM_GRUPO,
            ItemTipo.PA,
            r.codbarra_produto or "",
            marca=r.fabricante_produto or "",
            grupo3_origem=_safe_group3(r.nome_grupo3),
            grupo3=None,
            estoque_seg=1000,
            produto_inativo=None,
            dias=p_pa,
            site=str(p_pa),
            msg="INCLUIDO 1000 ESTOQUE SEG",
        )

        if r.codbarra_kit:
            _emit_single(
                RuleName.NENHUM_GRUPO,
                ItemTipo.KIT,
                r.codbarra_kit or "",
                marca=r.fabricante_kit or "",
                grupo3_origem=_safe_group3(r.nome_grupo3),
                grupo3=None,
                estoque_seg=0,
                produto_inativo=None,
                dias=p_kit,
                site=str(p_kit),
                msg=f"PRAZO DEFINIDO {p_kit} DIAS (FORNECEDOR)",
            )

        if r.codbarra_pai:
            _emit_single(
                RuleName.NENHUM_GRUPO,
                ItemTipo.PAI,
                r.codbarra_pai or "",
                marca=r.fabricante_pai or "",
                grupo3_origem=_safe_group3(r.nome_grupo3),
                grupo3=None,
                estoque_seg=0,
                produto_inativo=None,
                dias=p_pai,
                site=str(p_pai),
                msg=f"PRAZO DEFINIDO {p_pai} DIAS (FORNECEDOR)",
            )    #
# ======================================================
    # 5) OUTLET  ✅ CORRIGIDO: KIT ZERADO POR COMPONENTE FUNCIONA
    # ======================================================

    def _is_blank_local(v: Any) -> bool:
        if v is None:
            return True
        s = str(v).strip()
        return (not s) or (s.lower() in ("nan", "none"))

    def _brand_base_days(marca: str) -> int:
        m = norm_upper(marca)
        if m in OUTLET_BRANDS_IMEDIATA:
            return 0
        if m in OUTLET_BRANDS_3_DAYS:
            return 3
        return 1

    def _pick_best_pa_row(rr_list: List[AthosRow]) -> AthosRow:
        def score(r: AthosRow) -> int:
            s = 0
            try:
                if r.estoque_real_produto is not None and str(r.estoque_real_produto).strip() not in ("", "0", "0.0"):
                    s += 100
            except Exception:
                pass
            if getattr(r, "fabricante_produto", None):
                s += 10
            if getattr(r, "codbarra_kit", None):
                s += 3
            if getattr(r, "codbarra_pai", None):
                s += 2
            return s

        best = rr_list[0]
        best_score = score(best)
        for r in rr_list[1:]:
            sc = score(r)
            if sc > best_score:
                best = r
                best_score = sc
        return best

    def _emit_single_outlet(
        r_ref: AthosRow,
        tipo: ItemTipo,
        codbarra: Optional[str],
        *,
        estoque_seg: Optional[int],
        dias: int,
        msg: str,
        allow_locked: bool = False,
    ) -> None:
        if not codbarra:
            return
        if (not allow_locked) and is_locked(codbarra):
            return

        a = AthosAction(rule=RuleName.OUTLET, tipo=tipo, codbarra=codbarra)
        a.estoque_seguranca = estoque_seg

        if dias == 0:
            apply_imediata(a)
        else:
            apply_prazo(a, dias)

        if tipo == ItemTipo.PA:
            a.marca = r_ref.fabricante_produto or ""
        elif tipo == ItemTipo.KIT:
            a.marca = r_ref.fabricante_kit or ""
        else:
            a.marca = r_ref.fabricante_pai or ""

        a.grupo3_origem_pa = RuleName.OUTLET.value
        a.add_msg(msg)
        upsert_action(a)

        if not allow_locked:
            lock(a.codbarra, RuleName.OUTLET)

        report(RuleName.OUTLET, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", msg)

    def _forn_outlet(rr: AthosRow, tipo: ItemTipo) -> int:
        return _prazo_fornecedor(rr, tipo)

    # ---------- MAPAS GLOBAIS (IMPORTANTE): usar "rows", não só outlet_rows ----------
    pa_all_rows: Dict[str, List[AthosRow]] = defaultdict(list)
    kit_all_rows: Dict[str, List[AthosRow]] = defaultdict(list)
    kit_to_pas_all: Dict[str, Set[str]] = defaultdict(set)
    kit_to_row_ref: Dict[str, AthosRow] = {}
    kit_to_pai_resolved: Dict[str, str] = {}
    pai_to_row_ref: Dict[str, AthosRow] = {}

    for r in rows:
        if r.codbarra_produto:
            pa_all_rows[r.codbarra_produto].append(r)

        if r.codbarra_kit:
            kit_all_rows[r.codbarra_kit].append(r)
            kit_to_row_ref.setdefault(r.codbarra_kit, r)
            if r.codbarra_produto:
                kit_to_pas_all[r.codbarra_kit].add(r.codbarra_produto)
            if r.codbarra_pai and r.codbarra_kit not in kit_to_pai_resolved:
                kit_to_pai_resolved[r.codbarra_kit] = r.codbarra_pai

        if r.codbarra_pai:
            pai_to_row_ref.setdefault(r.codbarra_pai, r)

    outlet_rows: List[AthosRow] = [
        r for r in rows
        if grupo3_bucket(r.nome_grupo3) == RuleName.OUTLET.value and r.codbarra_produto
    ]

    if outlet_rows:
        pa_to_rows: Dict[str, List[AthosRow]] = defaultdict(list)
        pa_to_kits: Dict[str, Set[str]] = defaultdict(set)

        for r in outlet_rows:
            pa_to_rows[r.codbarra_produto].append(r)
            if r.codbarra_kit:
                pa_to_kits[r.codbarra_produto].add(r.codbarra_kit)

        # Grupinho por PAI (mantido igual)
        pai_to_grupinho_kits: Dict[str, Set[str]] = defaultdict(set)
        pai_to_grupinho_pas: Dict[str, Set[str]] = defaultdict(set)

        for r in outlet_rows:
            if not r.codbarra_kit:
                continue
            if _is_blank_local(r.grupo_kit):
                continue
            pai_res = kit_to_pai_resolved.get(r.codbarra_kit) or (r.codbarra_pai or "")
            if not pai_res:
                continue
            pai_to_grupinho_kits[pai_res].add(r.codbarra_kit)
            if r.codbarra_produto:
                pai_to_grupinho_pas[pai_res].add(r.codbarra_produto)

        def _emit_bundle_for_pa(
            pa_cod: str,
            *,
            pa_ref: AthosRow,
            estoque_pa: int,
            dias_pa: int,
            msg_pa: str,
            estoque_kit: int,
            dias_kit: int,
            msg_kit: str,
            estoque_pai: int,
            dias_pai: int,
            msg_pai: str,
        ) -> None:
            _emit_single_outlet(pa_ref, ItemTipo.PA, pa_cod, estoque_seg=estoque_pa, dias=dias_pa, msg=msg_pa)

            kits = sorted(pa_to_kits.get(pa_cod, set()))
            for kit_cod in kits:
                kit_ref = kit_to_row_ref.get(kit_cod, pa_ref)
                _emit_single_outlet(
                    kit_ref, ItemTipo.KIT, kit_cod,
                    estoque_seg=estoque_kit,
                    dias=(_forn_outlet(kit_ref, ItemTipo.KIT) if dias_kit == -1 else dias_kit),
                    msg=msg_kit,
                    allow_locked=True,
                )

            pais: Set[str] = set()
            for kit_cod in kits:
                p = kit_to_pai_resolved.get(kit_cod)
                if p:
                    pais.add(p)

            for pai_cod in sorted(pais):
                pai_ref = pai_to_row_ref.get(pai_cod, pa_ref)
                _emit_single_outlet(
                    pai_ref, ItemTipo.PAI, pai_cod,
                    estoque_seg=estoque_pai,
                    dias=(_forn_outlet(pai_ref, ItemTipo.PAI) if dias_pai == -1 else dias_pai),
                    msg=msg_pai,
                    allow_locked=True,
                )

        processed_pas: Set[str] = set()

        # 1) Processa PAI com grupinho (mantido)
        for pai_cod, kits_grup in pai_to_grupinho_kits.items():
            if not kits_grup:
                continue

            any_kit_le_zero = False
            for k in kits_grup:
                rrk = kit_to_row_ref.get(k)
                if rrk and _estoque_kit(rrk) <= 0:
                    any_kit_le_zero = True
                    break

            any_pa_cod = next(iter(pai_to_grupinho_pas.get(pai_cod, set())), None)
            pa_ref_base = (
                _pick_best_pa_row(pa_to_rows[any_pa_cod])
                if any_pa_cod and pa_to_rows.get(any_pa_cod)
                else (pai_to_row_ref.get(pai_cod) or outlet_rows[0])
            )
            base_days = _brand_base_days(pa_ref_base.fabricante_produto or "")

            if any_kit_le_zero:
                for pa_cod_g in sorted(pai_to_grupinho_pas.get(pai_cod, set())):
                    pa_ref2 = _pick_best_pa_row(pa_to_rows[pa_cod_g])
                    ppa = _forn_outlet(pa_ref2, ItemTipo.PA)
                    _emit_bundle_for_pa(
                        pa_cod_g,
                        pa_ref=pa_ref2,
                        estoque_pa=1000,
                        dias_pa=ppa,
                        msg_pa="OUTLET (PA) -> ESTOQUE 1000 + PRAZO FORNECEDOR (KIT<=0 NO GRUPINHO)",
                        estoque_kit=0,
                        dias_kit=-1,
                        msg_kit="OUTLET (KIT) -> ESTOQUE 0 + PRAZO FORNECEDOR (KIT<=0 NO GRUPINHO)",
                        estoque_pai=0,
                        dias_pai=-1,
                        msg_pai="OUTLET (PAI) -> ESTOQUE 0 + PRAZO FORNECEDOR (KIT<=0 NO GRUPINHO)",
                    )
                    processed_pas.add(pa_cod_g)
                continue

            for pa_cod_g in sorted(pai_to_grupinho_pas.get(pai_cod, set())):
                pa_ref2 = _pick_best_pa_row(pa_to_rows[pa_cod_g])
                _emit_bundle_for_pa(
                    pa_cod_g,
                    pa_ref=pa_ref2,
                    estoque_pa=0,
                    dias_pa=base_days,
                    msg_pa=f"OUTLET (PA) -> ESTOQUE 0 + PRAZO {base_days} (TODOS KITS>0 NO GRUPINHO)",
                    estoque_kit=0,
                    dias_kit=base_days,
                    msg_kit=f"OUTLET (KIT) -> ESTOQUE 0 + PRAZO {base_days} (GRUPINHO)",
                    estoque_pai=0,
                    dias_pai=base_days,
                    msg_pai=f"OUTLET (PAI) -> ESTOQUE 0 + PRAZO {base_days} (GRUPINHO)",
                )
                processed_pas.add(pa_cod_g)

        # 2) Restante dos PAs OUTLET
        for pa_cod, rr_list in pa_to_rows.items():
            if pa_cod in processed_pas:
                continue

            rr0 = _pick_best_pa_row(rr_list)
            kits_for_pa = sorted(pa_to_kits.get(pa_cod, set()))
            has_kit = bool(kits_for_pa)

            disp_pa = _estoque_pa(rr0)
            base_days = _brand_base_days(rr0.fabricante_produto or "")

            if not has_kit:
                if disp_pa <= 0:
                    p = _forn_outlet(rr0, ItemTipo.PA)
                    _emit_bundle_for_pa(
                        pa_cod,
                        pa_ref=rr0,
                        estoque_pa=1000,
                        dias_pa=p,
                        msg_pa="OUTLET (PA SEM KIT) -> ESTOQUE 1000 + PRAZO FORNECEDOR",
                        estoque_kit=0,
                        dias_kit=-1,
                        msg_kit="OUTLET (KIT) -> NA (SEM KIT)",
                        estoque_pai=0,
                        dias_pai=-1,
                        msg_pai="OUTLET (PAI) -> NA (SEM PAI)",
                    )
                else:
                    _emit_bundle_for_pa(
                        pa_cod,
                        pa_ref=rr0,
                        estoque_pa=0,
                        dias_pa=base_days,
                        msg_pa=f"OUTLET (PA SEM KIT) -> ESTOQUE 0 + PRAZO {base_days}",
                        estoque_kit=0,
                        dias_kit=base_days,
                        msg_kit="OUTLET (KIT) -> NA (SEM KIT)",
                        estoque_pai=0,
                        dias_pai=base_days,
                        msg_pai="OUTLET (PAI) -> NA (SEM PAI)",
                    )
                continue

            resolved_pais = {kit_to_pai_resolved.get(k) for k in kits_for_pa}
            resolved_pais.discard(None)
            has_pai_resolved = bool(resolved_pais)

            any_kit_le_zero = False
            for kit_cod in kits_for_pa:
                rrk = kit_to_row_ref.get(kit_cod)
                if rrk and _estoque_kit(rrk) <= 0:
                    any_kit_le_zero = True
                    break

            if not has_pai_resolved:
                if any_kit_le_zero:
                    ppa = _forn_outlet(rr0, ItemTipo.PA)
                    _emit_bundle_for_pa(
                        pa_cod,
                        pa_ref=rr0,
                        estoque_pa=1000,
                        dias_pa=ppa,
                        msg_pa="OUTLET (PA COM KIT, SEM PAI) -> ESTOQUE 1000 + PRAZO FORNECEDOR (KIT<=0)",
                        estoque_kit=0,
                        dias_kit=-1,
                        msg_kit="OUTLET (KIT, SEM PAI) -> ESTOQUE 0 + PRAZO FORNECEDOR (KIT<=0)",
                        estoque_pai=0,
                        dias_pai=-1,
                        msg_pai="OUTLET (PAI) -> NA (SEM PAI)",
                    )
                else:
                    _emit_bundle_for_pa(
                        pa_cod,
                        pa_ref=rr0,
                        estoque_pa=0,
                        dias_pa=0,
                        msg_pa="OUTLET (PA COM KIT, SEM PAI) -> ESTOQUE 0 + IMEDIATA (TODOS KITS>0)",
                        estoque_kit=0,
                        dias_kit=0,
                        msg_kit="OUTLET (KIT, SEM PAI) -> ESTOQUE 0 + IMEDIATA (MESMO DO PA)",
                        estoque_pai=0,
                        dias_pai=0,
                        msg_pai="OUTLET (PAI) -> NA (SEM PAI)",
                    )
                continue

            # ---- PA com KIT e COM PAI
            if disp_pa <= 0:
                ppa = _forn_outlet(rr0, ItemTipo.PA)
                _emit_bundle_for_pa(
                    pa_cod,
                    pa_ref=rr0,
                    estoque_pa=1000,
                    dias_pa=ppa,
                    msg_pa="OUTLET (PA COM PAI) -> ESTOQUE 1000 + PRAZO FORNECEDOR (PA<=0)",
                    estoque_kit=0,
                    dias_kit=-1,
                    msg_kit="OUTLET (KIT COM PAI) -> ESTOQUE 0 + PRAZO FORNECEDOR (PA<=0)",
                    estoque_pai=0,
                    dias_pai=-1,
                    msg_pai="OUTLET (PAI) -> ESTOQUE 0 + PRAZO FORNECEDOR (PA<=0)",
                )
                continue

            # ✅ KIT ZERADO POR COMPONENTE (CORRIGIDO)
            kit_efetivo_zerado = False
            for kit_cod in kits_for_pa:
                pas_do_kit = kit_to_pas_all.get(kit_cod, set())
                for pa_comp in pas_do_kit:
                    if pa_comp not in pa_all_rows:
                        continue
                    rr_comp = _pick_best_pa_row(pa_all_rows[pa_comp])
                    if _estoque_pa(rr_comp) <= 0:
                        kit_efetivo_zerado = True
                        break
                if kit_efetivo_zerado:
                    break

            if kit_efetivo_zerado:
                # 1) Emitir TODOS os PAs componentes com fornecedor:
                for kit_cod in kits_for_pa:
                    for pa_comp in kit_to_pas_all.get(kit_cod, set()):
                        if pa_comp not in pa_all_rows:
                            continue
                        rr_comp = _pick_best_pa_row(pa_all_rows[pa_comp])
                        p_comp = _forn_outlet(rr_comp, ItemTipo.PA)
                        if _estoque_pa(rr_comp) <= 0:
                            _emit_single_outlet(
                                rr_comp, ItemTipo.PA, pa_comp,
                                estoque_seg=1000,
                                dias=p_comp,
                                msg="OUTLET (PA COMPONENTE ZERADO) -> ESTOQUE 1000 + PRAZO FORNECEDOR",
                                allow_locked=True,
                            )
                        else:
                            _emit_single_outlet(
                                rr_comp, ItemTipo.PA, pa_comp,
                                estoque_seg=0,
                                dias=p_comp,
                                msg="OUTLET (PA COMPONENTE OK) -> ESTOQUE 0 + PRAZO FORNECEDOR (KIT ZERADO POR COMPONENTE)",
                                allow_locked=True,
                            )

                # 2) KITS com fornecedor
                for kit_cod in kits_for_pa:
                    kit_ref = kit_to_row_ref.get(kit_cod, rr0)
                    _emit_single_outlet(
                        kit_ref, ItemTipo.KIT, kit_cod,
                        estoque_seg=0,
                        dias=_forn_outlet(kit_ref, ItemTipo.KIT),
                        msg="OUTLET (KIT) -> ESTOQUE 0 + PRAZO FORNECEDOR (KIT ZERADO POR COMPONENTE)",
                        allow_locked=True,
                    )

                # 3) PAI com fornecedor
                for pai_cod_res in sorted(resolved_pais):
                    pai_ref = pai_to_row_ref.get(pai_cod_res, rr0)
                    _emit_single_outlet(
                        pai_ref, ItemTipo.PAI, pai_cod_res,
                        estoque_seg=0,
                        dias=_forn_outlet(pai_ref, ItemTipo.PAI),
                        msg="OUTLET (PAI) -> ESTOQUE 0 + PRAZO FORNECEDOR (KIT ZERADO POR COMPONENTE)",
                        allow_locked=True,
                    )
                continue

            # caso normal (sem kit efetivo zerado) -> mantém sua regra de base_days + pai condicional
            # (mantido como você já tinha)
            todos_pa_filhos_gt_zero = True
            for pai_cod_check in sorted(resolved_pais):
                pas_deste_pai: Set[str] = set()
                for other_pa, other_kits in pa_to_kits.items():
                    for ok in other_kits:
                        if kit_to_pai_resolved.get(ok) == pai_cod_check:
                            pas_deste_pai.add(other_pa)
                for other_pa_cod in pas_deste_pai:
                    other_rr0 = _pick_best_pa_row(pa_to_rows[other_pa_cod])
                    if _estoque_pa(other_rr0) <= 0:
                        todos_pa_filhos_gt_zero = False
                        break
                if not todos_pa_filhos_gt_zero:
                    break

            if todos_pa_filhos_gt_zero:
                dias_pai_final = base_days
                msg_pai_final = f"OUTLET (PAI) -> ESTOQUE 0 + PRAZO {base_days} (PADRÃO POR MARCA)"
            else:
                dias_pai_final = -1
                msg_pai_final = "OUTLET (PAI) -> ESTOQUE 0 + PRAZO FORNECEDOR (ALGUM PA FILHO <= 0)"

            _emit_bundle_for_pa(
                pa_cod,
                pa_ref=rr0,
                estoque_pa=0,
                dias_pa=base_days,
                msg_pa=f"OUTLET (PA) -> ESTOQUE 0 + PRAZO {base_days}",
                estoque_kit=0,
                dias_kit=base_days,
                msg_kit=f"OUTLET (KIT) -> ESTOQUE 0 + PRAZO {base_days} (MESMO DO PA)",
                estoque_pai=0,
                dias_pai=dias_pai_final,
                msg_pai=msg_pai_final,
            )

    # ======================================================
    # Finalização
    # ======================================================
    final_actions_by_rule: Dict[RuleName, List[AthosAction]] = {}
    for rn in ORDERED_RULES:
        final_actions_by_rule[rn] = list(actions_by_rule[rn].values())

    return AthosOutputs(
        actions_by_rule=final_actions_by_rule,
        report_lines=report_lines,
    )