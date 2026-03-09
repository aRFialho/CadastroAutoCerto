from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set
from collections import defaultdict, Counter

from ..athos_models import (
    AthosAction,
    AthosReportLine,
    AthosRow,
    ItemTipo,
    RuleName,
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

# DROSSI tratado como DMOV (3 dias quando disponível > 0)
OUTLET_BRANDS_3_DAYS = {"DMOV", "DMOV2", "DROSSI"}
OUTLET_BRANDS_IMEDIATA = {"KONFORT", "CASA DO PUFF", "DIVINI DECOR"}

# Marcas DMOV para ENVIO IMEDIATO (inclui DROSSI)
DMOV_BRANDS = {"DMOV2", "DROSSI"}

# Ignorar no "Sem Grupo"
IGNORE_SEM_GRUPO_BRANDS = {"DMOV - MP"}

# Padrão único do sistema
IMEDIATA_TEXT = "Imediata"


def to_float(v: Any) -> Optional[float]:
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


def to_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def safe_group3(g3: Optional[str]) -> str:
    return (g3 or "").strip()


def to_row(d: Dict[str, Any]) -> AthosRow:
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
        estoque_real_produto=to_float(g("ESTOQUE_REAL_PRODUTO")),
        prazo_produto=g("PRAZO_PRODUTO"),
        fabricante_produto=to_str(g("FABRICANTE_PRODUTO")),
        nome_grupo3=to_str(g("NOME_GRUPO3")),
        grupo_produto=to_str(g("GRUPO_PRODUTO")),
        codbarra_kit=normalize_ean(g("CODBARRA_KIT")),
        estoque_real_kit=to_float(g("ESTOQUE_REAL_KIT")),
        prazo_kit=g("PRAZO_KIT"),
        fabricante_kit=to_str(g("FABRICANTE_KIT")),
        grupo_kit=to_str(g("GRUPO_KIT")),
        codbarra_pai=normalize_ean(g("CODBARRA_PAI")),
        prazo_pai=g("PRAZO_PAI"),
        fabricante_pai=to_str(g("FABRICANTE_PAI")),
        grupo_pai=to_str(g("GRUPO_PAI")),
    )


@dataclass
class RuleContext:
    rows: List[AthosRow]
    whitelist_imediatos: Set[str]
    supplier_prazo_lookup: Optional[Callable[[str], Optional[int]]] = None

    def __post_init__(self) -> None:
        self.by_pai: Dict[str, List[AthosRow]] = defaultdict(list)
        for r in self.rows:
            pai = r.codbarra_pai or "__SEM_PAI__"
            self.by_pai[pai].append(r)

        self.locked_by: Dict[str, RuleName] = {}
        self.blocked_codbar: Set[str] = set()
        self.actions_by_rule: Dict[RuleName, Dict[str, AthosAction]] = {
            RuleName.FORA_DE_LINHA: {},
            RuleName.ESTOQUE_COMPARTILHADO: {},
            RuleName.ENVIO_IMEDIATO: {},
            RuleName.NENHUM_GRUPO: {},
            RuleName.OUTLET: {},
        }
        self.report_lines: List[AthosReportLine] = []
        self.kit_counts = Counter([r.codbarra_kit for r in self.rows if r.codbarra_kit])

    def lock(self, ean: str, rule: RuleName) -> None:
        self.locked_by[ean] = rule

    def is_locked(self, ean: str) -> bool:
        return ean in self.locked_by or ean in self.blocked_codbar

    def estoque_pa(self, r: AthosRow) -> float:
        return float(r.estoque_real_produto or 0)

    def estoque_kit(self, r: AthosRow) -> float:
        return float(r.estoque_real_kit or 0)

    def estoque_decisao(self, r: AthosRow) -> float:
        if r.codbarra_kit and self.kit_counts.get(r.codbarra_kit, 0) > 1:
            try:
                return float(r.estoque_real_kit or 0)
            except Exception:
                return float(r.estoque_real_produto or 0)
        return float(r.estoque_real_produto or 0)

    def prazo_fornecedor(self, r: AthosRow, which: ItemTipo) -> int:
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
        if self.supplier_prazo_lookup and m:
            try:
                db_p = self.supplier_prazo_lookup(m)
                if db_p is not None:
                    return int(db_p)
            except Exception:
                pass

        p2 = parse_int_safe(prazo_fallback)
        if p2 is not None:
            return int(p2)
        return 0

    def normalize_action(self, a: AthosAction) -> None:
        if a.dias_entrega == 0:
            a.site_disponibilidade = IMEDIATA_TEXT
        if a.site_disponibilidade is not None:
            s = str(a.site_disponibilidade).strip()
            if s.lower() == "imediata" or s.upper() == "IMEDIATA":
                a.site_disponibilidade = IMEDIATA_TEXT

    def upsert_action(self, action: AthosAction) -> None:
        self.normalize_action(action)
        bucket = self.actions_by_rule[action.rule]
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

        self.normalize_action(existing)
        if not existing.marca and action.marca:
            existing.marca = action.marca
        if not existing.grupo3_origem_pa and action.grupo3_origem_pa:
            existing.grupo3_origem_pa = action.grupo3_origem_pa
        for m in action.mensagens:
            if m not in existing.mensagens:
                existing.mensagens.append(m)

    def report(self, rule: RuleName, codbarra: str, tipo: ItemTipo, marca: str, grupo3: str, acao: str) -> None:
        self.report_lines.append(
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
        self,
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
        g3_pa = safe_group3(r.nome_grupo3)
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

        if include_pa and r.codbarra_produto and not self.is_locked(r.codbarra_produto):
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
                self.report(rule, a.codbarra, a.tipo, a.marca or "", g3_pa, final_msg_pa)
            self.upsert_action(a)
            self.lock(a.codbarra, rule)

        if include_kit and r.codbarra_kit and not self.is_locked(r.codbarra_kit):
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
                self.report(rule, a.codbarra, a.tipo, a.marca or "", g3_pa, final_msg_kit)
            self.upsert_action(a)
            self.lock(a.codbarra, rule)

        if include_pai and r.codbarra_pai and not self.is_locked(r.codbarra_pai):
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
                self.report(rule, a.codbarra, a.tipo, a.marca or "", g3_pa, final_msg_pai)
            self.upsert_action(a)
            self.lock(a.codbarra, rule)
