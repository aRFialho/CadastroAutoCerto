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

    def with_override(self, *, estoque_seg: Optional[int], dias: int, msg: str, source: str) -> "OutletDecision":
        return OutletDecision(
            estoque_seg=estoque_seg,
            dias=dias,
            msg=msg,
            source=source,
            overrides=self.overrides + [self.source],
        )


@dataclass
class OutletBundle:
    pa: OutletDecision
    kit: OutletDecision
    pai: OutletDecision


def apply(ctx: RuleContext) -> None:
    def is_blank_local(v: Any) -> bool:
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

    def decision_message(d: OutletDecision) -> str:
        if not d.overrides:
            return d.msg
        chain = " -> ".join(d.overrides + [d.source])
        return f"{d.msg} | prioridade={chain}"

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
        a.add_msg(decision_message(decision))
        ctx.upsert_action(a)
        if not allow_locked:
            ctx.lock(a.codbarra, RuleName.OUTLET)
        ctx.report(RuleName.OUTLET, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", decision_message(decision))

    pa_all_rows: Dict[str, List] = defaultdict(list)
    kit_all_rows: Dict[str, List] = defaultdict(list)
    kit_to_pas_all: Dict[str, Set[str]] = defaultdict(set)
    kit_to_row_ref: Dict[str, any] = {}
    kit_to_pai_resolved: Dict[str, str] = {}
    pai_to_row_ref: Dict[str, any] = {}

    for r in ctx.rows:
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

    outlet_rows = [r for r in ctx.rows if grupo3_bucket(r.nome_grupo3) == RuleName.OUTLET.value and r.codbarra_produto]
    if not outlet_rows:
        return

    pa_to_rows: Dict[str, List] = defaultdict(list)
    pa_to_kits: Dict[str, Set[str]] = defaultdict(set)
    for r in outlet_rows:
        pa_to_rows[r.codbarra_produto].append(r)
        if r.codbarra_kit:
            pa_to_kits[r.codbarra_produto].add(r.codbarra_kit)

    pai_to_grupinho_kits: Dict[str, Set[str]] = defaultdict(set)
    pai_to_grupinho_pas: Dict[str, Set[str]] = defaultdict(set)
    for r in outlet_rows:
        if not r.codbarra_kit:
            continue
        if is_blank_local(r.grupo_kit):
            continue
        pai_res = kit_to_pai_resolved.get(r.codbarra_kit) or (r.codbarra_pai or "")
        if not pai_res:
            continue
        pai_to_grupinho_kits[pai_res].add(r.codbarra_kit)
        if r.codbarra_produto:
            pai_to_grupinho_pas[pai_res].add(r.codbarra_produto)

    def base_bundle(rr0, *, has_kit: bool, has_pai_resolved: bool) -> OutletBundle:
        disp_pa = ctx.estoque_pa(rr0)
        base_days = brand_base_days(rr0.fabricante_produto or "")

        if disp_pa <= 0:
            pa = OutletDecision(1000, forn_outlet(rr0, ItemTipo.PA), "OUTLET base: PA sem estoque -> prazo fornecedor", "base_sem_estoque_pa")
            kit = OutletDecision(0, forn_outlet(rr0, ItemTipo.KIT), "OUTLET base: KIT vinculado a PA sem estoque -> prazo fornecedor", "base_sem_estoque_kit")
            pai = OutletDecision(0, forn_outlet(rr0, ItemTipo.PAI), "OUTLET base: PAI vinculado a PA sem estoque -> prazo fornecedor", "base_sem_estoque_pai")
            return OutletBundle(pa=pa, kit=kit, pai=pai)

        # estoque > 0: regra oficial por marca
        pa = OutletDecision(0, base_days, f"OUTLET base por marca: PA -> prazo {base_days}", "base_marca_pa")
        kit = OutletDecision(0, base_days, f"OUTLET base por marca: KIT -> prazo {base_days}", "base_marca_kit")
        pai = OutletDecision(0, base_days, f"OUTLET base por marca: PAI -> prazo {base_days}", "base_marca_pai")

        # complementar histórica preservada: PA com KIT e sem PAI, todos os kits > 0, vira imediata
        if has_kit and (not has_pai_resolved):
            pa = OutletDecision(0, 0, "OUTLET complementar: PA com KIT e sem PAI -> imediata", "sem_pai_pa")
            kit = OutletDecision(0, 0, "OUTLET complementar: KIT sem PAI acompanha PA -> imediata", "sem_pai_kit")
            pai = OutletDecision(0, 0, "OUTLET complementar: sem PAI resolvido -> sem ação operacional de pai/imediata", "sem_pai_pai")

        return OutletBundle(pa=pa, kit=kit, pai=pai)

    def emit_bundle_for_pa(pa_cod: str, *, pa_ref, bundle: OutletBundle, kit_days_override: Optional[int] = None, pai_days_override: Optional[int] = None) -> None:
        emit_single_outlet(pa_ref, ItemTipo.PA, pa_cod, decision=bundle.pa)
        kits = sorted(pa_to_kits.get(pa_cod, set()))
        for kit_cod in kits:
            kit_ref = kit_to_row_ref.get(kit_cod, pa_ref)
            decision = bundle.kit
            if kit_days_override is not None:
                decision = decision.with_override(
                    estoque_seg=decision.estoque_seg,
                    dias=kit_days_override,
                    msg=f"{decision.msg} (prazo ajustado por item KIT)",
                    source="kit_override",
                )
            emit_single_outlet(kit_ref, ItemTipo.KIT, kit_cod, decision=decision, allow_locked=True)
        pais: Set[str] = set()
        for kit_cod in kits:
            p = kit_to_pai_resolved.get(kit_cod)
            if p:
                pais.add(p)
        for pai_cod in sorted(pais):
            pai_ref = pai_to_row_ref.get(pai_cod, pa_ref)
            decision = bundle.pai
            if pai_days_override is not None:
                decision = decision.with_override(
                    estoque_seg=decision.estoque_seg,
                    dias=pai_days_override,
                    msg=f"{decision.msg} (prazo ajustado por item PAI)",
                    source="pai_override",
                )
            emit_single_outlet(pai_ref, ItemTipo.PAI, pai_cod, decision=decision, allow_locked=True)

    processed_pas: Set[str] = set()

    # COMPLEMENTAR 1: grupinho tem prioridade sobre a base, mas parte da regra oficial por marca
    for pai_cod, kits_grup in pai_to_grupinho_kits.items():
        if not kits_grup:
            continue
        any_kit_le_zero = False
        for k in kits_grup:
            rrk = kit_to_row_ref.get(k)
            if rrk and ctx.estoque_kit(rrk) <= 0:
                any_kit_le_zero = True
                break

        any_pa_cod = next(iter(pai_to_grupinho_pas.get(pai_cod, set())), None)
        pa_ref_base = pick_best_pa_row(pa_to_rows[any_pa_cod]) if any_pa_cod and pa_to_rows.get(any_pa_cod) else (pai_to_row_ref.get(pai_cod) or outlet_rows[0])
        base_days = brand_base_days(pa_ref_base.fabricante_produto or "")

        for pa_cod_g in sorted(pai_to_grupinho_pas.get(pai_cod, set())):
            pa_ref2 = pick_best_pa_row(pa_to_rows[pa_cod_g])
            bundle = base_bundle(pa_ref2, has_kit=bool(pa_to_kits.get(pa_cod_g, set())), has_pai_resolved=True)
            if any_kit_le_zero:
                bundle = OutletBundle(
                    pa=bundle.pa.with_override(
                        estoque_seg=1000,
                        dias=forn_outlet(pa_ref2, ItemTipo.PA),
                        msg="OUTLET complementar: grupinho com algum KIT <= 0 -> PA prazo fornecedor",
                        source="grupinho_kit_zero_pa",
                    ),
                    kit=bundle.kit.with_override(
                        estoque_seg=0,
                        dias=forn_outlet(pa_ref2, ItemTipo.KIT),
                        msg="OUTLET complementar: grupinho com algum KIT <= 0 -> KIT prazo fornecedor",
                        source="grupinho_kit_zero_kit",
                    ),
                    pai=bundle.pai.with_override(
                        estoque_seg=0,
                        dias=forn_outlet(pa_ref2, ItemTipo.PAI),
                        msg="OUTLET complementar: grupinho com algum KIT <= 0 -> PAI prazo fornecedor",
                        source="grupinho_kit_zero_pai",
                    ),
                )
            else:
                bundle = OutletBundle(
                    pa=bundle.pa.with_override(
                        estoque_seg=0,
                        dias=base_days,
                        msg=f"OUTLET complementar: grupinho com todos os KITS > 0 -> PA prazo {base_days}",
                        source="grupinho_ok_pa",
                    ),
                    kit=bundle.kit.with_override(
                        estoque_seg=0,
                        dias=base_days,
                        msg=f"OUTLET complementar: grupinho com todos os KITS > 0 -> KIT prazo {base_days}",
                        source="grupinho_ok_kit",
                    ),
                    pai=bundle.pai.with_override(
                        estoque_seg=0,
                        dias=base_days,
                        msg=f"OUTLET complementar: grupinho com todos os KITS > 0 -> PAI prazo {base_days}",
                        source="grupinho_ok_pai",
                    ),
                )
            emit_bundle_for_pa(pa_cod_g, pa_ref=pa_ref2, bundle=bundle)
            processed_pas.add(pa_cod_g)

    for pa_cod, rr_list in pa_to_rows.items():
        if pa_cod in processed_pas:
            continue
        rr0 = pick_best_pa_row(rr_list)
        kits_for_pa = sorted(pa_to_kits.get(pa_cod, set()))
        has_kit = bool(kits_for_pa)
        resolved_pais = {kit_to_pai_resolved.get(k) for k in kits_for_pa}
        resolved_pais.discard(None)
        has_pai_resolved = bool(resolved_pais)

        bundle = base_bundle(rr0, has_kit=has_kit, has_pai_resolved=has_pai_resolved)

        if not has_kit:
            emit_bundle_for_pa(pa_cod, pa_ref=rr0, bundle=bundle)
            continue

        any_kit_le_zero = False
        for kit_cod in kits_for_pa:
            rrk = kit_to_row_ref.get(kit_cod)
            if rrk and ctx.estoque_kit(rrk) <= 0:
                any_kit_le_zero = True
                break

        if not has_pai_resolved and any_kit_le_zero:
            bundle = OutletBundle(
                pa=bundle.pa.with_override(
                    estoque_seg=1000,
                    dias=forn_outlet(rr0, ItemTipo.PA),
                    msg="OUTLET complementar: PA com KIT e sem PAI, com KIT <= 0 -> prazo fornecedor",
                    source="sem_pai_kit_zero_pa",
                ),
                kit=bundle.kit.with_override(
                    estoque_seg=0,
                    dias=forn_outlet(rr0, ItemTipo.KIT),
                    msg="OUTLET complementar: KIT sem PAI com KIT <= 0 -> prazo fornecedor",
                    source="sem_pai_kit_zero_kit",
                ),
                pai=bundle.pai,
            )
            emit_bundle_for_pa(pa_cod, pa_ref=rr0, bundle=bundle)
            continue

        if ctx.estoque_pa(rr0) <= 0:
            emit_bundle_for_pa(pa_cod, pa_ref=rr0, bundle=bundle)
            continue

        # COMPLEMENTAR 2: kit efetivo zerado por componente. Refina KIT/PAI; PA componente zerado segue regra própria.
        kit_efetivo_zerado = False
        for kit_cod in kits_for_pa:
            pas_do_kit = kit_to_pas_all.get(kit_cod, set())
            for pa_comp in pas_do_kit:
                if pa_comp not in pa_all_rows:
                    continue
                rr_comp = pick_best_pa_row(pa_all_rows[pa_comp])
                if ctx.estoque_pa(rr_comp) <= 0:
                    kit_efetivo_zerado = True
                    break
            if kit_efetivo_zerado:
                break

        if kit_efetivo_zerado:
            base_days = brand_base_days(rr0.fabricante_produto or "")
            for kit_cod in kits_for_pa:
                for pa_comp in kit_to_pas_all.get(kit_cod, set()):
                    if pa_comp not in pa_all_rows:
                        continue
                    rr_comp = pick_best_pa_row(pa_all_rows[pa_comp])
                    if ctx.estoque_pa(rr_comp) <= 0:
                        decision = OutletDecision(
                            1000,
                            forn_outlet(rr_comp, ItemTipo.PA),
                            "OUTLET complementar: PA componente zerado -> prazo fornecedor",
                            "kit_comp_zero_pa_zero",
                        )
                    else:
                        decision = OutletDecision(
                            0,
                            base_days,
                            f"OUTLET complementar: PA componente ok mantém regra base -> prazo {base_days}",
                            "kit_comp_zero_pa_ok",
                        )
                    emit_single_outlet(rr_comp, ItemTipo.PA, pa_comp, decision=decision, allow_locked=True)

            bundle = OutletBundle(
                pa=bundle.pa,
                kit=bundle.kit.with_override(
                    estoque_seg=0,
                    dias=forn_outlet(rr0, ItemTipo.KIT),
                    msg="OUTLET complementar: KIT zerado por componente -> prazo fornecedor",
                    source="kit_comp_zero_kit",
                ),
                pai=bundle.pai.with_override(
                    estoque_seg=0,
                    dias=forn_outlet(rr0, ItemTipo.PAI),
                    msg="OUTLET complementar: PAI impactado por KIT zerado por componente -> prazo fornecedor",
                    source="kit_comp_zero_pai",
                ),
            )
            emit_bundle_for_pa(pa_cod, pa_ref=rr0, bundle=bundle)
            continue

        # COMPLEMENTAR 3: PAI depende do conjunto de PAs filhos do pai
        todos_pa_filhos_gt_zero = True
        for pai_cod_check in sorted(resolved_pais):
            pas_deste_pai: Set[str] = set()
            for other_pa, other_kits in pa_to_kits.items():
                for ok in other_kits:
                    if kit_to_pai_resolved.get(ok) == pai_cod_check:
                        pas_deste_pai.add(other_pa)
            for other_pa_cod in pas_deste_pai:
                other_rr0 = pick_best_pa_row(pa_to_rows[other_pa_cod])
                if ctx.estoque_pa(other_rr0) <= 0:
                    todos_pa_filhos_gt_zero = False
                    break
            if not todos_pa_filhos_gt_zero:
                break

        if not todos_pa_filhos_gt_zero:
            bundle = OutletBundle(
                pa=bundle.pa,
                kit=bundle.kit,
                pai=bundle.pai.with_override(
                    estoque_seg=0,
                    dias=forn_outlet(rr0, ItemTipo.PAI),
                    msg="OUTLET complementar: algum PA filho do PAI <= 0 -> prazo fornecedor",
                    source="pai_algum_pa_zero",
                ),
            )

        emit_bundle_for_pa(pa_cod, pa_ref=rr0, bundle=bundle)
