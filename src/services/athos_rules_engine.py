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

# Marcas com comportamento especial no OUTLET
OUTLET_BRANDS_3_DAYS = {"DMOV", "DMOV2"}
OUTLET_BRANDS_IMEDIATA = {"KONFORT", "CASA DO PUFF", "DIVINI DECOR"}

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

        # ✅ novo header do SQL
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

    # ======================================================
    # ✅ ESTOQUE DE DECISÃO (regra do projeto)
    # Se o KIT se repete (mesmo CODBARRA_KIT em múltiplas linhas),
    # NÃO usar estoque do PA; usar ESTOQUE_REAL_KIT (cálculo final do kit).
    # ======================================================
    kit_counts = Counter([r.codbarra_kit for r in rows if r.codbarra_kit])

    def _estoque_decisao(r: AthosRow) -> float:
        if r.codbarra_kit and kit_counts.get(r.codbarra_kit, 0) > 1:
            try:
                return float(r.estoque_real_kit or 0)
            except Exception:
                return float(r.estoque_real_produto or 0)
        return float(r.estoque_real_produto or 0)

    # ✅ prioridade: GRUPO_* do item -> DB fornecedor -> PRAZO_*
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

    # ✅ normaliza ação para consistência: dias==0 -> "Imediata"
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

        # ✅ normaliza também o existente depois de mesclar (blindagem total)
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
    ) -> None:
        g3_pa = _safe_group3(r.nome_grupo3)

        # ✅ normaliza site/prazo
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

        if include_pa and r.codbarra_produto and not is_locked(r.codbarra_produto):
            a = AthosAction(rule=rule, tipo=ItemTipo.PA, codbarra=r.codbarra_produto)
            a.grupo3 = grupo3
            a.produto_inativo = produto_inativo
            a.dias_entrega = dias_entrega
            a.site_disponibilidade = final_site
            a.estoque_seguranca = estoque_pa
            a.marca = r.fabricante_produto or ""
            a.grupo3_origem_pa = g3_pa
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
            if final_msg_pai:
                a.add_msg(final_msg_pai)
                report(rule, a.codbarra, a.tipo, a.marca or "", g3_pa, final_msg_pai)
            upsert_action(a)
            lock(a.codbarra, rule)

    # ======================================================
    # 1) FORA DE LINHA
    # ======================================================
    for r in rows:
        g3 = grupo3_bucket(r.nome_grupo3)
        if g3 != RuleName.FORA_DE_LINHA.value:
            continue
        if _estoque_decisao(r) <= 0 and r.codbarra_produto:
            emit_for_pa_kit_pai(
                RuleName.FORA_DE_LINHA,
                r,
                produto_inativo="T",
                msg_pa="PRODUTO INATIVADO",
                msg_kit="PRODUTO INATIVADO",
                msg_pai="PRODUTO INATIVADO",
            )

    # ======================================================
    # 2) ESTOQUE COMPARTILHADO
    # - KIT herda prazo do PA
    # - PAI pega o maior prazo dos KITS do mesmo pai
    # ======================================================
    for pai_key, group_rows in by_pai.items():
        esc_rows = [r for r in group_rows if grupo3_bucket(r.nome_grupo3) == RuleName.ESTOQUE_COMPARTILHADO.value]
        if not esc_rows:
            continue

        kit_prazos: List[int] = []
        for r in esc_rows:
            if not r.codbarra_kit or is_locked(r.codbarra_kit):
                continue

            # prazo do PA (pode ser "IMEDIATA" ou número)
            if is_imediata(r.prazo_produto):
                a = AthosAction(rule=RuleName.ESTOQUE_COMPARTILHADO, tipo=ItemTipo.KIT, codbarra=r.codbarra_kit)
                apply_imediata(a)  # já vira "Imediata" via models + normalize
                a.marca = r.fabricante_kit or ""
                a.grupo3_origem_pa = _safe_group3(r.nome_grupo3)
                a.add_msg("PRAZO HERDADO DO PA (Imediata)")
                upsert_action(a)
                lock(a.codbarra, RuleName.ESTOQUE_COMPARTILHADO)
                report(
                    RuleName.ESTOQUE_COMPARTILHADO,
                    a.codbarra,
                    a.tipo,
                    a.marca or "",
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
                a.codbarra,
                a.tipo,
                a.marca or "",
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
                a.codbarra,
                a.tipo,
                a.marca or "",
                a.grupo3_origem_pa or "",
                f"MAIOR PRAZO DOS KITS: {maior} DIAS",
            )

    # ======================================================
    # 3) ENVIO IMEDIATO
    # ======================================================
    # 3.1) remover do grupo3 quem não está na whitelist
    for r in rows:
        if grupo3_bucket(r.nome_grupo3) != RuleName.ENVIO_IMEDIATO.value:
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
                a.codbarra,
                a.tipo,
                a.marca or "",
                a.grupo3_origem_pa or "",
                "RETIRADO DO GRUPO3 ENVIO IMEDIATO",
            )

    # 3.2) regra especial só relatório
    for pai_key, group_rows in by_pai.items():
        grp = [r for r in group_rows if grupo3_bucket(r.nome_grupo3) == RuleName.ENVIO_IMEDIATO.value and r.codbarra_produto]
        if not grp:
            continue

        special_pas = [r for r in grp if norm_upper(r.fabricante_produto) in SPECIAL_IMEDIATO_BRANDS]
        if not special_pas:
            continue

        all_le_zero = all(_estoque_decisao(rr) <= 0 for rr in grp)
        if not all_le_zero:
            continue

        # bloqueia tudo (PA/KIT/PAI)
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
        grp = [
            r for r in group_rows
            if grupo3_bucket(r.nome_grupo3) == RuleName.ENVIO_IMEDIATO.value
            and r.codbarra_produto
            and r.codbarra_produto in whitelist_imediatos
        ]
        if not grp:
            continue

        stocks = {r.codbarra_produto: _estoque_decisao(r) for r in grp if r.codbarra_produto}
        all_gt_zero = bool(stocks) and all(v > 0 for v in stocks.values())
        all_le_zero = bool(stocks) and all(v <= 0 for v in stocks.values())

        marca_group = norm_upper(grp[0].fabricante_produto)

        def set_pai(*, dias: int, site: str, msg: str) -> None:
            if pai_key != "__SEM_PAI__" and not is_locked(pai_key):
                a = AthosAction(rule=RuleName.ENVIO_IMEDIATO, tipo=ItemTipo.PAI, codbarra=pai_key)
                a.dias_entrega = dias
                a.site_disponibilidade = IMEDIATA_TEXT if dias == 0 else site
                a.estoque_seguranca = 0
                a.marca = grp[0].fabricante_pai or ""
                a.grupo3_origem_pa = RuleName.ENVIO_IMEDIATO.value
                a.add_msg(IMEDIATA_TEXT if msg.strip().lower() == "imediata" else msg)
                upsert_action(a)
                lock(a.codbarra, RuleName.ENVIO_IMEDIATO)
                report(RuleName.ENVIO_IMEDIATO, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", a.mensagens[-1])

        # DMOV2
        if marca_group == "DMOV2":
            for r in grp:
                disp = _estoque_decisao(r)
                if disp > 0:
                    emit_for_pa_kit_pai(
                        RuleName.ENVIO_IMEDIATO, r,
                        estoque_pa=1000, estoque_kit=0, estoque_pai=0,
                        dias_entrega=3, site_disp="3",
                        msg_pa="INCLUIDO 1000 ESTOQUE SEG",
                        msg_kit="PRAZO DEFINIDO 3 DIAS",
                    )
                else:
                    p = _prazo_fornecedor(r, ItemTipo.PA)
                    emit_for_pa_kit_pai(
                        RuleName.ENVIO_IMEDIATO, r,
                        estoque_pa=0, estoque_kit=0, estoque_pai=0,
                        dias_entrega=p, site_disp=str(p),
                        msg_pa=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                        msg_kit=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                    )

            if pai_key != "__SEM_PAI__":
                if all_gt_zero:
                    set_pai(dias=3, site="3", msg="PRAZO DEFINIDO 3 DIAS")
                else:
                    pmax = max((_prazo_fornecedor(r, ItemTipo.PA) for r in grp), default=0)
                    set_pai(dias=pmax, site=str(pmax), msg=f"PRAZO DEFINIDO {pmax} DIAS (FORNECEDOR)")
            continue

        # Imediata brands
        if marca_group in IMEDIATA_BRANDS:
            if all_gt_zero:
                for r in grp:
                    emit_for_pa_kit_pai(
                        RuleName.ENVIO_IMEDIATO, r,
                        estoque_pa=0, estoque_kit=0, estoque_pai=0,
                        dias_entrega=0, site_disp=IMEDIATA_TEXT,
                        msg_pa=IMEDIATA_TEXT,
                        msg_kit=IMEDIATA_TEXT,
                    )
                set_pai(dias=0, site=IMEDIATA_TEXT, msg=IMEDIATA_TEXT)
            elif all_le_zero:
                for r in grp:
                    p = _prazo_fornecedor(r, ItemTipo.PA)
                    emit_for_pa_kit_pai(
                        RuleName.ENVIO_IMEDIATO, r,
                        estoque_pa=1000, estoque_kit=0, estoque_pai=0,
                        dias_entrega=p, site_disp=str(p),
                        msg_pa="INCLUIDO 1000 ESTOQUE SEG",
                        msg_kit=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                    )
                pmax = max((_prazo_fornecedor(r, ItemTipo.PA) for r in grp), default=0)
                set_pai(dias=pmax, site=str(pmax), msg=f"PRAZO DEFINIDO {pmax} DIAS (FORNECEDOR)")
            else:
                # misto: quem tem estoque vira imediata, quem não tem -> fornecedor, pai vira imediata
                for r in grp:
                    disp = _estoque_decisao(r)
                    if disp <= 0:
                        p = _prazo_fornecedor(r, ItemTipo.PA)
                        emit_for_pa_kit_pai(
                            RuleName.ENVIO_IMEDIATO, r,
                            estoque_pa=0, estoque_kit=0, estoque_pai=0,
                            dias_entrega=p, site_disp=str(p),
                            msg_pa=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                            msg_kit=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                        )
                    else:
                        emit_for_pa_kit_pai(
                            RuleName.ENVIO_IMEDIATO, r,
                            estoque_pa=0, estoque_kit=0, estoque_pai=0,
                            dias_entrega=0, site_disp=IMEDIATA_TEXT,
                            msg_pa=IMEDIATA_TEXT,
                            msg_kit=IMEDIATA_TEXT,
                        )
                set_pai(dias=0, site=IMEDIATA_TEXT, msg=IMEDIATA_TEXT)
            continue

        # Outras marcas (1 dia quando tem estoque)
        if all_gt_zero:
            for r in grp:
                emit_for_pa_kit_pai(
                    RuleName.ENVIO_IMEDIATO, r,
                    estoque_pa=0, estoque_kit=0, estoque_pai=0,
                    dias_entrega=1, site_disp="1",
                    msg_pa="PRAZO DEFINIDO 1 DIA",
                    msg_kit="PRAZO DEFINIDO 1 DIA",
                )
            set_pai(dias=1, site="1", msg="PRAZO DEFINIDO 1 DIA")
        elif all_le_zero:
            for r in grp:
                p = _prazo_fornecedor(r, ItemTipo.PA)
                emit_for_pa_kit_pai(
                    RuleName.ENVIO_IMEDIATO, r,
                    estoque_pa=1000, estoque_kit=0, estoque_pai=0,
                    dias_entrega=p, site_disp=str(p),
                    msg_pa="INCLUIDO 1000 ESTOQUE SEG",
                    msg_kit=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                )
            pmax = max((_prazo_fornecedor(r, ItemTipo.PA) for r in grp), default=0)
            set_pai(dias=pmax, site=str(pmax), msg=f"PRAZO DEFINIDO {pmax} DIAS (FORNECEDOR)")
        else:
            for r in grp:
                disp = _estoque_decisao(r)
                if disp <= 0:
                    p = _prazo_fornecedor(r, ItemTipo.PA)
                    emit_for_pa_kit_pai(
                        RuleName.ENVIO_IMEDIATO, r,
                        estoque_pa=0, estoque_kit=0, estoque_pai=0,
                        dias_entrega=p, site_disp=str(p),
                        msg_pa=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                        msg_kit=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                    )
                else:
                    emit_for_pa_kit_pai(
                        RuleName.ENVIO_IMEDIATO, r,
                        estoque_pa=0, estoque_kit=0, estoque_pai=0,
                        dias_entrega=1, site_disp="1",
                        msg_pa="PRAZO DEFINIDO 1 DIA",
                        msg_kit="PRAZO DEFINIDO 1 DIA",
                    )
            set_pai(dias=1, site="1", msg="PRAZO DEFINIDO 1 DIA")

    # ======================================================
    # 4) NENHUM GRUPO
    # Regra ajustada:
    # - Só entra aqui se NOME_GRUPO3 estiver vazio
    # - E também NÃO existir nenhum GRUPO_* (mesmo em texto)
    #   (ex: "2 Lugares" já conta como grupo => NÃO é sem grupo)
    # ======================================================

    def _has_any_grupo_text(r: AthosRow) -> bool:
        return any(
            (str(v).strip() != "" and str(v).strip().lower() not in ("nan", "none"))
            for v in (r.grupo_produto, r.grupo_kit, r.grupo_pai)
            if v is not None
        )

    for r in rows:
        # ✅ se tem grupo3 (nome_grupo3), não é SEM_GRUPO
        if grupo3_bucket(r.nome_grupo3) is not None:
            continue

        # ✅ NOVO: se já existe qualquer GRUPO_* preenchido (mesmo texto), também NÃO é SEM_GRUPO
        if _has_any_grupo_text(r):
            continue

        if not r.codbarra_produto:
            continue
        if not (r.fabricante_produto or "").strip():
            continue
        if norm_upper(r.fabricante_produto) in IGNORE_SEM_GRUPO_BRANDS:
            continue
        if is_locked(r.codbarra_produto):
            continue

        disp = _estoque_decisao(r)

        if disp > 0:
            if r.codbarra_produto in whitelist_imediatos:
                emit_for_pa_kit_pai(
                    RuleName.NENHUM_GRUPO, r,
                    grupo3=RuleName.ENVIO_IMEDIATO.value,
                    estoque_pa=0, estoque_kit=0, estoque_pai=0,
                    dias_entrega=1, site_disp="1",
                    msg_pa="MOVIDO PARA GRUPO3 ENVIO IMEDIATO",
                    msg_kit="MOVIDO PARA GRUPO3 ENVIO IMEDIATO",
                    msg_pai="MOVIDO PARA GRUPO3 ENVIO IMEDIATO",
                )
            else:
                emit_for_pa_kit_pai(
                    RuleName.NENHUM_GRUPO, r,
                    grupo3=RuleName.OUTLET.value,
                    estoque_pa=0, estoque_kit=0, estoque_pai=0,
                    dias_entrega=1, site_disp="1",
                    msg_pa="MOVIDO PARA GRUPO3 OUTLET",
                    msg_kit="MOVIDO PARA GRUPO3 OUTLET",
                    msg_pai="MOVIDO PARA GRUPO3 OUTLET",
                )
        else:
            p = _prazo_fornecedor(r, ItemTipo.PA)
            emit_for_pa_kit_pai(
                RuleName.NENHUM_GRUPO, r,
                estoque_pa=1000, estoque_kit=0, estoque_pai=0,
                dias_entrega=p, site_disp=str(p),
                msg_pa="INCLUIDO 1000 ESTOQUE SEG",
                msg_kit=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                msg_pai=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
            )

    # ======================================================
    # 5) OUTLET
    # ======================================================
    for pai_key, group_rows in by_pai.items():
        grp = [r for r in group_rows if grupo3_bucket(r.nome_grupo3) == RuleName.OUTLET.value and r.codbarra_produto]
        if not grp:
            continue

        # marca do grupo (PA)
        marca_group = norm_upper(grp[0].fabricante_produto)
        stocks = {r.codbarra_produto: _estoque_decisao(r) for r in grp if r.codbarra_produto}

        all_gt_zero = bool(stocks) and all(v > 0 for v in stocks.values())
        any_le_zero = bool(stocks) and any(v <= 0 for v in stocks.values())

        def set_pai_outlet(*, dias: int, site: str, msg: str) -> None:
            if pai_key != "__SEM_PAI__" and not is_locked(pai_key):
                a = AthosAction(rule=RuleName.OUTLET, tipo=ItemTipo.PAI, codbarra=pai_key)
                a.dias_entrega = dias
                a.site_disponibilidade = IMEDIATA_TEXT if dias == 0 else site
                a.estoque_seguranca = 0
                a.marca = grp[0].fabricante_pai or ""
                a.grupo3_origem_pa = RuleName.OUTLET.value
                a.add_msg(IMEDIATA_TEXT if msg.strip().lower() == "imediata" else msg)
                upsert_action(a)
                lock(a.codbarra, RuleName.OUTLET)
                report(RuleName.OUTLET, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", a.mensagens[-1])

        # Cenário A: PA sem estoque -> PA=1000 / KIT=0 / PAI=0, prazo fornecedor
        # (aplicado por linha)
        for r in grp:
            disp = _estoque_decisao(r)
            if disp <= 0:
                p = _prazo_fornecedor(r, ItemTipo.PA)
                emit_for_pa_kit_pai(
                    RuleName.OUTLET, r,
                    estoque_pa=1000, estoque_kit=0, estoque_pai=0,
                    dias_entrega=p, site_disp=str(p),
                    msg_pa="INCLUIDO 1000 ESTOQUE SEG",
                    msg_kit="INCLUIDO 0 ESTOQUE SEGURANÇA",
                    msg_pai=None,
                    include_pai=False,  # pai definido abaixo (por grupo)
                )
            else:
                # tem estoque: define por marca
                if marca_group in OUTLET_BRANDS_IMEDIATA:
                    emit_for_pa_kit_pai(
                        RuleName.OUTLET, r,
                        estoque_pa=0, estoque_kit=0, estoque_pai=0,
                        dias_entrega=0, site_disp=IMEDIATA_TEXT,
                        msg_pa=IMEDIATA_TEXT,
                        msg_kit=IMEDIATA_TEXT,
                        msg_pai=None,
                        include_pai=False,
                    )
                elif marca_group in OUTLET_BRANDS_3_DAYS:
                    emit_for_pa_kit_pai(
                        RuleName.OUTLET, r,
                        estoque_pa=0, estoque_kit=0, estoque_pai=0,
                        dias_entrega=3, site_disp="3",
                        msg_pa="PRAZO DEFINIDO 3 DIAS",
                        msg_kit="PRAZO DEFINIDO 3 DIAS",
                        msg_pai=None,
                        include_pai=False,
                    )
                else:
                    emit_for_pa_kit_pai(
                        RuleName.OUTLET, r,
                        estoque_pa=0, estoque_kit=0, estoque_pai=0,
                        dias_entrega=1, site_disp="1",
                        msg_pa="PRAZO DEFINIDO 1 DIA",
                        msg_kit="PRAZO DEFINIDO 1 DIA",
                        msg_pai=None,
                        include_pai=False,
                    )

        # Pai: se todos PA > 0 -> prazo padrão da marca; se algum <=0 -> prazo fornecedor do pai (GRUPO_PAI > DB)
        if pai_key != "__SEM_PAI__":
            if all_gt_zero:
                if marca_group in OUTLET_BRANDS_IMEDIATA:
                    set_pai_outlet(dias=0, site=IMEDIATA_TEXT, msg=IMEDIATA_TEXT)
                elif marca_group in OUTLET_BRANDS_3_DAYS:
                    set_pai_outlet(dias=3, site="3", msg="PRAZO DEFINIDO 3 DIAS")
                else:
                    set_pai_outlet(dias=1, site="1", msg="PRAZO DEFINIDO 1 DIA")
            elif any_le_zero:
                # prazo do fornecedor (prioriza GRUPO_PAI; se vazio, DB marca do pai)
                p_pai = max((_prazo_fornecedor(r, ItemTipo.PAI) for r in grp), default=0)
                set_pai_outlet(dias=p_pai, site=str(p_pai), msg=f"PRAZO DEFINIDO {p_pai} DIAS (FORNECEDOR)")

    # finalizar
    final_actions_by_rule: Dict[RuleName, List[AthosAction]] = {}
    for rn in ORDERED_RULES:
        final_actions_by_rule[rn] = list(actions_by_rule[rn].values())

    return AthosOutputs(actions_by_rule=final_actions_by_rule, report_lines=report_lines)