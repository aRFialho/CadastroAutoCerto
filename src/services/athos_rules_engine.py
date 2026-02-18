from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple
from collections import defaultdict

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


@dataclass
class AthosOutputs:
    """
    Saída do motor:
    - actions_by_rule: dict com listas de ações (linhas a escrever em cada planilha)
    - report_lines: relatório único consolidado
    """
    actions_by_rule: Dict[RuleName, List[AthosAction]]
    report_lines: List[AthosReportLine]


def _to_row(d: Dict[str, Any]) -> AthosRow:
    # Aceita dicts vindos do pyodbc (chaves podem vir em qualquer caixa)
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
        codbarra_produto=normalize_ean(g("CODBARRA_PRODUTO", "codbarra_produto")),
        estoque_real_produto=_to_float(g("ESTOQUE_REAL_PRODUTO", "estoque_real_produto")),
        prazo_produto=g("PRAZO_PRODUTO", "prazo_produto"),
        fabricante_produto=_to_str(g("FABRICANTE_PRODUTO", "fabricante_produto")),
        nome_grupo3=_to_str(g("NOME_GRUPO3", "nome_grupo3")),
        nome_grupo_produto=_to_str(g("NOME_GRUPO", "GRUPO DO PRODUTO", "grupo do produto", "nome_grupo")),

        codbarra_kit=normalize_ean(g("CODBARRA_KIT", "codbarra_kit")),
        estoque_real_kit=_to_float(g("ESTOQUE_REAL_KIT", "estoque_real_kit")),
        prazo_kit=g("PRAZO_KIT", "prazo_kit"),
        fabricante_kit=_to_str(g("FABRICANTE_KIT", "fabricante_kit")),

        codbarra_pai=normalize_ean(g("CODBARRA_PAI", "codbarra_pai")),
        prazo_pai=g("PRAZO_PAI", "prazo_pai"),
        fabricante_pai=_to_str(g("FABRICANTE_PAI", "fabricante_pai")),
    )


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        # tenta parse string
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


def process_rows(
    sql_rows: List[Dict[str, Any]],
    whitelist_imediatos: Set[str],
    supplier_prazo_lookup: Optional[Callable[[str], Optional[int]]] = None,
) -> AthosOutputs:
    """
    Motor principal:
    - recebe rows do SQL (dicts)
    - recebe whitelist (set EANs)
    - retorna ações por regra + relatório único
    """

    rows = [_to_row(r) for r in sql_rows]

    # index por pai: lista de linhas
    by_pai: Dict[str, List[AthosRow]] = defaultdict(list)
    for r in rows:
        pai = r.codbarra_pai or "__SEM_PAI__"
        by_pai[pai].append(r)

    # controladores de prioridade: se um codbarra já foi "travado" por regra anterior
    locked_by: Dict[str, RuleName] = {}

    # regra especial: quando bloqueia atualização (só relatório)
    blocked_codbar: Set[str] = set()

    actions_by_rule: Dict[RuleName, Dict[str, AthosAction]] = {
        rn: {} for rn in ORDERED_RULES
    }
    report_lines: List[AthosReportLine] = []

    def lock(ean: str, rule: RuleName) -> None:
        locked_by[ean] = rule

    def is_locked(ean: str) -> bool:
        return ean in locked_by or ean in blocked_codbar

    def _prazo_fornecedor(r: AthosRow) -> int:
        """
        Prazo do fornecedor:
        1) se nome_grupo_produto existir e for numérico, usa ele
        2) senão, tenta banco de fornecedores via callback (por marca)
        3) fallback: tenta parse do próprio prazo_produto (se vier numérico)
        4) fallback final: 0
        """
        p = parse_int_safe(r.nome_grupo_produto)
        if p is not None:
            return int(p)

        marca = norm_upper(r.fabricante_produto)
        if supplier_prazo_lookup and marca:
            try:
                db_p = supplier_prazo_lookup(marca)
                if db_p is not None:
                    return int(db_p)
            except Exception:
                pass

        p2 = parse_int_safe(r.prazo_produto)
        if p2 is not None:
            return int(p2)

        return 0

    def upsert_action(action: AthosAction) -> None:
        """
        Insere/mescla por (rule, codbarra).
        Consolidamos para não duplicar linhas na planilha.
        """
        bucket = actions_by_rule[action.rule]
        existing = bucket.get(action.codbarra)
        if existing is None:
            bucket[action.codbarra] = action
            return

        # merge conservador: não sobrescrever campos já setados
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

        # meta
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
        # campos (aplicáveis a todos, exceto estoque)
        grupo3: Optional[str] = None,
        produto_inativo: Optional[str] = None,
        dias_entrega: Optional[int] = None,
        site_disp: Optional[str] = None,
        # estoque (PA/KIT/PAI)
        estoque_pa: Optional[int] = None,
        estoque_kit: Optional[int] = None,
        estoque_pai: Optional[int] = None,
        msg_pa: Optional[str] = None,
        msg_kit: Optional[str] = None,
        msg_pai: Optional[str] = None,
    ) -> None:
        """
        Cria ações (linhas) para PA, KIT e PAI conforme regra-mãe.
        Não cria se codbarra estiver vazio.
        Respeita lock/prioridade.
        """
        g3_pa = _safe_group3(r.nome_grupo3)

        # PA
        if r.codbarra_produto and not is_locked(r.codbarra_produto):
            a = AthosAction(rule=rule, tipo=ItemTipo.PA, codbarra=r.codbarra_produto)
            a.grupo3 = grupo3
            a.produto_inativo = produto_inativo
            a.dias_entrega = dias_entrega
            a.site_disponibilidade = site_disp
            a.estoque_seguranca = estoque_pa
            a.marca = r.fabricante_produto or ""
            a.grupo3_origem_pa = g3_pa
            if msg_pa:
                a.add_msg(msg_pa)
                report(rule, a.codbarra, a.tipo, a.marca or "", g3_pa, msg_pa)
            upsert_action(a)
            lock(a.codbarra, rule)

        # KIT
        if r.codbarra_kit and not is_locked(r.codbarra_kit):
            a = AthosAction(rule=rule, tipo=ItemTipo.KIT, codbarra=r.codbarra_kit)
            a.grupo3 = grupo3
            a.produto_inativo = produto_inativo
            a.dias_entrega = dias_entrega
            a.site_disponibilidade = site_disp
            a.estoque_seguranca = estoque_kit
            a.marca = r.fabricante_kit or ""
            a.grupo3_origem_pa = g3_pa
            if msg_kit:
                a.add_msg(msg_kit)
                report(rule, a.codbarra, a.tipo, a.marca or "", g3_pa, msg_kit)
            upsert_action(a)
            lock(a.codbarra, rule)

        # PAI
        if r.codbarra_pai and not is_locked(r.codbarra_pai):
            a = AthosAction(rule=rule, tipo=ItemTipo.PAI, codbarra=r.codbarra_pai)
            a.grupo3 = grupo3
            a.produto_inativo = produto_inativo
            a.dias_entrega = dias_entrega
            a.site_disponibilidade = site_disp
            a.estoque_seguranca = estoque_pai
            a.marca = r.fabricante_pai or ""
            a.grupo3_origem_pa = g3_pa
            if msg_pai:
                a.add_msg(msg_pai)
                report(rule, a.codbarra, a.tipo, a.marca or "", g3_pa, msg_pai)
            upsert_action(a)
            lock(a.codbarra, rule)

    # ======================================================
    # 1) FORA DE LINHA
    # ======================================================
    for r in rows:
        g3 = grupo3_bucket(r.nome_grupo3)
        if g3 != RuleName.FORA_DE_LINHA.value:
            continue
        if (r.estoque_real_produto or 0) <= 0 and r.codbarra_produto:
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
    # ======================================================
    # Regra:
    # - Kits com mesmo prazo do PA
    # - Pai com maior prazo dos kits do grupo
    for pai_key, group_rows in by_pai.items():
        # pega apenas os registros cujo PA está em estoque compartilhado
        # (grupo3 é do PA)
        esc_rows = [r for r in group_rows if grupo3_bucket(r.nome_grupo3) == RuleName.ESTOQUE_COMPARTILHADO.value]
        if not esc_rows:
            continue

        # (a) kits com prazo do PA (por linha)
        kit_prazos: List[int] = []
        for r in esc_rows:
            if not r.codbarra_kit:
                continue
            if is_locked(r.codbarra_kit):
                continue

            if is_imediata(r.prazo_produto):
                # regra geral: se o prazo do PA vier como "Imediata", aplica como imediata
                a = AthosAction(rule=RuleName.ESTOQUE_COMPARTILHADO, tipo=ItemTipo.KIT, codbarra=r.codbarra_kit)
                apply_imediata(a)
                a.marca = r.fabricante_kit or ""
                a.grupo3_origem_pa = _safe_group3(r.nome_grupo3)
                a.add_msg("IMEDIATA (DIAS=0, SITE=IMEDIATA)")
                upsert_action(a)
                lock(a.codbarra, RuleName.ESTOQUE_COMPARTILHADO)
                report(RuleName.ESTOQUE_COMPARTILHADO, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", "IMEDIATA (DIAS=0, SITE=IMEDIATA)")
                continue

            p = parse_int_safe(r.prazo_produto)
            if p is None:
                # fallback: se não conseguir parsear, não mexe aqui (prazo fornecedor entra em regra futura se necessário)
                continue

            kit_prazos.append(p)
            a = AthosAction(rule=RuleName.ESTOQUE_COMPARTILHADO, tipo=ItemTipo.KIT, codbarra=r.codbarra_kit)
            apply_prazo(a, p)
            a.marca = r.fabricante_kit or ""
            a.grupo3_origem_pa = _safe_group3(r.nome_grupo3)
            a.add_msg(f"PRAZO DEFINIDO {p} DIAS")
            upsert_action(a)
            lock(a.codbarra, RuleName.ESTOQUE_COMPARTILHADO)
            report(RuleName.ESTOQUE_COMPARTILHADO, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", f"PRAZO DEFINIDO {p} DIAS")

        # (b) pai com maior prazo dos kits do grupo
        if pai_key != "__SEM_PAI__" and kit_prazos and not is_locked(pai_key):
            maior = max(kit_prazos)
            a = AthosAction(rule=RuleName.ESTOQUE_COMPARTILHADO, tipo=ItemTipo.PAI, codbarra=pai_key)
            apply_prazo(a, maior)
            # marca do pai: pega do primeiro que tiver fabricante_pai
            any_row = next((rr for rr in esc_rows if rr.fabricante_pai), None)
            a.marca = any_row.fabricante_pai if any_row else ""
            a.grupo3_origem_pa = RuleName.ESTOQUE_COMPARTILHADO.value
            a.add_msg(f"PRAZO DEFINIDO {maior} DIAS")
            upsert_action(a)
            lock(a.codbarra, RuleName.ESTOQUE_COMPARTILHADO)
            report(RuleName.ESTOQUE_COMPARTILHADO, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", f"PRAZO DEFINIDO {maior} DIAS")

    # ======================================================
    # 3) ENVIO IMEDIATO
    # ======================================================
    # (a) LIMPEZA: se está no grupo3 envio imediato e não está na whitelist => GRUPO3="apagar"
    for r in rows:
        g3 = grupo3_bucket(r.nome_grupo3)
        if g3 != RuleName.ENVIO_IMEDIATO.value:
            continue
        if not r.codbarra_produto:
            continue
        if is_locked(r.codbarra_produto):
            continue

        if r.codbarra_produto not in whitelist_imediatos:
            a = AthosAction(rule=RuleName.ENVIO_IMEDIATO, tipo=ItemTipo.PA, codbarra=r.codbarra_produto)
            a.grupo3 = "apagar"
            a.marca = r.fabricante_produto or ""
            a.grupo3_origem_pa = _safe_group3(r.nome_grupo3)
            a.add_msg("RETIRADO DO GRUPO3 ENVIO IMEDIATO")
            upsert_action(a)
            lock(a.codbarra, RuleName.ENVIO_IMEDIATO)
            report(RuleName.ENVIO_IMEDIATO, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", "RETIRADO DO GRUPO3 ENVIO IMEDIATO")

    # (b) REGRA ESPECIAL (somente relatório, sem gerar planilha):
    # marcas especiais + todos PAs do mesmo PAI com estoque <=0
    for pai_key, group_rows in by_pai.items():
        if pai_key == "__SEM_PAI__":
            continue

        # considera apenas linhas onde PA está em envio imediato
        grp = [r for r in group_rows if grupo3_bucket(r.nome_grupo3) == RuleName.ENVIO_IMEDIATO.value and r.codbarra_produto]
        if not grp:
            continue

        # pega marca do PA em cada linha, e filtra só as marcas especiais
        special_pas = [r for r in grp if norm_upper(r.fabricante_produto) in SPECIAL_IMEDIATO_BRANDS]

        if not special_pas:
            continue

        # avalia "todos os PA do mesmo pai <=0" (considera TODOS os PAs do grupo envio imediato)
        all_le_zero = all((rr.estoque_real_produto or 0) <= 0 for rr in grp)
        if not all_le_zero:
            continue

        # Se bloqueou: NÃO atualiza nada em planilha para esse grupo.
        # Bloqueia PA + KIT + PAI (quando existirem) para que nenhuma outra regra escreva.
        for rr in grp:
            if rr.codbarra_produto:
                blocked_codbar.add(rr.codbarra_produto)
            if rr.codbarra_kit:
                blocked_codbar.add(rr.codbarra_kit)
            if rr.codbarra_pai:
                blocked_codbar.add(rr.codbarra_pai)

        # Para cada PA especial: só relatório
        for rr in special_pas:
            if rr.codbarra_produto:
                report(
                    RuleName.ENVIO_IMEDIATO,
                    rr.codbarra_produto,
                    ItemTipo.PA,
                    rr.fabricante_produto or "",
                    _safe_group3(rr.nome_grupo3),
                    "Colocar cód Fabricante, mudar para Estoque Compartilhado",
                )

    # (c) APLICAÇÃO REAL DO ENVIO IMEDIATO (válidos na whitelist)
    IMEDIATA_BRANDS = {"KONFORT", "CASA DO PUFF", "DIVINI DECOR", "LUMIL", "MADERATTO"}

    # Pré-cálculo por pai: status dos PAs
    pai_pa_stock: Dict[str, Dict[str, float]] = defaultdict(dict)
    pai_pa_brand: Dict[str, str] = {}
    for r in rows:
        if grupo3_bucket(r.nome_grupo3) != RuleName.ENVIO_IMEDIATO.value:
            continue
        if not r.codbarra_produto:
            continue
        pai_key = r.codbarra_pai or "__SEM_PAI__"
        # só considera PAs da whitelist para a lógica de grupo
        if r.codbarra_produto not in whitelist_imediatos:
            continue
        pai_pa_stock[pai_key][r.codbarra_produto] = float(r.estoque_real_produto or 0)
        if pai_key not in pai_pa_brand:
            pai_pa_brand[pai_key] = norm_upper(r.fabricante_produto)

    for pai_key, group_rows in by_pai.items():
        # filtra somente linhas de envio imediato válidas
        grp = [
            r for r in group_rows
            if grupo3_bucket(r.nome_grupo3) == RuleName.ENVIO_IMEDIATO.value
            and r.codbarra_produto
            and r.codbarra_produto in whitelist_imediatos
        ]
        if not grp:
            continue

        stocks = pai_pa_stock.get(pai_key, {})
        all_gt_zero = bool(stocks) and all(v > 0 for v in stocks.values())
        all_le_zero = bool(stocks) and all(v <= 0 for v in stocks.values())
        marca_group = pai_pa_brand.get(pai_key) or norm_upper(grp[0].fabricante_produto)

        def set_pai(rule: RuleName, *, dias: int, site: str, msg: str) -> None:
            if pai_key != "__SEM_PAI__" and not is_locked(pai_key):
                a = AthosAction(rule=rule, tipo=ItemTipo.PAI, codbarra=pai_key)
                a.dias_entrega = dias
                a.site_disponibilidade = site
                a.marca = grp[0].fabricante_pai or ""
                a.grupo3_origem_pa = RuleName.ENVIO_IMEDIATO.value
                a.add_msg(msg)
                upsert_action(a)
                lock(a.codbarra, rule)
                report(rule, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", msg)

        # --- DMOV2 ---
        if marca_group == "DMOV2":
            # regra base: PA > 0 => estoque seg 1000, 3 dias
            for r in grp:
                disp = float(r.estoque_real_produto or 0)
                if disp > 0:
                    emit_for_pa_kit_pai(
                        RuleName.ENVIO_IMEDIATO,
                        r,
                        estoque_pa=1000,
                        dias_entrega=3,
                        site_disp="3",
                        msg_pa="INCLUIDO 1000 ESTOQUE SEG",
                        msg_kit="PRAZO DEFINIDO 3 DIAS",
                        msg_pai=None,
                    )
                else:
                    p = _prazo_fornecedor(r)
                    emit_for_pa_kit_pai(
                        RuleName.ENVIO_IMEDIATO,
                        r,
                        estoque_pa=0,
                        dias_entrega=p,
                        site_disp=str(p),
                        msg_pa=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                        msg_kit=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                        msg_pai=None,
                    )

            # pai: se TODOS PA do pai >0 => 3 dias, senão prazo fornecedor
            if pai_key != "__SEM_PAI__":
                if all_gt_zero:
                    set_pai(RuleName.ENVIO_IMEDIATO, dias=3, site="3", msg="PRAZO DEFINIDO 3 DIAS")
                else:
                    p = max((_prazo_fornecedor(r) for r in grp), default=0)
                    set_pai(RuleName.ENVIO_IMEDIATO, dias=p, site=str(p), msg=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)")

            continue

        # --- Marcas imediata (Konfort, Casa do Puff, Divini, Lumil, Maderatto) ---
        if marca_group in IMEDIATA_BRANDS:
            if all_gt_zero:
                # tudo imediata
                for r in grp:
                    emit_for_pa_kit_pai(
                        RuleName.ENVIO_IMEDIATO,
                        r,
                        estoque_pa=0,
                        dias_entrega=0,
                        site_disp="IMEDIATA",
                        msg_pa="IMEDIATA (DIAS=0, SITE=IMEDIATA)",
                        msg_kit="IMEDIATA (DIAS=0, SITE=IMEDIATA)",
                        msg_pai=None,
                    )
                set_pai(RuleName.ENVIO_IMEDIATO, dias=0, site="IMEDIATA", msg="IMEDIATA (DIAS=0, SITE=IMEDIATA)")
            elif all_le_zero:
                # todos <=0: PA estoque seg 1000; prazo fornecedor para todos
                for r in grp:
                    p = _prazo_fornecedor(r)
                    emit_for_pa_kit_pai(
                        RuleName.ENVIO_IMEDIATO,
                        r,
                        estoque_pa=1000,
                        dias_entrega=p,
                        site_disp=str(p),
                        msg_pa="INCLUIDO 1000 ESTOQUE SEG",
                        msg_kit=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                        msg_pai=None,
                    )
                pmax = max((_prazo_fornecedor(r) for r in grp), default=0)
                set_pai(RuleName.ENVIO_IMEDIATO, dias=pmax, site=str(pmax), msg=f"PRAZO DEFINIDO {pmax} DIAS (FORNECEDOR)")
            else:
                # mix: PA <=0 => prazo fornecedor; pai imediata
                for r in grp:
                    disp = float(r.estoque_real_produto or 0)
                    if disp <= 0:
                        p = _prazo_fornecedor(r)
                        emit_for_pa_kit_pai(
                            RuleName.ENVIO_IMEDIATO,
                            r,
                            estoque_pa=0,
                            dias_entrega=p,
                            site_disp=str(p),
                            msg_pa=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                            msg_kit=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                            msg_pai=None,
                        )
                    else:
                        emit_for_pa_kit_pai(
                            RuleName.ENVIO_IMEDIATO,
                            r,
                            estoque_pa=0,
                            dias_entrega=0,
                            site_disp="IMEDIATA",
                            msg_pa="IMEDIATA (DIAS=0, SITE=IMEDIATA)",
                            msg_kit="IMEDIATA (DIAS=0, SITE=IMEDIATA)",
                            msg_pai=None,
                        )

                set_pai(RuleName.ENVIO_IMEDIATO, dias=0, site="IMEDIATA", msg="IMEDIATA (DIAS=0, SITE=IMEDIATA)")

            continue

        # --- Outras marcas ---
        if all_gt_zero:
            for r in grp:
                emit_for_pa_kit_pai(
                    RuleName.ENVIO_IMEDIATO,
                    r,
                    estoque_pa=0,
                    dias_entrega=1,
                    site_disp="1",
                    msg_pa="PRAZO DEFINIDO 1 DIA",
                    msg_kit="PRAZO DEFINIDO 1 DIA",
                    msg_pai=None,
                )
            set_pai(RuleName.ENVIO_IMEDIATO, dias=1, site="1", msg="PRAZO DEFINIDO 1 DIA")
        elif all_le_zero:
            for r in grp:
                p = _prazo_fornecedor(r)
                emit_for_pa_kit_pai(
                    RuleName.ENVIO_IMEDIATO,
                    r,
                    estoque_pa=1000,
                    dias_entrega=p,
                    site_disp=str(p),
                    msg_pa="INCLUIDO 1000 ESTOQUE SEG",
                    msg_kit=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                    msg_pai=None,
                )
            pmax = max((_prazo_fornecedor(r) for r in grp), default=0)
            set_pai(RuleName.ENVIO_IMEDIATO, dias=pmax, site=str(pmax), msg=f"PRAZO DEFINIDO {pmax} DIAS (FORNECEDOR)")
        else:
            # mix: PA <=0 => prazo fornecedor; pai 1 dia
            for r in grp:
                disp = float(r.estoque_real_produto or 0)
                if disp <= 0:
                    p = _prazo_fornecedor(r)
                    emit_for_pa_kit_pai(
                        RuleName.ENVIO_IMEDIATO,
                        r,
                        estoque_pa=0,
                        dias_entrega=p,
                        site_disp=str(p),
                        msg_pa=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                        msg_kit=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                        msg_pai=None,
                    )
                else:
                    emit_for_pa_kit_pai(
                        RuleName.ENVIO_IMEDIATO,
                        r,
                        estoque_pa=0,
                        dias_entrega=1,
                        site_disp="1",
                        msg_pa="PRAZO DEFINIDO 1 DIA",
                        msg_kit="PRAZO DEFINIDO 1 DIA",
                        msg_pai=None,
                    )

            set_pai(RuleName.ENVIO_IMEDIATO, dias=1, site="1", msg="PRAZO DEFINIDO 1 DIA")

    # ======================================================
    # 4) NENHUM GRUPO
    # ======================================================
    for r in rows:
        g3 = grupo3_bucket(r.nome_grupo3)
        if g3 is not None:
            continue  # só sem grupo
        if not r.codbarra_produto:
            continue
        if not (r.fabricante_produto or "").strip():
            continue  # sem marca ignora
        if is_locked(r.codbarra_produto):
            continue

        disp = r.estoque_real_produto or 0

        if disp > 0:
            # se está na whitelist => mover para envio imediato, senão => outlet
            if r.codbarra_produto in whitelist_imediatos:
                emit_for_pa_kit_pai(
                    RuleName.NENHUM_GRUPO,
                    r,
                    grupo3=RuleName.ENVIO_IMEDIATO.value,
                    msg_pa="MOVIDO PARA GRUPO3 ENVIO IMEDIATO",
                    msg_kit="MOVIDO PARA GRUPO3 ENVIO IMEDIATO",
                    msg_pai="MOVIDO PARA GRUPO3 ENVIO IMEDIATO",
                )
            else:
                emit_for_pa_kit_pai(
                    RuleName.NENHUM_GRUPO,
                    r,
                    grupo3=RuleName.OUTLET.value,
                    msg_pa="MOVIDO PARA GRUPO3 OUTLET",
                    msg_kit="MOVIDO PARA GRUPO3 OUTLET",
                    msg_pai="MOVIDO PARA GRUPO3 OUTLET",
                )
        else:
            # <=0: não mexe grupo3; PA estoque seg 1000; KIT/PAI prazo fornecedor (por enquanto aplica PRAZO_* se conseguir parsear)
            p = _prazo_fornecedor(r)
            emit_for_pa_kit_pai(
                RuleName.NENHUM_GRUPO,
                r,
                estoque_pa=1000,
                dias_entrega=p,
                site_disp=str(p),
                msg_pa="INCLUIDO 1000 ESTOQUE SEG",
                msg_kit=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
                msg_pai=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
            )

    # ======================================================
    # 5) OUTLET
    # ======================================================
    for r in rows:
        g3 = grupo3_bucket(r.nome_grupo3)
        if g3 != RuleName.OUTLET.value:
            continue
        if not r.codbarra_produto:
            continue
        if is_locked(r.codbarra_produto):
            continue

        disp = r.estoque_real_produto or 0
        marca_pa = norm_upper(r.fabricante_produto)

        if disp <= 0:
            # PA estoque seg 1000; KIT e FILHOS com estoque seg 0; prazo fornecedor
            p = _prazo_fornecedor(r)
            emit_for_pa_kit_pai(
                RuleName.OUTLET,
                r,
                estoque_pa=1000,
                estoque_kit=0,
                dias_entrega=p,
                site_disp=str(p),
                msg_pa="INCLUIDO 1000 ESTOQUE SEG",
                msg_kit="INCLUIDO 0 ESTOQUE SEGURANÇA",
                msg_pai=f"PRAZO DEFINIDO {p} DIAS (FORNECEDOR)",
            )
            continue

        # disp > 0: regra por marca
        if marca_pa in OUTLET_BRANDS_3_DAYS:
            # DMOV/DMOV2: exportar apenas os KITS (não exportar o pai/PA)
            prazo = 3
            if r.codbarra_kit and not is_locked(r.codbarra_kit):
                a = AthosAction(rule=RuleName.OUTLET, tipo=ItemTipo.KIT, codbarra=r.codbarra_kit)
                apply_prazo(a, prazo)
                a.estoque_seguranca = 0
                a.marca = r.fabricante_kit or ""
                a.grupo3_origem_pa = _safe_group3(r.nome_grupo3)
                a.add_msg(f"PRAZO DEFINIDO {prazo} DIAS")
                a.add_msg("INCLUIDO 0 ESTOQUE SEGURANÇA")
                upsert_action(a)
                lock(a.codbarra, RuleName.OUTLET)
                report(RuleName.OUTLET, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", f"PRAZO DEFINIDO {prazo} DIAS")
                report(RuleName.OUTLET, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", "INCLUIDO 0 ESTOQUE SEGURANÇA")
        elif marca_pa in OUTLET_BRANDS_IMEDIATA:
            # Konfort/Casa do Puff/Divini: exportar apenas os KITS (imediata)
            if r.codbarra_kit and not is_locked(r.codbarra_kit):
                a = AthosAction(rule=RuleName.OUTLET, tipo=ItemTipo.KIT, codbarra=r.codbarra_kit)
                apply_imediata(a)
                a.estoque_seguranca = 0
                a.marca = r.fabricante_kit or ""
                a.grupo3_origem_pa = _safe_group3(r.nome_grupo3)
                a.add_msg("IMEDIATA (DIAS=0, SITE=IMEDIATA)")
                a.add_msg("INCLUIDO 0 ESTOQUE SEGURANÇA")
                upsert_action(a)
                lock(a.codbarra, RuleName.OUTLET)
                report(RuleName.OUTLET, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", "IMEDIATA (DIAS=0, SITE=IMEDIATA)")
                report(RuleName.OUTLET, a.codbarra, a.tipo, a.marca or "", a.grupo3_origem_pa or "", "INCLUIDO 0 ESTOQUE SEGURANÇA")
        else:
            prazo = 1
            emit_for_pa_kit_pai(
                RuleName.OUTLET,
                r,
                dias_entrega=prazo,
                site_disp=str(prazo),
                estoque_pa=0,
                msg_pa="INCLUIDO 0 ESTOQUE SEGURANÇA",
                msg_kit=f"PRAZO DEFINIDO {prazo} DIAS",
                msg_pai=f"PRAZO DEFINIDO {prazo} DIAS",
            )

    # =========================================
    # Final: converter dict -> lista por regra
    # =========================================
    final_actions_by_rule: Dict[RuleName, List[AthosAction]] = {}
    for rn in ORDERED_RULES:
        bucket = actions_by_rule[rn]
        final_actions_by_rule[rn] = list(bucket.values())

    return AthosOutputs(actions_by_rule=final_actions_by_rule, report_lines=report_lines)
