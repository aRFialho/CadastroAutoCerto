"""
Motor de Regras — Robô Athos

- Interpreta linhas do export do SQL (lista de dicts)
- Aplica todas as regras (FORA DE LINHA / ESTOQUE COMPARTILHADO / ENVIO IMEDIATO / SEM GRUPO / OUTLET)
- Retorna linhas no formato "template-friendly" (preencher SOMENTE a aba PRODUTOS)
- Gera relatório consolidado: EAN | TIPO(PA/KIT/PAI) | MARCA | GRUPO3 | AÇÃO
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set
import re


@dataclass
class ReportLine:
    ean: str
    tipo: str  # "PA" | "KIT" | "PAI"
    marca: str
    grupo3: str
    acao: str


@dataclass
class RuleOutput:
    rows: List[Dict[str, Any]]
    report: List[ReportLine]


class AthosRulesEngine:
    RULE_KEYS = [
        "FORA_DE_LINHA",
        "ESTOQUE_COMPARTILHADO",
        "ENVIO_IMEDIATO",
        "SEM_GRUPO",
        "OUTLET",
    ]

    BRANDS_IMEDIATA = {
        "KONFORT",
        "CASA DO PUFF",
        "DIVINI DECOR",
        "LUMIL",
        "MADERATTO",
    }

    BRANDS_SKIP_TO_ESTOQUE_COMP = {
        "MOVEIS VILA RICA",
        "COLIBRI MOVEIS",
        "MADETEC",
        "CAEMMUN",
        "LINEA BRASIL",
    }

    BRANDS_3_DIAS = {"DMOV", "DMOV2"}

    def apply_all(
        self,
        sql_rows: List[Dict[str, Any]],
        whitelist_eans: Optional[Set[str]] = None,
    ) -> Dict[str, RuleOutput]:
        whitelist_eans = whitelist_eans or set()
        items = [self._normalize_sql_row(r) for r in sql_rows if r]
        by_pai = self._group_by_pai(items)

        out: Dict[str, RuleOutput] = {}
        out["FORA_DE_LINHA"] = self._rule_fora_de_linha(items)
        out["ESTOQUE_COMPARTILHADO"] = self._rule_estoque_compartilhado(items)
        out["ENVIO_IMEDIATO"] = self._rule_envio_imediato(items, whitelist_eans, by_pai)
        out["SEM_GRUPO"] = self._rule_sem_grupo(items, whitelist_eans)
        out["OUTLET"] = self._rule_outlet(items)
        return out

    # =========================
    # 01 — FORA DE LINHA
    # =========================
    def _rule_fora_de_linha(self, items: List[Dict[str, Any]]) -> RuleOutput:
        rows: List[Dict[str, Any]] = []
        report: List[ReportLine] = []

        for it in items:
            pa_ean = self._ean(it.get("codbarra_produto"))
            if not pa_ean:
                continue

            pa_disp = self._as_float(it.get("estoque_real_produto"), default=0.0)
            if pa_disp > 0:
                continue

            g3 = self._str(it.get("nome_grupo3")) or ""
            pa_marca = self._brand(it.get("fabricante_produto"))

            rows.append({"COD_BARRA": pa_ean, "TIPO": "PA", "PRODUTO_INATIVO": "T"})
            report.append(ReportLine(pa_ean, "PA", pa_marca, g3, "PRODUTO INATIVADO"))

            kit_ean = self._ean(it.get("codbarra_kit"))
            if kit_ean:
                kit_marca = self._brand(it.get("fabricante_kit"))
                rows.append({"COD_BARRA": kit_ean, "TIPO": "KIT", "PRODUTO_INATIVO": "T"})
                report.append(ReportLine(kit_ean, "KIT", kit_marca, g3, "PRODUTO INATIVADO"))

            pai_ean = self._ean(it.get("codbarra_pai"))
            if pai_ean:
                pai_marca = self._brand(it.get("fabricante_pai"))
                rows.append({"COD_BARRA": pai_ean, "TIPO": "PAI", "PRODUTO_INATIVO": "T"})
                report.append(ReportLine(pai_ean, "PAI", pai_marca, g3, "PRODUTO INATIVADO"))

        return RuleOutput(rows=self._dedupe_keep_first(rows), report=report)

    # =========================
    # 02 — ESTOQUE COMPARTILHADO
    # =========================
    def _rule_estoque_compartilhado(self, items: List[Dict[str, Any]]) -> RuleOutput:
        rows: List[Dict[str, Any]] = []
        report: List[ReportLine] = []

        pai_max_prazo: Dict[str, int] = {}
        pai_brand: Dict[str, str] = {}

        for it in items:
            if self._upper(it.get("nome_grupo3")) != "ESTOQUE COMPARTILHADO":
                continue

            pa_prazo = self._as_int(it.get("prazo_produto"), default=0)
            grupo3 = "ESTOQUE COMPARTILHADO"

            kit_ean = self._ean(it.get("codbarra_kit"))
            if kit_ean:
                kit_marca = self._brand(it.get("fabricante_kit"))
                rows.append(self._row_prazo(kit_ean, tipo="KIT", grupo3=None, prazo=pa_prazo, estoque_seg=None, imediata=False))
                report.append(ReportLine(kit_ean, "KIT", kit_marca, grupo3, f"PRAZO = {pa_prazo} (MESMO DO PA)"))

            pai_ean = self._ean(it.get("codbarra_pai"))
            if pai_ean:
                cur = pai_max_prazo.get(pai_ean)
                pai_max_prazo[pai_ean] = pa_prazo if cur is None else max(cur, pa_prazo)
                pai_brand[pai_ean] = self._brand(it.get("fabricante_pai")) or pai_brand.get(pai_ean, "")

        for pai_ean, max_prazo in pai_max_prazo.items():
            rows.append(self._row_prazo(pai_ean, tipo="PAI", grupo3=None, prazo=max_prazo, estoque_seg=None, imediata=False))
            report.append(
                ReportLine(
                    pai_ean,
                    "PAI",
                    pai_brand.get(pai_ean, ""),
                    "ESTOQUE COMPARTILHADO",
                    f"PAI PRAZO = {max_prazo} (MAIOR ENTRE KITS/PA DO PAI)",
                )
            )

        return RuleOutput(rows=self._dedupe_keep_first(rows), report=report)

    # =========================
    # 03 — ENVIO IMEDIATO
    # =========================
    def _rule_envio_imediato(
        self,
        items: List[Dict[str, Any]],
        whitelist: Set[str],
        by_pai: Dict[str, List[Dict[str, Any]]],
    ) -> RuleOutput:
        rows: List[Dict[str, Any]] = []
        report: List[ReportLine] = []

        need_imediato = set(self._ean(x) for x in whitelist if self._ean(x))

        # Detecta PAI "skip"
        pai_skip: Set[str] = set()
        for pai_ean, group_items in by_pai.items():
            if not pai_ean:
                continue

            marcas = []
            for it in group_items:
                marcas.append(self._brand(it.get("fabricante_produto")))
                marcas.append(self._brand(it.get("fabricante_pai")))
            marcas = [m for m in marcas if m]
            marca = marcas[0] if marcas else ""

            if self._upper(marca) not in self.BRANDS_SKIP_TO_ESTOQUE_COMP:
                continue

            all_le_zero = True
            pa_eans = set()
            for it in group_items:
                pa_ean = self._ean(it.get("codbarra_produto"))
                if not pa_ean:
                    continue
                pa_eans.add(pa_ean)
                if self._as_float(it.get("estoque_real_produto"), default=0.0) > 0:
                    all_le_zero = False
                    break

            if all_le_zero and pa_eans:
                pai_skip.add(pai_ean)

        for it in items:
            pa_ean = self._ean(it.get("codbarra_produto"))
            if not pa_ean:
                continue

            marca_pa = self._brand(it.get("fabricante_produto"))
            marca_up = self._upper(marca_pa)

            g3_raw = self._str(it.get("nome_grupo3")) or ""
            g3_up = g3_raw.strip().upper()

            pai_ean = self._ean(it.get("codbarra_pai"))

            # Regra especial (não atualiza)
            if pai_ean and pai_ean in pai_skip:
                if pa_ean in need_imediato or g3_up == "ENVIO IMEDIATO":
                    report.append(
                        ReportLine(
                            pa_ean,
                            "PA",
                            marca_pa,
                            g3_raw,
                            "Colocar cód Fabricante, mudar para Estoque Compartilhado",
                        )
                    )
                continue

            in_whitelist = pa_ean in need_imediato
            in_group = (g3_up == "ENVIO IMEDIATO")

            if not in_whitelist and not in_group:
                continue

            if marca_up in self.BRANDS_IMEDIATA:
                imediata = True
                prazo = 0
                estoque_seg_pa = 0
            elif marca_up in self.BRANDS_3_DIAS:
                imediata = False
                prazo = 3
                estoque_seg_pa = 1000
            else:
                imediata = False
                prazo = 1
                estoque_seg_pa = 0

            # Remover do grupo
            if in_group and not in_whitelist:
                rows.append({
                    "COD_BARRA": pa_ean,
                    "TIPO": "PA",
                    "GRUPO3": "",
                    "GRUPO3_APAGAR": "X",
                    **self._row_prazo_dict(prazo=prazo, imediata=imediata),
                })
                report.append(ReportLine(pa_ean, "PA", marca_pa, g3_raw, "RETIRADO DO GRUPO3 ENVIO IMEDIATO"))
                continue

            # Adicionar/garantir no grupo
            if in_whitelist:
                rows.append(self._row_prazo(pa_ean, tipo="PA", grupo3="ENVIO IMEDIATO", prazo=prazo, estoque_seg=estoque_seg_pa, imediata=imediata))
                report.append(ReportLine(pa_ean, "PA", marca_pa, g3_raw, f"INCLUIDO NO GRUPO3 ENVIO IMEDIATO + PRAZO {('IMEDIATA' if imediata else prazo)} + ESTOQUE_SEG {estoque_seg_pa}"))

                kit_ean = self._ean(it.get("codbarra_kit"))
                if kit_ean:
                    marca_kit = self._brand(it.get("fabricante_kit"))
                    rows.append(self._row_prazo(kit_ean, tipo="KIT", grupo3="ENVIO IMEDIATO", prazo=prazo, estoque_seg=None, imediata=imediata))
                    report.append(ReportLine(kit_ean, "KIT", marca_kit, g3_raw, f"ALINHADO COM PA (GRUPO3 + PRAZO {('IMEDIATA' if imediata else prazo)})"))

                if pai_ean:
                    marca_pai = self._brand(it.get("fabricante_pai"))
                    rows.append(self._row_prazo(pai_ean, tipo="PAI", grupo3="ENVIO IMEDIATO", prazo=prazo, estoque_seg=None, imediata=imediata))
                    report.append(ReportLine(pai_ean, "PAI", marca_pai, g3_raw, f"ALINHADO COM PA (GRUPO3 + PRAZO {('IMEDIATA' if imediata else prazo)})"))

        return RuleOutput(rows=self._dedupe_keep_first(rows), report=report)

    # =========================
    # 04 — SEM GRUPO
    # =========================
    def _rule_sem_grupo(self, items: List[Dict[str, Any]], whitelist: Set[str]) -> RuleOutput:
        rows: List[Dict[str, Any]] = []
        report: List[ReportLine] = []

        whitelist_eans = set(self._ean(x) for x in whitelist if self._ean(x))

        for it in items:
            g3 = self._str(it.get("nome_grupo3"))
            if g3 and g3.strip():
                continue

            pa_ean = self._ean(it.get("codbarra_produto"))
            if not pa_ean:
                continue

            marca = self._brand(it.get("fabricante_produto"))
            if not marca:
                continue

            pa_disp = self._as_float(it.get("estoque_real_produto"), default=0.0)
            pa_prazo = self._as_int(it.get("prazo_produto"), default=1)

            kit_ean = self._ean(it.get("codbarra_kit"))
            pai_ean = self._ean(it.get("codbarra_pai"))
            marca_kit = self._brand(it.get("fabricante_kit"))
            marca_pai = self._brand(it.get("fabricante_pai"))

            if pa_disp > 0:
                if pa_ean in whitelist_eans:
                    rows.append(self._row_prazo(pa_ean, tipo="PA", grupo3="ENVIO IMEDIATO", prazo=0, estoque_seg=0, imediata=True))
                    report.append(ReportLine(pa_ean, "PA", marca, "", "SEM GRUPO → ENVIO IMEDIATO (IMEDIATA)"))

                    if kit_ean:
                        rows.append(self._row_prazo(kit_ean, tipo="KIT", grupo3="ENVIO IMEDIATO", prazo=0, estoque_seg=None, imediata=True))
                        report.append(ReportLine(kit_ean, "KIT", marca_kit, "", "ALINHADO COM PA (IMEDIATA)"))
                    if pai_ean:
                        rows.append(self._row_prazo(pai_ean, tipo="PAI", grupo3="ENVIO IMEDIATO", prazo=0, estoque_seg=None, imediata=True))
                        report.append(ReportLine(pai_ean, "PAI", marca_pai, "", "ALINHADO COM PA (IMEDIATA)"))
                else:
                    rows.append(self._row_prazo(pa_ean, tipo="PA", grupo3="OUTLET", prazo=1, estoque_seg=0, imediata=False))
                    report.append(ReportLine(pa_ean, "PA", marca, "", "SEM GRUPO → OUTLET (1 dia)"))

                    if kit_ean:
                        rows.append(self._row_prazo(kit_ean, tipo="KIT", grupo3="OUTLET", prazo=1, estoque_seg=None, imediata=False))
                        report.append(ReportLine(kit_ean, "KIT", marca_kit, "", "ALINHADO COM PA (OUTLET 1 dia)"))
                    if pai_ean:
                        rows.append(self._row_prazo(pai_ean, tipo="PAI", grupo3="OUTLET", prazo=1, estoque_seg=None, imediata=False))
                        report.append(ReportLine(pai_ean, "PAI", marca_pai, "", "ALINHADO COM PA (OUTLET 1 dia)"))
            else:
                rows.append(self._row_prazo(pa_ean, tipo="PA", grupo3=None, prazo=pa_prazo, estoque_seg=1000, imediata=False))
                report.append(ReportLine(pa_ean, "PA", marca, "", "SEM GRUPO + PA<=0 → INCLUIDO 1000 ESTOQUE SEG"))

                if kit_ean:
                    rows.append(self._row_prazo(kit_ean, tipo="KIT", grupo3=None, prazo=pa_prazo, estoque_seg=None, imediata=False))
                    report.append(ReportLine(kit_ean, "KIT", marca_kit, "", f"PA<=0 → PRAZO FORNECEDOR {pa_prazo}"))
                if pai_ean:
                    rows.append(self._row_prazo(pai_ean, tipo="PAI", grupo3=None, prazo=pa_prazo, estoque_seg=None, imediata=False))
                    report.append(ReportLine(pai_ean, "PAI", marca_pai, "", f"PA<=0 → PRAZO FORNECEDOR {pa_prazo}"))

        return RuleOutput(rows=self._dedupe_keep_first(rows), report=report)

    # =========================
    # 05 — OUTLET
    # =========================
    def _rule_outlet(self, items: List[Dict[str, Any]]) -> RuleOutput:
        rows: List[Dict[str, Any]] = []
        report: List[ReportLine] = []

        for it in items:
            if self._upper(it.get("nome_grupo3")) != "OUTLET":
                continue

            pa_ean = self._ean(it.get("codbarra_produto"))
            if not pa_ean:
                continue

            marca = self._brand(it.get("fabricante_produto"))
            marca_up = self._upper(marca)

            pa_disp = self._as_float(it.get("estoque_real_produto"), default=0.0)
            pa_prazo_fornecedor = self._as_int(it.get("prazo_produto"), default=1)

            kit_ean = self._ean(it.get("codbarra_kit"))
            pai_ean = self._ean(it.get("codbarra_pai"))
            marca_kit = self._brand(it.get("fabricante_kit"))
            marca_pai = self._brand(it.get("fabricante_pai"))

            if pa_disp <= 0:
                prazo = pa_prazo_fornecedor
                imediata = False

                rows.append(self._row_prazo(pa_ean, tipo="PA", grupo3="OUTLET", prazo=prazo, estoque_seg=1000, imediata=imediata))
                report.append(ReportLine(pa_ean, "PA", marca, "OUTLET", "INCLUIDO 1000 ESTOQUE SEG"))

                if kit_ean:
                    rows.append(self._row_prazo(kit_ean, tipo="KIT", grupo3="OUTLET", prazo=prazo, estoque_seg=None, imediata=imediata))
                    report.append(ReportLine(kit_ean, "KIT", marca_kit, "OUTLET", f"PRAZO FORNECEDOR {prazo}"))
                if pai_ean:
                    rows.append(self._row_prazo(pai_ean, tipo="PAI", grupo3="OUTLET", prazo=prazo, estoque_seg=None, imediata=imediata))
                    report.append(ReportLine(pai_ean, "PAI", marca_pai, "OUTLET", f"PRAZO FORNECEDOR {prazo}"))

            else:
                if marca_up in self.BRANDS_IMEDIATA:
                    prazo = 0
                    imediata = True
                elif marca_up in self.BRANDS_3_DIAS:
                    prazo = 3
                    imediata = False
                else:
                    prazo = 1
                    imediata = False

                rows.append(self._row_prazo(pa_ean, tipo="PA", grupo3="OUTLET", prazo=prazo, estoque_seg=0, imediata=imediata))
                report.append(ReportLine(pa_ean, "PA", marca, "OUTLET", f"INCLUIDO 0 ESTOQUE SEGURANÇA + PRAZO {('IMEDIATA' if imediata else prazo)}"))

                if kit_ean:
                    rows.append(self._row_prazo(kit_ean, tipo="KIT", grupo3="OUTLET", prazo=prazo, estoque_seg=None, imediata=imediata))
                    report.append(ReportLine(kit_ean, "KIT", marca_kit, "OUTLET", f"ALINHADO COM PA (PRAZO {('IMEDIATA' if imediata else prazo)})"))
                if pai_ean:
                    rows.append(self._row_prazo(pai_ean, tipo="PAI", grupo3="OUTLET", prazo=prazo, estoque_seg=None, imediata=imediata))
                    report.append(ReportLine(pai_ean, "PAI", marca_pai, "OUTLET", f"ALINHADO COM PA (PRAZO {('IMEDIATA' if imediata else prazo)})"))

        return RuleOutput(rows=self._dedupe_keep_first(rows), report=report)

    # =========================
    # Helpers
    # =========================
    def _group_by_pai(self, items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        for it in items:
            pai = self._ean(it.get("codbarra_pai"))
            if not pai:
                continue
            out.setdefault(pai, []).append(it)
        return out

    def _normalize_sql_row(self, r: Dict[str, Any]) -> Dict[str, Any]:
        rr: Dict[str, Any] = {}
        for k, v in r.items():
            if k is None:
                continue
            rr[str(k).strip()] = v
        return rr

    def _dedupe_keep_first(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        out: List[Dict[str, Any]] = []
        for r in rows:
            ean = self._ean(r.get("COD_BARRA"))
            if not ean:
                continue
            if ean in seen:
                continue
            seen.add(ean)
            out.append(r)
        return out

    def _row_prazo_dict(self, prazo: int, imediata: bool) -> Dict[str, Any]:
        if imediata:
            return {"DATA_ENTREGA": 0, "SITE_DISPONIBILIDADE": "IMEDIATA"}
        return {"DATA_ENTREGA": int(prazo), "SITE_DISPONIBILIDADE": int(prazo)}

    def _row_prazo(
        self,
        ean: str,
        tipo: str,  # "PA" | "KIT" | "PAI"
        grupo3: Optional[str],
        prazo: int,
        estoque_seg: Optional[int],
        imediata: bool,
    ) -> Dict[str, Any]:
        d: Dict[str, Any] = {"COD_BARRA": self._ean(ean), "TIPO": tipo}
        if grupo3 is not None:
            d["GRUPO3"] = grupo3
        if estoque_seg is not None:
            d["ESTOQUE_SEG"] = int(estoque_seg)
        d.update(self._row_prazo_dict(prazo=prazo, imediata=imediata))
        return d

    def _ean(self, v: Any) -> str:
        if v is None:
            return ""
        s = str(v).strip()
        if not s:
            return ""
        if s.endswith(".0"):
            try:
                s = str(int(float(s)))
            except Exception:
                pass
        return s.strip()

    def _str(self, v: Any) -> str:
        return "" if v is None else str(v).strip()

    def _upper(self, v: Any) -> str:
        return self._str(v).upper()

    def _brand(self, v: Any) -> str:
        s = self._str(v)
        s = re.sub(r"\s+", " ", s).strip()
        return s.upper()

    def _as_int(self, v: Any, default: int = 0) -> int:
        if v is None:
            return default
        try:
            if isinstance(v, (int, float)):
                return int(v)
            s = str(v).strip()
            if not s:
                return default
            digits = "".join(ch for ch in s if ch.isdigit())
            return int(digits) if digits else default
        except Exception:
            return default

    def _as_float(self, v: Any, default: float = 0.0) -> float:
        if v is None:
            return default
        try:
            if isinstance(v, (int, float)):
                return float(v)
            s = str(v).strip().replace(",", ".")
            return float(s) if s else default
        except Exception:
            return default
