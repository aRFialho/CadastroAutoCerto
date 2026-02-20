"""Athos rules engine.

Regras de negócio para gerar as 5 planilhas do Robô Athos.

Pontos importantes (atualizados):
- Prazo do fornecedor: SEMPRE tentar usar o campo GRUPO_* (produto/kit/pai) se for numérico.
  Se estiver vazio ou não-numérico, usar supplier_prazo_lookup(marca).
- Para regras que dependem de ESTOQUE_REAL:
  * Se um KIT se repetir (mesmo CODBARRA_KIT em mais de uma linha), considere o estoque final do KIT
    (ESTOQUE_REAL_KIT) em vez do estoque do PA.
  * Essa lógica se aplica a todas as regras que precisam decidir por estoque.
- Em ENVIO_IMEDIATO: se algum componente estiver inativado (FORA_DE_LINHA) não exportar o KIT.

Este módulo NÃO escreve Excel; ele apenas produz linhas com chaves compatíveis com o template.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from ..utils.logger import get_logger

logger = get_logger("athos_rules")

SupplierPrazoLookup = Callable[[str], Optional[int]]


# =========================
# Models
# =========================

@dataclass(frozen=True)
class RowRef:
    """Uma linha do SQL já normalizada."""

    codbarra_produto: str
    codaux_produto: str
    complemento_produto: str
    estoque_real_produto: float
    prazo_produto: Optional[int]
    fabricante_produto: str
    grupo3_produto: str
    grupo_produto: str

    codbarra_kit: str
    codaux_kit: str
    complemento_kit: str
    prazo_kit: Optional[int]
    fabricante_kit: str
    estoque_real_kit: float
    grupo_kit: str

    codbarra_pai: str
    codaux_pai: str
    complemento_pai: str
    prazo_pai: Optional[int]
    fabricante_pai: str
    grupo_pai: str


@dataclass
class ReportEntry:
    ean: str
    codaux: str
    tipo: str  # PA | KIT | PAI
    marca: str
    grupo3: str
    grupo: str
    acao: str


@dataclass
class RuleOutput:
    name: str
    rows: List[Dict[str, Any]]


@dataclass
class AthosOutputs:
    rule_outputs: List[RuleOutput]
    report_lines: List[ReportEntry]


# =========================
# Helpers
# =========================

def _to_str(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _to_float(v: Any) -> float:
    try:
        if v is None:
            return 0.0
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip().replace(".", "").replace(",", ".")
        return float(s) if s else 0.0
    except Exception:
        return 0.0


def _parse_int_from_any(v: Any) -> Optional[int]:
    """Tenta extrair um inteiro de v (aceita número, texto, '15 dias', etc)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        # 3.0 -> 3
        try:
            return int(v)
        except Exception:
            return None
    s = str(v).strip()
    if not s:
        return None
    # achar primeiro bloco numérico
    import re

    m = re.search(r"-?\d+", s)
    if not m:
        return None
    try:
        return int(m.group(0))
    except Exception:
        return None


def _site_disp_from_days(days: Optional[int], site: Optional[Any] = None) -> str:
    """Regra de UI/site: se days==0 => 'Imediata'. Senão, se site fornecido, usa; senão usa '{days} dias'."""
    if days is None:
        return _to_str(site)
    if int(days) == 0:
        return "Imediata"
    if site is None or _to_str(site) == "":
        return f"{int(days)} dias"
    return _to_str(site)


def _prazo_fornecedor(
    grupo_field: Any,
    marca: str,
    supplier_prazo_lookup: Optional[SupplierPrazoLookup],
) -> Optional[int]:
    """Regra: se GRUPO_* for numérico, usa ele. Caso contrário, lookup no banco por marca."""
    n = _parse_int_from_any(grupo_field)
    if n is not None:
        return n
    if not marca:
        return None
    if supplier_prazo_lookup is None:
        return None
    try:
        return supplier_prazo_lookup(marca)
    except Exception:
        return None


def _brand_bucket(marca: str) -> str:
    m = (marca or "").strip().upper()
    if m in {"KONFORT", "CASA DO PUFF", "DIVINI DECOR", "LUMIL", "MADERATTO"}:
        return "IMEDIATA"
    if m in {"DMOV", "DMOV2"}:
        return "DMOV"
    if m == "DMOV - MP":
        return "DMOV_MP"
    return "OUTRAS"


# =========================
# Engine
# =========================

class AthosRulesEngine:
    """Aplica todas as regras e devolve as linhas para cada planilha."""

    def __init__(
        self,
        sql_rows: List[Dict[str, Any]],
        whitelist_imediatos: Set[str],
        supplier_prazo_lookup: Optional[SupplierPrazoLookup] = None,
    ):
        self.sql_rows = sql_rows
        self.whitelist_imediatos = whitelist_imediatos
        self.supplier_prazo_lookup = supplier_prazo_lookup

        self.rows: List[RowRef] = self._parse_sql_rows(sql_rows)
        self.kit_counts: Dict[str, int] = self._count_kits(self.rows)

    # ---------- parsing ----------

    def _parse_sql_rows(self, rows: List[Dict[str, Any]]) -> List[RowRef]:
        out: List[RowRef] = []

        # tolerância a nomes (case/underscore)
        def g(r: Dict[str, Any], key: str) -> Any:
            # tentativas
            if key in r:
                return r.get(key)
            # tentar variações
            for k in r.keys():
                if k.strip().lower() == key.strip().lower():
                    return r.get(k)
            return None

        for r in rows:
            out.append(
                RowRef(
                    codbarra_produto=_to_str(g(r, "CODBARRA_PRODUTO")),
                    codaux_produto=_to_str(g(r, "CODAUXILIAR_PRODUTO")),
                    complemento_produto=_to_str(g(r, "COMPLEMENTO_PRODUTO")),
                    estoque_real_produto=_to_float(g(r, "ESTOQUE_REAL_PRODUTO")),
                    prazo_produto=_parse_int_from_any(g(r, "PRAZO_PRODUTO")),
                    fabricante_produto=_to_str(g(r, "FABRICANTE_PRODUTO")),
                    grupo3_produto=_to_str(g(r, "NOME_GRUPO3")),
                    grupo_produto=_to_str(g(r, "GRUPO_PRODUTO")),

                    codbarra_kit=_to_str(g(r, "CODBARRA_KIT")),
                    codaux_kit=_to_str(g(r, "CODAUXILIAR_KIT")),
                    complemento_kit=_to_str(g(r, "COMPLEMENTO_KIT")),
                    prazo_kit=_parse_int_from_any(g(r, "PRAZO_KIT")),
                    fabricante_kit=_to_str(g(r, "FABRICANTE_KIT")),
                    estoque_real_kit=_to_float(g(r, "ESTOQUE_REAL_KIT")),
                    grupo_kit=_to_str(g(r, "GRUPO_KIT")),

                    codbarra_pai=_to_str(g(r, "CODBARRA_PAI")),
                    codaux_pai=_to_str(g(r, "CODAUXILIAR_PAI")),
                    complemento_pai=_to_str(g(r, "COMPLEMENTO_PAI")),
                    prazo_pai=_parse_int_from_any(g(r, "PRAZO_PAI")),
                    fabricante_pai=_to_str(g(r, "FABRICANTE_PAI")),
                    grupo_pai=_to_str(g(r, "GRUPO_PAI")),
                )
            )
        return out

    def _count_kits(self, rows: Iterable[RowRef]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for rr in rows:
            k = rr.codbarra_kit
            if not k:
                continue
            counts[k] = counts.get(k, 0) + 1
        return counts

    # ---------- stock helpers ----------

    def _effective_stock_for_pa(self, rr: RowRef) -> float:
        """Se o kit se repete, usar estoque do kit; senão, usar estoque do PA."""
        if rr.codbarra_kit and self.kit_counts.get(rr.codbarra_kit, 0) > 1:
            return rr.estoque_real_kit
        return rr.estoque_real_produto

    def _effective_stock_for_kit(self, rr: RowRef) -> float:
        return rr.estoque_real_kit

    def _kit_has_inactive_component(self, kit_code: str, inactive_components: Set[str]) -> bool:
        if not kit_code:
            return False
        for rr in self.rows:
            if rr.codbarra_kit == kit_code and rr.codbarra_produto in inactive_components:
                return True
        return False

    # ---------- parent/kit relationships ----------

    def _kits_by_parent(self) -> Dict[str, Set[str]]:
        m: Dict[str, Set[str]] = {}
        for rr in self.rows:
            if rr.codbarra_pai and rr.codbarra_kit:
                m.setdefault(rr.codbarra_pai, set()).add(rr.codbarra_kit)
        return m

    def _rows_for_kit(self, kit_code: str) -> List[RowRef]:
        return [r for r in self.rows if r.codbarra_kit == kit_code]

    def _any_row_for_code(self, code: str) -> Optional[RowRef]:
        for rr in self.rows:
            if rr.codbarra_produto == code or rr.codbarra_kit == code or rr.codbarra_pai == code:
                return rr
        return None

    # =========================
    # Public
    # =========================

    def apply_all(self) -> AthosOutputs:
        report: List[ReportEntry] = []

        # 1) Fora de linha (gera também lista de inativos p/ não vazarem para outras regras)
        fora = self._rule_fora_de_linha(report)
        inactive_components: Set[str] = set()
        for row in fora.rows:
            ean = _to_str(row.get("Código de Barras"))
            if ean:
                inactive_components.add(ean)

        # 2) Outros grupos
        estoque_comp = self._rule_estoque_compartilhado(report)
        envio = self._rule_envio_imediato(report, inactive_components=inactive_components)
        sem_grupo = self._rule_sem_grupo(report)
        outlet = self._rule_outlet(report)

        return AthosOutputs(
            rule_outputs=[fora, estoque_comp, envio, sem_grupo, outlet],
            report_lines=report,
        )

    # =========================
    # Rule: FORA_DE_LINHA
    # =========================

    def _rule_fora_de_linha(self, report: List[ReportEntry]) -> RuleOutput:
        rows_out: List[Dict[str, Any]] = []
        emitted: Set[str] = set()

        for rr in self.rows:
            if rr.grupo3_produto.strip().upper() != "FORA DE LINHA":
                continue

            avail = self._effective_stock_for_pa(rr)
            if avail > 0:
                continue

            targets = [
                (rr.codbarra_produto, rr.codaux_produto, "PA", rr.fabricante_produto, rr.grupo3_produto, rr.grupo_produto),
                (rr.codbarra_kit, rr.codaux_kit, "KIT", rr.fabricante_kit, rr.grupo3_produto, rr.grupo_kit),
                (rr.codbarra_pai, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo3_produto, rr.grupo_pai),
            ]
            for ean, codaux, tipo, marca, grupo3, grupo in targets:
                if not ean or ean in emitted:
                    continue
                emitted.add(ean)
                rows_out.append({
                    "Código de Barras": ean,
                    "Produto Inativo": "T",
                })
                report.append(ReportEntry(
                    ean=ean,
                    codaux=codaux,
                    tipo=tipo,
                    marca=marca,
                    grupo3=grupo3,
                    grupo=grupo,
                    acao="PRODUTO INATIVADO",
                ))

        return RuleOutput(name="FORA_DE_LINHA", rows=rows_out)

    # =========================
    # Rule: ESTOQUE_COMPARTILHADO
    # =========================

    def _rule_estoque_compartilhado(self, report: List[ReportEntry]) -> RuleOutput:
        """Sincroniza prazos entre kit e pai.

        Ajustes:
        - Dias para Entrega deve espelhar o Site Disponibilidade.
        - Não preencher Tipo Produto.
        """
        rows_out: List[Dict[str, Any]] = []
        emitted: Set[str] = set()

        # Para cada kit: copiar prazo do PA (prazo_produto) -> kit
        # Depois: pai recebe maior prazo entre seus kits
        kits_by_pai = self._kits_by_parent()

        kit_prazo: Dict[str, Optional[int]] = {}
        for rr in self.rows:
            if rr.grupo3_produto.strip().upper() != "ESTOQUE COMPARTILHADO":
                continue
            if not rr.codbarra_kit:
                continue
            # prazo do kit é o prazo do PA
            p = rr.prazo_produto
            if p is None:
                p = _prazo_fornecedor(rr.grupo_produto, rr.fabricante_produto, self.supplier_prazo_lookup)
            kit_prazo[rr.codbarra_kit] = p

        # escrever kits
        for kit, p in kit_prazo.items():
            if not kit or kit in emitted:
                continue
            emitted.add(kit)
            days = int(p) if p is not None else None
            rows_out.append({
                "Código de Barras": kit,
                "Dias para Entrega": days,
                "Site Disponibilidade": _site_disp_from_days(days),
            })
            rr_any = self._any_row_for_code(kit)
            report.append(ReportEntry(
                ean=kit,
                codaux=(rr_any.codaux_kit if rr_any else ""),
                tipo="KIT",
                marca=(rr_any.fabricante_kit if rr_any else ""),
                grupo3=(rr_any.grupo3_produto if rr_any else ""),
                grupo=(rr_any.grupo_kit if rr_any else ""),
                acao="SINCRONIZOU PRAZO DO PA",
            ))

        # pai = maior prazo dos kits
        for pai, kits in kits_by_pai.items():
            if not pai:
                continue
            prazos = [kit_prazo.get(k) for k in kits if kit_prazo.get(k) is not None]
            if not prazos:
                continue
            max_p = max(int(x) for x in prazos if x is not None)
            if pai in emitted:
                continue
            emitted.add(pai)
            rows_out.append({
                "Código de Barras": pai,
                "Dias para Entrega": int(max_p),
                "Site Disponibilidade": _site_disp_from_days(int(max_p)),
            })
            rr_any = self._any_row_for_code(pai)
            report.append(ReportEntry(
                ean=pai,
                codaux=(rr_any.codaux_pai if rr_any else ""),
                tipo="PAI",
                marca=(rr_any.fabricante_pai if rr_any else ""),
                grupo3=(rr_any.grupo3_produto if rr_any else ""),
                grupo=(rr_any.grupo_pai if rr_any else ""),
                acao="PAI RECEBEU MAIOR PRAZO DOS KITS",
            ))

        return RuleOutput(name="ESTOQUE_COMPARTILHADO", rows=rows_out)

    # =========================
    # Rule: ENVIO_IMEDIATO
    # =========================

    def _rule_envio_imediato(self, report: List[ReportEntry], inactive_components: Set[str]) -> RuleOutput:
        rows_out: List[Dict[str, Any]] = []
        emitted: Set[str] = set()

        kits_by_pai = self._kits_by_parent()

        # Pré-calcular estoque efetivo por kit (único)
        kit_stock: Dict[str, float] = {}
        kit_brand: Dict[str, str] = {}
        kit_group: Dict[str, str] = {}
        kit_codaux: Dict[str, str] = {}
        kit_pai: Dict[str, str] = {}

        for rr in self.rows:
            if rr.codbarra_kit:
                kit_stock[rr.codbarra_kit] = self._effective_stock_for_kit(rr)
                kit_brand[rr.codbarra_kit] = rr.fabricante_kit or rr.fabricante_produto
                kit_group[rr.codbarra_kit] = rr.grupo_kit
                kit_codaux[rr.codbarra_kit] = rr.codaux_kit
                if rr.codbarra_pai:
                    kit_pai[rr.codbarra_kit] = rr.codbarra_pai

        for rr in self.rows:
            if rr.grupo3_produto.strip().upper() != "ENVIO IMEDIATO":
                continue

            pa_code = rr.codbarra_produto
            kit_code = rr.codbarra_kit
            pai_code = rr.codbarra_pai

            if not pa_code:
                continue

            # 1) valida whitelist
            if pa_code not in self.whitelist_imediatos:
                if pa_code not in emitted:
                    emitted.add(pa_code)
                    rows_out.append({
                        "Código de Barras": pa_code,
                        "GRUPO3": "APAGAR",
                    })
                    report.append(ReportEntry(
                        ean=pa_code,
                        codaux=rr.codaux_produto,
                        tipo="PA",
                        marca=rr.fabricante_produto,
                        grupo3=rr.grupo3_produto,
                        grupo=rr.grupo_produto,
                        acao="RETIRADO DO GRUPO3 ENVIO IMEDIATO",
                    ))
                continue

            # 2) se kit tiver componente inativo, não exportar kit
            kit_inactive = False
            if kit_code:
                kit_inactive = self._kit_has_inactive_component(kit_code, inactive_components)

            bucket = _brand_bucket(rr.fabricante_produto)

            # estoque efetivo (PA ou KIT se repetir)
            effective_stock = self._effective_stock_for_pa(rr)
            has_stock = effective_stock > 0

            def emit_line(ean: str, codaux: str, tipo: str, marca: str, grupo3: str, grupo: str,
                          estoque_seg: Optional[int], dias: Optional[int], site: Optional[str], grupo3_value: Optional[str], acao: str):
                if not ean or ean in emitted:
                    return
                emitted.add(ean)
                row: Dict[str, Any] = {"Código de Barras": ean}
                if grupo3_value is not None:
                    row["GRUPO3"] = grupo3_value
                if grupo:
                    row["Grupo"] = grupo
                if estoque_seg is not None:
                    row["Estoque de Segurança"] = int(estoque_seg)
                if dias is not None:
                    row["Dias para Entrega"] = int(dias)
                if site is not None:
                    row["Site Disponibilidade"] = site
                else:
                    # derivar pelo padrão
                    if dias is not None:
                        row["Site Disponibilidade"] = _site_disp_from_days(dias)
                # regra global: dias==0 => Imediata
                if dias is not None and int(dias) == 0:
                    row["Site Disponibilidade"] = "Imediata"
                rows_out.append(row)
                report.append(ReportEntry(
                    ean=ean, codaux=codaux, tipo=tipo, marca=marca, grupo3=grupo3, grupo=grupo, acao=acao
                ))

            # ------------ cenários ------------
            if bucket == "DMOV":
                # Dmov2: se tem estoque -> 1000 / 3 dias; pai 3 se todos kits do pai com estoque; caso contrário prazo fornecedor
                if has_stock:
                    emit_line(
                        pa_code, rr.codaux_produto, "PA", rr.fabricante_produto, rr.grupo3_produto, rr.grupo_produto,
                        estoque_seg=1000, dias=3, site="3 dias", grupo3_value="", acao="INCLUIDO 1000 ESTOQUE SEG"
                    )
                    # kit só se não tiver componente inativo
                    if kit_code and not kit_inactive:
                        emit_line(
                            kit_code, rr.codaux_kit, "KIT", rr.fabricante_kit, rr.grupo3_produto, rr.grupo_kit,
                            estoque_seg=0, dias=3, site="3 dias", grupo3_value="", acao="KIT PRAZO 3 DIAS"
                        )

                    # pai
                    if pai_code:
                        kits = kits_by_pai.get(pai_code, set())
                        all_kits_stock = True
                        for k in kits:
                            if kit_stock.get(k, 0.0) <= 0:
                                all_kits_stock = False
                                break
                        if all_kits_stock:
                            emit_line(
                                pai_code, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo3_produto, rr.grupo_pai,
                                estoque_seg=0, dias=3, site="3 dias", grupo3_value="", acao="PAI PRAZO 3 DIAS"
                            )
                        else:
                            prazo = _prazo_fornecedor(rr.grupo_pai, rr.fabricante_pai, self.supplier_prazo_lookup)
                            emit_line(
                                pai_code, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo3_produto, rr.grupo_pai,
                                estoque_seg=0, dias=prazo, site=_site_disp_from_days(prazo), grupo3_value="", acao="PAI PRAZO FORNECEDOR"
                            )
                else:
                    # sem estoque: regra do pai/kit depende do fornecedor, mas não puxa PA como imediato
                    # (mantemos apenas pai/kit para refletir reposição, quando aplicável)
                    prazo = _prazo_fornecedor(rr.grupo_produto, rr.fabricante_produto, self.supplier_prazo_lookup)
                    if kit_code and not kit_inactive:
                        emit_line(
                            kit_code, rr.codaux_kit, "KIT", rr.fabricante_kit, rr.grupo3_produto, rr.grupo_kit,
                            estoque_seg=0, dias=prazo, site=_site_disp_from_days(prazo), grupo3_value="", acao="KIT PRAZO FORNECEDOR"
                        )
                    if pai_code:
                        prazo_pai = _prazo_fornecedor(rr.grupo_pai, rr.fabricante_pai, self.supplier_prazo_lookup)
                        emit_line(
                            pai_code, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo3_produto, rr.grupo_pai,
                            estoque_seg=0, dias=prazo_pai, site=_site_disp_from_days(prazo_pai), grupo3_value="", acao="PAI PRAZO FORNECEDOR"
                        )

            elif bucket == "IMEDIATA":
                if has_stock:
                    # tudo imediato 0 dias / estoque 0
                    emit_line(
                        pa_code, rr.codaux_produto, "PA", rr.fabricante_produto, rr.grupo3_produto, rr.grupo_produto,
                        estoque_seg=0, dias=0, site="Imediata", grupo3_value="", acao="IMEDIATA"
                    )
                    if kit_code and not kit_inactive:
                        emit_line(
                            kit_code, rr.codaux_kit, "KIT", rr.fabricante_kit, rr.grupo3_produto, rr.grupo_kit,
                            estoque_seg=0, dias=0, site="Imediata", grupo3_value="", acao="IMEDIATA"
                        )
                    if pai_code:
                        emit_line(
                            pai_code, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo3_produto, rr.grupo_pai,
                            estoque_seg=0, dias=0, site="Imediata", grupo3_value="", acao="IMEDIATA"
                        )
                else:
                    # sem estoque: se TODOS os kits do pai sem estoque => PA seg 1000 e prazo fornecedor para todos
                    prazo = _prazo_fornecedor(rr.grupo_produto, rr.fabricante_produto, self.supplier_prazo_lookup)
                    if pai_code:
                        kits = kits_by_pai.get(pai_code, set())
                        all_no_stock = True
                        for k in kits:
                            if kit_stock.get(k, 0.0) > 0:
                                all_no_stock = False
                                break
                        if all_no_stock:
                            emit_line(
                                pa_code, rr.codaux_produto, "PA", rr.fabricante_produto, rr.grupo3_produto, rr.grupo_produto,
                                estoque_seg=1000, dias=prazo, site=_site_disp_from_days(prazo), grupo3_value="", acao="INCLUIDO 1000 ESTOQUE SEG"
                            )
                            if kit_code and not kit_inactive:
                                emit_line(
                                    kit_code, rr.codaux_kit, "KIT", rr.fabricante_kit, rr.grupo3_produto, rr.grupo_kit,
                                    estoque_seg=0, dias=prazo, site=_site_disp_from_days(prazo), grupo3_value="", acao="KIT PRAZO FORNECEDOR"
                                )
                            emit_line(
                                pai_code, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo3_produto, rr.grupo_pai,
                                estoque_seg=0, dias=prazo, site=_site_disp_from_days(prazo), grupo3_value="", acao="PAI PRAZO FORNECEDOR"
                            )
                        else:
                            # pelo menos um kit com estoque: PAs sem estoque vão com prazo fornecedor; pai imediato
                            emit_line(
                                pa_code, rr.codaux_produto, "PA", rr.fabricante_produto, rr.grupo3_produto, rr.grupo_produto,
                                estoque_seg=0, dias=prazo, site=_site_disp_from_days(prazo), grupo3_value="", acao="PA PRAZO FORNECEDOR"
                            )
                            # pai imediato
                            emit_line(
                                pai_code, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo3_produto, rr.grupo_pai,
                                estoque_seg=0, dias=0, site="Imediata", grupo3_value="", acao="PAI IMEDIATA"
                            )

            else:
                # outras marcas
                if has_stock:
                    emit_line(
                        pa_code, rr.codaux_produto, "PA", rr.fabricante_produto, rr.grupo3_produto, rr.grupo_produto,
                        estoque_seg=0, dias=1, site="1 dia", grupo3_value="", acao="PRAZO 1 DIA"
                    )
                    if kit_code and not kit_inactive:
                        emit_line(
                            kit_code, rr.codaux_kit, "KIT", rr.fabricante_kit, rr.grupo3_produto, rr.grupo_kit,
                            estoque_seg=0, dias=1, site="1 dia", grupo3_value="", acao="PRAZO 1 DIA"
                        )
                    if pai_code:
                        emit_line(
                            pai_code, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo3_produto, rr.grupo_pai,
                            estoque_seg=0, dias=1, site="1 dia", grupo3_value="", acao="PRAZO 1 DIA"
                        )
                else:
                    prazo = _prazo_fornecedor(rr.grupo_produto, rr.fabricante_produto, self.supplier_prazo_lookup)
                    if pai_code:
                        kits = kits_by_pai.get(pai_code, set())
                        all_no_stock = True
                        for k in kits:
                            if kit_stock.get(k, 0.0) > 0:
                                all_no_stock = False
                                break
                        if all_no_stock:
                            emit_line(
                                pa_code, rr.codaux_produto, "PA", rr.fabricante_produto, rr.grupo3_produto, rr.grupo_produto,
                                estoque_seg=1000, dias=prazo, site=_site_disp_from_days(prazo), grupo3_value="", acao="INCLUIDO 1000 ESTOQUE SEG"
                            )
                            if kit_code and not kit_inactive:
                                emit_line(
                                    kit_code, rr.codaux_kit, "KIT", rr.fabricante_kit, rr.grupo3_produto, rr.grupo_kit,
                                    estoque_seg=0, dias=prazo, site=_site_disp_from_days(prazo), grupo3_value="", acao="KIT PRAZO FORNECEDOR"
                                )
                            emit_line(
                                pai_code, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo3_produto, rr.grupo_pai,
                                estoque_seg=0, dias=prazo, site=_site_disp_from_days(prazo), grupo3_value="", acao="PAI PRAZO FORNECEDOR"
                            )
                        else:
                            emit_line(
                                pa_code, rr.codaux_produto, "PA", rr.fabricante_produto, rr.grupo3_produto, rr.grupo_produto,
                                estoque_seg=0, dias=prazo, site=_site_disp_from_days(prazo), grupo3_value="", acao="PA PRAZO FORNECEDOR"
                            )
                            emit_line(
                                pai_code, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo3_produto, rr.grupo_pai,
                                estoque_seg=0, dias=1, site="1 dia", grupo3_value="", acao="PAI PRAZO 1 DIA"
                            )

        return RuleOutput(name="ENVIO_IMEDIATO", rows=rows_out)

    # =========================
    # Rule: SEM_GRUPO
    # =========================

    def _rule_sem_grupo(self, report: List[ReportEntry]) -> RuleOutput:
        rows_out: List[Dict[str, Any]] = []
        emitted: Set[str] = set()

        for rr in self.rows:
            if rr.grupo3_produto.strip().upper() not in {"", "SEM GRUPO", "SEM NENHUM GRUPO", "NENHUM GRUPO"}:
                continue

            # filtros iniciais
            if not rr.fabricante_produto.strip():
                continue
            if _brand_bucket(rr.fabricante_produto) == "DMOV_MP":
                continue

            avail = self._effective_stock_for_pa(rr)

            # helper para emitir
            def emit(ean: str, codaux: str, tipo: str, marca: str, grupo3_value: str, grupo: str,
                     estoque_seg: Optional[int], dias: Optional[int], acao: str):
                if not ean or ean in emitted:
                    return
                emitted.add(ean)
                row: Dict[str, Any] = {"Código de Barras": ean}
                if grupo3_value:
                    row["GRUPO3"] = grupo3_value
                if grupo:
                    row["Grupo"] = grupo
                if estoque_seg is not None:
                    row["Estoque de Segurança"] = int(estoque_seg)
                if dias is not None:
                    row["Dias para Entrega"] = int(dias)
                if dias is not None:
                    row["Site Disponibilidade"] = _site_disp_from_days(dias)
                rows_out.append(row)
                report.append(ReportEntry(
                    ean=ean, codaux=codaux, tipo=tipo, marca=marca, grupo3=rr.grupo3_produto, grupo=grupo, acao=acao
                ))

            if avail > 0:
                # reclassificar via whitelist (controla tudo por banco/lista)
                if rr.codbarra_produto in self.whitelist_imediatos:
                    emit(rr.codbarra_produto, rr.codaux_produto, "PA", rr.fabricante_produto, "ENVIO IMEDIATO", rr.grupo_produto,
                         estoque_seg=0, dias=0, acao="RECLASSIFICADO PARA ENVIO IMEDIATO")
                else:
                    emit(rr.codbarra_produto, rr.codaux_produto, "PA", rr.fabricante_produto, "OUTLET", rr.grupo_produto,
                         estoque_seg=0, dias=1, acao="RECLASSIFICADO PARA OUTLET")
            else:
                # sem estoque: PA seg 1000 e prazo fornecedor nos kits/pai
                prazo = _prazo_fornecedor(rr.grupo_produto, rr.fabricante_produto, self.supplier_prazo_lookup)
                emit(rr.codbarra_produto, rr.codaux_produto, "PA", rr.fabricante_produto, "", rr.grupo_produto,
                     estoque_seg=1000, dias=None, acao="INCLUIDO 1000 ESTOQUE SEG")
                if rr.codbarra_kit:
                    prazo_kit = _prazo_fornecedor(rr.grupo_kit, rr.fabricante_kit or rr.fabricante_produto, self.supplier_prazo_lookup)
                    emit(rr.codbarra_kit, rr.codaux_kit, "KIT", rr.fabricante_kit, "", rr.grupo_kit,
                         estoque_seg=0, dias=prazo_kit, acao="KIT PRAZO FORNECEDOR")
                if rr.codbarra_pai:
                    prazo_pai = _prazo_fornecedor(rr.grupo_pai, rr.fabricante_pai or rr.fabricante_produto, self.supplier_prazo_lookup)
                    emit(rr.codbarra_pai, rr.codaux_pai, "PAI", rr.fabricante_pai, "", rr.grupo_pai,
                         estoque_seg=0, dias=prazo_pai, acao="PAI PRAZO FORNECEDOR")

        return RuleOutput(name="SEM_GRUPO", rows=rows_out)

    # =========================
    # Rule: OUTLET
    # =========================

    def _rule_outlet(self, report: List[ReportEntry]) -> RuleOutput:
        rows_out: List[Dict[str, Any]] = []
        emitted: Set[str] = set()

        kits_by_pai = self._kits_by_parent()

        for rr in self.rows:
            if rr.grupo3_produto.strip().upper() != "OUTLET":
                continue

            avail = self._effective_stock_for_pa(rr)
            bucket = _brand_bucket(rr.fabricante_produto)

            def emit(ean: str, codaux: str, tipo: str, marca: str, grupo: str,
                     estoque_seg: Optional[int], dias: Optional[int], site: Optional[str], acao: str):
                if not ean or ean in emitted:
                    return
                emitted.add(ean)
                row: Dict[str, Any] = {"Código de Barras": ean}
                if grupo:
                    row["Grupo"] = grupo
                if estoque_seg is not None:
                    row["Estoque de Segurança"] = int(estoque_seg)
                if dias is not None:
                    row["Dias para Entrega"] = int(dias)
                # Site
                if dias is not None and int(dias) == 0:
                    row["Site Disponibilidade"] = "Imediata"
                else:
                    row["Site Disponibilidade"] = site if site is not None else _site_disp_from_days(dias)
                rows_out.append(row)
                report.append(ReportEntry(
                    ean=ean, codaux=codaux, tipo=tipo, marca=marca, grupo3=rr.grupo3_produto, grupo=grupo, acao=acao
                ))

            if avail <= 0:
                # sem estoque: PA seg 1000, kit/pai seg 0, todos com prazo fornecedor
                prazo_pa = _prazo_fornecedor(rr.grupo_produto, rr.fabricante_produto, self.supplier_prazo_lookup)
                prazo_kit = _prazo_fornecedor(rr.grupo_kit, rr.fabricante_kit or rr.fabricante_produto, self.supplier_prazo_lookup)
                prazo_pai = _prazo_fornecedor(rr.grupo_pai, rr.fabricante_pai or rr.fabricante_produto, self.supplier_prazo_lookup)

                emit(rr.codbarra_produto, rr.codaux_produto, "PA", rr.fabricante_produto, rr.grupo_produto,
                     estoque_seg=1000, dias=prazo_pa, site=_site_disp_from_days(prazo_pa), acao="INCLUIDO 1000 ESTOQUE SEG")
                if rr.codbarra_kit:
                    emit(rr.codbarra_kit, rr.codaux_kit, "KIT", rr.fabricante_kit, rr.grupo_kit,
                         estoque_seg=0, dias=prazo_kit, site=_site_disp_from_days(prazo_kit), acao="INCLUIDO 0 ESTOQUE SEGURANÇA")
                if rr.codbarra_pai:
                    emit(rr.codbarra_pai, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo_pai,
                         estoque_seg=0, dias=prazo_pai, site=_site_disp_from_days(prazo_pai), acao="PAI PRAZO FORNECEDOR")

            else:
                # com estoque: depende da marca
                if bucket == "IMEDIATA":
                    emit(rr.codbarra_produto, rr.codaux_produto, "PA", rr.fabricante_produto, rr.grupo_produto,
                         estoque_seg=0, dias=0, site="Imediata", acao="IMEDIATA")
                    if rr.codbarra_kit:
                        emit(rr.codbarra_kit, rr.codaux_kit, "KIT", rr.fabricante_kit, rr.grupo_kit,
                             estoque_seg=0, dias=0, site="Imediata", acao="IMEDIATA")

                    # pai: se algum kit sem estoque => prazo fornecedor
                    if rr.codbarra_pai:
                        kits = kits_by_pai.get(rr.codbarra_pai, set())
                        any_no_stock = any(
                            (self._effective_stock_for_kit(self._rows_for_kit(k)[0]) if self._rows_for_kit(k) else 0.0) <= 0
                            for k in kits
                        )
                        if any_no_stock:
                            prazo_pai = _prazo_fornecedor(rr.grupo_pai, rr.fabricante_pai, self.supplier_prazo_lookup)
                            emit(rr.codbarra_pai, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo_pai,
                                 estoque_seg=0, dias=prazo_pai, site=_site_disp_from_days(prazo_pai), acao="PAI PRAZO FORNECEDOR")
                        else:
                            emit(rr.codbarra_pai, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo_pai,
                                 estoque_seg=0, dias=0, site="Imediata", acao="PAI IMEDIATA")

                elif bucket == "DMOV":
                    emit(rr.codbarra_produto, rr.codaux_produto, "PA", rr.fabricante_produto, rr.grupo_produto,
                         estoque_seg=0, dias=3, site="3 dias", acao="PRAZO 3 DIAS")
                    if rr.codbarra_kit:
                        emit(rr.codbarra_kit, rr.codaux_kit, "KIT", rr.fabricante_kit, rr.grupo_kit,
                             estoque_seg=0, dias=3, site="3 dias", acao="PRAZO 3 DIAS")
                    if rr.codbarra_pai:
                        kits = kits_by_pai.get(rr.codbarra_pai, set())
                        all_kits_stock = all(
                            (self._rows_for_kit(k)[0].estoque_real_kit if self._rows_for_kit(k) else 0.0) > 0
                            for k in kits
                        )
                        if all_kits_stock:
                            emit(rr.codbarra_pai, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo_pai,
                                 estoque_seg=0, dias=3, site="3 dias", acao="PAI PRAZO 3 DIAS")
                        else:
                            prazo_pai = _prazo_fornecedor(rr.grupo_pai, rr.fabricante_pai, self.supplier_prazo_lookup)
                            emit(rr.codbarra_pai, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo_pai,
                                 estoque_seg=0, dias=prazo_pai, site=_site_disp_from_days(prazo_pai), acao="PAI PRAZO FORNECEDOR")
                else:
                    emit(rr.codbarra_produto, rr.codaux_produto, "PA", rr.fabricante_produto, rr.grupo_produto,
                         estoque_seg=0, dias=1, site="1 dia", acao="PRAZO 1 DIA")
                    if rr.codbarra_kit:
                        emit(rr.codbarra_kit, rr.codaux_kit, "KIT", rr.fabricante_kit, rr.grupo_kit,
                             estoque_seg=0, dias=1, site="1 dia", acao="PRAZO 1 DIA")
                    if rr.codbarra_pai:
                        kits = kits_by_pai.get(rr.codbarra_pai, set())
                        all_kits_stock = all(
                            (self._rows_for_kit(k)[0].estoque_real_kit if self._rows_for_kit(k) else 0.0) > 0
                            for k in kits
                        )
                        if all_kits_stock:
                            emit(rr.codbarra_pai, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo_pai,
                                 estoque_seg=0, dias=1, site="1 dia", acao="PAI PRAZO 1 DIA")
                        else:
                            prazo_pai = _prazo_fornecedor(rr.grupo_pai, rr.fabricante_pai, self.supplier_prazo_lookup)
                            emit(rr.codbarra_pai, rr.codaux_pai, "PAI", rr.fabricante_pai, rr.grupo_pai,
                                 estoque_seg=0, dias=prazo_pai, site=_site_disp_from_days(prazo_pai), acao="PAI PRAZO FORNECEDOR")

        return RuleOutput(name="OUTLET", rows=rows_out)
