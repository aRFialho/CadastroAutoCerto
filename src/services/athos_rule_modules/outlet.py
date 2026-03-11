from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .base import (
    AthosAction,
    ItemTipo,
    OUTLET_BRANDS_3_DAYS,
    OUTLET_BRANDS_IMEDIATA,
    RuleContext,
    RuleName,
    apply_imediata,
    apply_prazo,
    grupo3_bucket,
    norm_upper,
)


@dataclass
class OutletDecision:
    estoque_seg: Optional[int]
    dias: int
    msg: str
    source: str
    overrides: List[str] = field(default_factory=list)

    def label(self) -> str:
        if self.dias == 0:
            return "IMEDIATA"
        return f"PRAZO {self.dias}"

    def add_override(self, reason: str) -> None:
        if reason not in self.overrides:
            self.overrides.append(reason)

    def final_message(self, prefix: str) -> str:
        parts = [f"OUTLET ({prefix}) -> ESTOQUE {self.estoque_seg} + {self.label()}"]
        if self.source:
            parts.append(f"[{self.source}]")
        if self.overrides:
            parts.append(" | OVERRIDE: " + " | ".join(self.overrides))
        if self.msg:
            parts.append(f" | {self.msg}")
        return "".join(parts)


def apply(ctx: RuleContext) -> None:
    def is_blank(v: Any) -> bool:
        if v is None:
            return True
        s = str(v).strip()
        return (not s) or (s.lower() in ("nan", "none"))

    def brand_base_days(marca: str) -> int:
        m = norm_upper(marca)
        if m in OUTLET_BRANDS_IMEDIATA:
            return 0
        if m in OUTLET_BRANDS_3_DAYS:
            return 3
        return 1

    def pick_best_pa_row(rr_list: List) -> any:
        def score(r) -> int:
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

    def forn_outlet(rr, tipo: ItemTipo) -> int:
        return ctx.prazo_fornecedor(rr, tipo)

    def emit_single_outlet(
        r_ref,
        tipo: ItemTipo,
        codbarra: Optional[str],
        *,
        decision: OutletDecision,
        allow_locked: bool = False,
    ) -> None:
        if not codbarra:
            return
        if (not allow_locked) and ctx.is_locked(codbarra):
            return

        a = AthosAction(rule=RuleName.OUTLET, tipo=tipo, codbarra=codbarra)
        a.estoque_seguranca = decision.estoque_seg
        if decision.dias == 0:
            apply_imediata(a)
        else:
            apply_prazo(a, decision.dias)

        if tipo == ItemTipo.PA:
            a.marca = r_ref.fabricante_produto or ""
        elif tipo == ItemTipo.KIT:
            a.marca = r_ref.fabricante_kit or ""
        else:
            a.marca = r_ref.fabricante_pai or ""

        a.grupo3_origem_pa = RuleName.OUTLET.value
        msg = decision.final_message(tipo.value)
        a.add_msg(msg)
        ctx.upsert_action(a)
        if not allow_locked:
            ctx.lock(a.codbarra, RuleName.OUTLET)
        ctx.report(RuleName.OUTLET, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", msg)

    # Índices globais para leitura das complementares
    pa_all_rows: Dict[str, List] = defaultdict(list)
    kit_all_rows: Dict[str, List] = defaultdict(list)
    kit_to_pas_all: Dict[str, Set[str]] = defaultdict(set)
    for r in ctx.rows:
        if r.codbarra_produto:
            pa_all_rows[r.codbarra_produto].append(r)
        if r.codbarra_kit:
            kit_all_rows[r.codbarra_kit].append(r)
            if r.codbarra_produto:
                kit_to_pas_all[r.codbarra_kit].add(r.codbarra_produto)

    # Recorte estrito: só OUTLET
    outlet_rows = [r for r in ctx.rows if grupo3_bucket(r.nome_grupo3) == RuleName.OUTLET.value and r.codbarra_produto]
    if not outlet_rows:
        return

    pa_to_rows: Dict[str, List] = defaultdict(list)
    pa_to_kits: Dict[str, Set[str]] = defaultdict(set)
    kit_to_row_ref: Dict[str, any] = {}
    kit_to_pai_resolved: Dict[str, str] = {}
    pai_to_row_ref: Dict[str, any] = {}
    pai_to_pas: Dict[str, Set[str]] = defaultdict(set)
    pai_to_kits: Dict[str, Set[str]] = defaultdict(set)

    outlet_pa_set: Set[str] = set()
    outlet_kit_set: Set[str] = set()
    outlet_pai_set: Set[str] = set()

    for r in outlet_rows:
        pa_cod = r.codbarra_produto
        pa_to_rows[pa_cod].append(r)
        outlet_pa_set.add(pa_cod)
        if r.codbarra_kit:
            pa_to_kits[pa_cod].add(r.codbarra_kit)
            kit_to_row_ref.setdefault(r.codbarra_kit, r)
            outlet_kit_set.add(r.codbarra_kit)
            if r.codbarra_pai:
                kit_to_pai_resolved.setdefault(r.codbarra_kit, r.codbarra_pai)
                pai_to_pas[r.codbarra_pai].add(pa_cod)
                pai_to_kits[r.codbarra_pai].add(r.codbarra_kit)
        if r.codbarra_pai:
            pai_to_row_ref.setdefault(r.codbarra_pai, r)
            outlet_pai_set.add(r.codbarra_pai)

    pai_to_grupinho_kits: Dict[str, Set[str]] = defaultdict(set)
    for r in outlet_rows:
        if not r.codbarra_kit or not r.codbarra_pai:
            continue
        if is_blank(r.grupo_kit):
            continue
        pai_to_grupinho_kits[r.codbarra_pai].add(r.codbarra_kit)

    def pa_base_decision(pa_ref) -> OutletDecision:
        marca = pa_ref.fabricante_produto or ""
        dias_base = brand_base_days(marca)
        if ctx.estoque_pa(pa_ref) <= 0:
            return OutletDecision(
                estoque_seg=1000,
                dias=forn_outlet(pa_ref, ItemTipo.PA),
                msg="REGRA BASE: PA SEM ESTOQUE -> PRAZO FORNECEDOR",
                source="BASE",
            )
        return OutletDecision(
            estoque_seg=0,
            dias=dias_base,
            msg=f"REGRA BASE POR MARCA ({norm_upper(marca) or 'SEM MARCA'})",
            source="BASE",
        )

    def kit_component_zero(kit_cod: str) -> bool:
        pas_do_kit = kit_to_pas_all.get(kit_cod, set())
        for pa_comp in pas_do_kit:
            if pa_comp not in pa_all_rows:
                continue
            rr_comp = pick_best_pa_row(pa_all_rows[pa_comp])
            if ctx.estoque_pa(rr_comp) <= 0:
                return True
        return False

    def kit_decision(pa_ref, kit_ref, kit_cod: str) -> OutletDecision:
        # Base do KIT sempre nasce da regra principal do PA/marca
        base = pa_base_decision(pa_ref)
        decision = OutletDecision(
            estoque_seg=0,
            dias=base.dias,
            msg="REGRA BASE DO KIT = REGRA PRINCIPAL DO PA",
            source="BASE",
        )

        # Complementar 1: KIT fisicamente zerado
        if ctx.estoque_kit(kit_ref) <= 0:
            decision.dias = forn_outlet(kit_ref, ItemTipo.KIT)
            decision.msg = "KIT SEM ESTOQUE -> PRAZO FORNECEDOR"
            decision.source = "COMPLEMENTAR"
            decision.add_override("estoque_real_kit <= 0")
            return decision

        # Complementar 2: KIT zerado por componente
        if kit_component_zero(kit_cod):
            decision.dias = forn_outlet(kit_ref, ItemTipo.KIT)
            decision.msg = "KIT ZERADO POR COMPONENTE -> PRAZO FORNECEDOR"
            decision.source = "COMPLEMENTAR"
            decision.add_override("kit_efetivo_zerado")
            decision.add_override("algum componente do kit zerado")
            return decision

        # Complementar 3: grupinho influencia o KIT, não derruba o PA sozinho
        if not is_blank(getattr(kit_ref, "grupo_kit", None)):
            decision.add_override("grupo_kit / grupinho presente")

        return decision

    def pai_has_any_special_issue(pai_cod: str) -> bool:
        # grupinho com kit zerado ou componente zerado força fornecedor no PAI
        for kit_cod in pai_to_grupinho_kits.get(pai_cod, set()):
            kit_ref = kit_to_row_ref.get(kit_cod)
            if kit_ref is None:
                continue
            if ctx.estoque_kit(kit_ref) <= 0:
                return True
            if kit_component_zero(kit_cod):
                return True
        return False

    def pai_decision(pai_cod: str, pai_ref) -> OutletDecision:
        pa_codes = sorted(pai_to_pas.get(pai_cod, set()))
        if not pa_codes:
            # fallback seguro
            return OutletDecision(
                estoque_seg=0,
                dias=forn_outlet(pai_ref, ItemTipo.PAI),
                msg="PAI SEM PAS MAPEADOS -> PRAZO FORNECEDOR",
                source="FALLBACK",
            )

        rep_pa = pick_best_pa_row(pa_to_rows[pa_codes[0]])
        base_days = brand_base_days(rep_pa.fabricante_produto or "")

        all_pa_gt_zero = True
        for pa_cod in pa_codes:
            rr = pick_best_pa_row(pa_to_rows[pa_cod])
            if ctx.estoque_pa(rr) <= 0:
                all_pa_gt_zero = False
                break

        if all_pa_gt_zero:
            decision = OutletDecision(
                estoque_seg=0,
                dias=base_days,
                msg="REGRA BASE DO PAI: TODOS OS PAs COM ESTOQUE",
                source="BASE",
            )
        else:
            decision = OutletDecision(
                estoque_seg=0,
                dias=forn_outlet(pai_ref, ItemTipo.PAI),
                msg="REGRA BASE DO PAI: ALGUM PA SEM ESTOQUE -> PRAZO FORNECEDOR",
                source="BASE",
            )

        if pai_has_any_special_issue(pai_cod):
            decision.dias = forn_outlet(pai_ref, ItemTipo.PAI)
            decision.msg = "COMPLEMENTAR DO PAI -> PRAZO FORNECEDOR"
            decision.source = "COMPLEMENTAR"
            decision.add_override("grupinho com kit/componente zerado")

        return decision

    # 1) Emitir PA e KIT por PA, respeitando base primeiro e complementares só no alvo certo
    for pa_cod in sorted(outlet_pa_set):
        rr0 = pick_best_pa_row(pa_to_rows[pa_cod])
        emit_single_outlet(rr0, ItemTipo.PA, pa_cod, decision=pa_base_decision(rr0))

        for kit_cod in sorted(pa_to_kits.get(pa_cod, set())):
            if kit_cod not in outlet_kit_set:
                continue
            kit_ref = kit_to_row_ref.get(kit_cod, rr0)
            emit_single_outlet(
                kit_ref,
                ItemTipo.KIT,
                kit_cod,
                decision=kit_decision(rr0, kit_ref, kit_cod),
                allow_locked=True,
            )

    # 2) Emitir PAI por pai resolvido, usando todos os PAs OUTLET do pai
    for pai_cod in sorted(outlet_pai_set):
        pai_ref = pai_to_row_ref.get(pai_cod)
        if pai_ref is None:
            continue
        emit_single_outlet(
            pai_ref,
            ItemTipo.PAI,
            pai_cod,
            decision=pai_decision(pai_cod, pai_ref),
            allow_locked=True,
        )
