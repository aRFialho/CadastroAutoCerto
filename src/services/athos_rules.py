# (o arquivo é grande — como você pediu “completo atualizado”, eu mando ele inteiro.)
# Se você preferir, eu te mando só o patch/diff pra aplicar.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
import re


SupplierPrazoLookup = Callable[[str], Optional[int]]


@dataclass
class ReportLine:
    codbarra: str
    tipo: str
    marca: str
    grupo3: str
    acao: str


@dataclass
class RuleOutput:
    rows: List[Dict[str, Any]]
    report_lines: List[ReportLine]


class AthosRulesEngine:
    def __init__(
        self,
        sql_rows: List[Dict[str, Any]],
        whitelist_eans: List[str],
        supplier_prazo_lookup: Optional[SupplierPrazoLookup] = None,
    ) -> None:
        self.sql_rows = sql_rows or []
        self.whitelist_eans = set(self._only_digits(x) for x in (whitelist_eans or []) if x)
        self.supplier_prazo_lookup = supplier_prazo_lookup

    def apply_all(self) -> Dict[str, RuleOutput]:
        # Normaliza e indexa relações
        normalized = [self._normalize_row(r) for r in self.sql_rows]
        by_pa: Dict[str, List[Dict[str, Any]]] = {}
        by_pai: Dict[str, List[Dict[str, Any]]] = {}
        for it in normalized:
            pa = self._ean(it.get("codbarra_produto"))
            pai = self._ean(it.get("codbarra_pai"))
            if pa:
                by_pa.setdefault(pa, []).append(it)
            if pai:
                by_pai.setdefault(pai, []).append(it)

        handled: set[str] = set()

        out: Dict[str, RuleOutput] = {}

        # Ordem fixa
        out["FORA_DE_LINHA"] = self._rule_fora_de_linha(normalized, handled)
        out["ESTOQUE_COMPARTILHADO"] = self._rule_estoque_compartilhado(normalized, handled, by_pai)
        out["ENVIO_IMEDIATO"] = self._rule_envio_imediato(normalized, handled, by_pai)
        out["SEM_GRUPO"] = self._rule_sem_grupo(normalized, handled)
        out["OUTLET"] = self._rule_outlet(normalized, handled)

        return out

    # =========================
    # RULES
    # =========================
    def _rule_fora_de_linha(self, rows: List[Dict[str, Any]], handled: set[str]) -> RuleOutput:
        out_rows: List[Dict[str, Any]] = []
        report: List[ReportLine] = []

        for it in rows:
            cod = self._ean(it.get("codbarra_produto"))
            if not cod:
                continue

            g3 = self._str(it.get("nome_grupo3")) or ""
            if g3.strip().upper() != "FORA DE LINHA":
                continue

            disp = self._float(it.get("disponivel"))
            if disp > 0:
                continue

            # PA
            if cod not in handled:
                handled.add(cod)
                out_rows.append(self._row_inativo(cod, tipo="PA"))
                report.append(ReportLine(cod, "PA", self._brand(it.get("fabricante_produto")), g3, "PRODUTO INATIVADO"))

            # KIT
            kit = self._ean(it.get("codbarra_kit"))
            if kit and kit not in handled:
                handled.add(kit)
                out_rows.append(self._row_inativo(kit, tipo="KIT"))
                report.append(ReportLine(kit, "KIT", self._brand(it.get("fabricante_produto")), g3, "PRODUTO INATIVADO"))

            # PAI (sem filho: “kit é o filho”)
            pai = self._ean(it.get("codbarra_pai"))
            if pai and pai not in handled:
                handled.add(pai)
                out_rows.append(self._row_inativo(pai, tipo="PAI"))
                report.append(ReportLine(pai, "PAI", self._brand(it.get("fabricante_produto")), g3, "PRODUTO INATIVADO"))

        return RuleOutput(out_rows, report)

    def _rule_outlet(self, rows: List[Dict[str, Any]], handled: set[str]) -> RuleOutput:
        out_rows: List[Dict[str, Any]] = []
        report: List[ReportLine] = []

        for it in rows:
            pa_ean = self._ean(it.get("codbarra_produto"))
            if not pa_ean or pa_ean in handled:
                continue

            g3_raw = self._str(it.get("nome_grupo3")) or ""
            if g3_raw.strip().upper() != "OUTLET":
                continue

            disp = self._float(it.get("disponivel"))
            marca = self._brand(it.get("fabricante_produto"))
            marca_up = self._upper(marca)

            if disp <= 0:
                prazo = self._prazo_fornecedor(it, marca)
                # PA
                handled.add(pa_ean)
                out_rows.append(self._row_prazo(pa_ean, tipo="PA", grupo3="OUTLET", prazo=prazo, estoque_seg=1000, imediata=False))
                report.append(ReportLine(pa_ean, "PA", marca, "OUTLET", f"INCLUIDO 1000 ESTOQUE SEG + PRAZO FORNECEDOR {prazo}"))

                # KIT e PAI com estoque 0
                kit_ean = self._ean(it.get("codbarra_kit"))
                pai_ean = self._ean(it.get("codbarra_pai"))
                marca_kit = self._brand(it.get("fabricante_kit"))
                marca_pai = self._brand(it.get("fabricante_pai"))

                if kit_ean and kit_ean not in handled:
                    handled.add(kit_ean)
                    out_rows.append(self._row_prazo(kit_ean, tipo="KIT", grupo3="OUTLET", prazo=prazo, estoque_seg=0, imediata=False))
                    report.append(ReportLine(kit_ean, "KIT", marca_kit, "OUTLET", f"PRAZO FORNECEDOR {prazo}"))

                if pai_ean and pai_ean not in handled:
                    handled.add(pai_ean)
                    out_rows.append(self._row_prazo(pai_ean, tipo="PAI", grupo3="OUTLET", prazo=prazo, estoque_seg=0, imediata=False))
                    report.append(ReportLine(pai_ean, "PAI", marca_pai, "OUTLET", f"PRAZO FORNECEDOR {prazo}"))

                continue

            # disp > 0
            imediata = False
            prazo = 1
            estoque_seg = 0

            if "DMOV" in marca_up:
                prazo = 3
            elif any(x in marca_up for x in ["KONFORT", "CASA DO PUFF", "DIVINI DECOR"]):
                prazo = 0
                imediata = True
                estoque_seg = 0
            else:
                prazo = 1

            handled.add(pa_ean)
            out_rows.append(self._row_prazo(pa_ean, tipo="PA", grupo3="OUTLET", prazo=prazo, estoque_seg=estoque_seg, imediata=imediata))
            report.append(ReportLine(pa_ean, "PA", marca, "OUTLET", f"ALINHADO PRAZO {('IMEDIATA' if imediata else prazo)}"))

            # somente KIT (mas se vier pai no SQL, a regra do seu texto diz “sem pai” em alguns casos;
            # aqui mantemos alinhamento simples com estoque 0)
            kit_ean = self._ean(it.get("codbarra_kit"))
            pai_ean = self._ean(it.get("codbarra_pai"))
            marca_kit = self._brand(it.get("fabricante_kit"))
            marca_pai = self._brand(it.get("fabricante_pai"))

            if kit_ean and kit_ean not in handled:
                handled.add(kit_ean)
                out_rows.append(self._row_prazo(kit_ean, tipo="KIT", grupo3="OUTLET", prazo=prazo, estoque_seg=0, imediata=imediata))
                report.append(ReportLine(kit_ean, "KIT", marca_kit, "OUTLET", f"ALINHADO COM PA (PRAZO {('IMEDIATA' if imediata else prazo)})"))

            if pai_ean and pai_ean not in handled:
                handled.add(pai_ean)
                out_rows.append(self._row_prazo(pai_ean, tipo="PAI", grupo3="OUTLET", prazo=prazo, estoque_seg=0, imediata=imediata))
                report.append(ReportLine(pai_ean, "PAI", marca_pai, "OUTLET", f"ALINHADO COM PA (PRAZO {('IMEDIATA' if imediata else prazo)})"))

        return RuleOutput(out_rows, report)

    def _rule_envio_imediato(self, rows: List[Dict[str, Any]], handled: set[str], by_pai: Dict[str, List[Dict[str, Any]]]) -> RuleOutput:
        out_rows: List[Dict[str, Any]] = []
        report: List[ReportLine] = []

        for it in rows:
            pa_ean = self._ean(it.get("codbarra_produto"))
            if not pa_ean or pa_ean in handled:
                continue

            g3_raw = self._str(it.get("nome_grupo3")) or ""
            g3_up = g3_raw.strip().upper()

            # ✅ ajuste: ENVIO IMEDIATO não deve puxar códigos que já estejam em FORA DE LINHA
            if g3_up == "FORA DE LINHA":
                continue

            if g3_up != "ENVIO IMEDIATO":
                continue

            disp = self._float(it.get("disponivel"))
            marca = self._brand(it.get("fabricante_produto"))

            # valida whitelist (se não estiver, manda “APAGAR”)
            in_whitelist = pa_ean in self.whitelist_eans

            if not in_whitelist:
                handled.add(pa_ean)
                out_rows.append({"COD_BARRA": pa_ean, "GRUPO3": "APAGAR"})
                report.append(ReportLine(pa_ean, "PA", marca, g3_raw, "RETIRADO DO GRUPO3 ENVIO IMEDIATO (APAGAR)"))
                continue

            # se disponível <=0, regras de fornecedor/estoque por pai
            if disp <= 0:
                pai_ean = self._ean(it.get("codbarra_pai"))
                prazo = self._prazo_fornecedor(it, marca)

                handled.add(pa_ean)
                out_rows.append(self._row_prazo(pa_ean, tipo="PA", grupo3="ENVIO IMEDIATO", prazo=prazo, estoque_seg=0, imediata=False))
                report.append(ReportLine(pa_ean, "PA", marca, g3_raw, f"PA<=0 → PRAZO FORNECEDOR {prazo}"))

                # kit + pai (estoque 0)
                kit_ean = self._ean(it.get("codbarra_kit"))
                if kit_ean and kit_ean not in handled:
                    handled.add(kit_ean)
                    out_rows.append(self._row_prazo(kit_ean, tipo="KIT", grupo3="ENVIO IMEDIATO", prazo=prazo, estoque_seg=0, imediata=False))
                    report.append(ReportLine(kit_ean, "KIT", marca, g3_raw, f"PA<=0 → PRAZO FORNECEDOR {prazo}"))

                if pai_ean and pai_ean not in handled:
                    handled.add(pai_ean)
                    out_rows.append(self._row_prazo(pai_ean, tipo="PAI", grupo3="ENVIO IMEDIATO", prazo=prazo, estoque_seg=0, imediata=False))
                    report.append(ReportLine(pai_ean, "PAI", marca, g3_raw, f"PA<=0 → PRAZO FORNECEDOR {prazo}"))
                continue

            # disp > 0
            marca_up = self._upper(marca)

            imediata = False
            prazo = 1
            estoque_seg = 0

            if "DMOV2" in marca_up:
                prazo = 3
                estoque_seg = 1000
            elif any(x in marca_up for x in ["KONFORT", "CASA DO PUFF", "DIVINI DECOR", "LUMIL", "MADERATTO"]):
                prazo = 0
                imediata = True
                estoque_seg = 0
            else:
                prazo = 1
                estoque_seg = 0

            handled.add(pa_ean)
            out_rows.append(self._row_prazo(pa_ean, tipo="PA", grupo3="ENVIO IMEDIATO", prazo=prazo, estoque_seg=estoque_seg, imediata=imediata))
            report.append(ReportLine(pa_ean, "PA", marca, g3_raw, f"ALINHADO (PRAZO {('IMEDIATA' if imediata else prazo)} + ESTOQUE {estoque_seg})"))

            prazo_txt = "IMEDIATA" if imediata else str(prazo)

            # Kit
            kit_ean = self._ean(it.get("codbarra_kit"))
            if kit_ean and kit_ean not in handled:
                handled.add(kit_ean)
                out_rows.append(self._row_prazo(kit_ean, tipo="KIT", grupo3="ENVIO IMEDIATO", prazo=prazo, estoque_seg=0, imediata=imediata))
                report.append(ReportLine(kit_ean, "KIT", marca or "", g3_raw, f"ALINHADO COM PA (PRAZO {prazo_txt})"))

            # Pai
            pai_ean = self._ean(it.get("codbarra_pai"))
            if pai_ean and pai_ean not in handled:
                handled.add(pai_ean)
                prazo_pai = self._prazo_for_pai(pai_ean, by_pai, default_prazo=prazo)
                out_rows.append(self._row_prazo(pai_ean, tipo="PAI", grupo3="ENVIO IMEDIATO", prazo=prazo_pai, estoque_seg=0, imediata=imediata))
                report.append(ReportLine(pai_ean, "PAI", marca or "", g3_raw, f"PRAZO DO PAI = {prazo_pai}"))

        return RuleOutput(out_rows, report)

    def _rule_sem_grupo(self, rows: List[Dict[str, Any]], handled: set[str]) -> RuleOutput:
        out_rows: List[Dict[str, Any]] = []
        report: List[ReportLine] = []

        for it in rows:
            pa_ean = self._ean(it.get("codbarra_produto"))
            if not pa_ean or pa_ean in handled:
                continue

            g3_raw = self._str(it.get("nome_grupo3")) or ""
            if g3_raw.strip() != "":
                continue  # não é SEM_GRUPO

            marca = self._brand(it.get("fabricante_produto"))
            if not marca:
                continue

            # ✅ ajuste: no SEM_GRUPO ignorar totalmente a marca/grupo "DMOV - MP"
            if "DMOV - MP" in self._upper(marca):
                continue

            disp = self._float(it.get("disponivel"))

            # disp > 0: classifica para ENVIO IMEDIATO (se está na whitelist) ou OUTLET (se não)
            if disp > 0:
                if pa_ean in self.whitelist_eans:
                    handled.add(pa_ean)
                    out_rows.append({"COD_BARRA": pa_ean, "GRUPO3": "ENVIO IMEDIATO"})
                    report.append(ReportLine(pa_ean, "PA", marca, "", "RETIRADO DO SEM_GRUPO → GRUPO3 ENVIO IMEDIATO"))

                    kit_ean = self._ean(it.get("codbarra_kit"))
                    pai_ean = self._ean(it.get("codbarra_pai"))
                    marca_kit = self._brand(it.get("fabricante_kit"))
                    marca_pai = self._brand(it.get("fabricante_pai"))

                    if kit_ean and kit_ean not in handled:
                        handled.add(kit_ean)
                        out_rows.append(self._row_prazo(kit_ean, tipo="KIT", grupo3="ENVIO IMEDIATO", prazo=0, estoque_seg=0, imediata=True))
                        report.append(ReportLine(kit_ean, "KIT", marca_kit, "", "ALINHADO COM PA (IMEDIATA)"))
                    if pai_ean and pai_ean not in handled:
                        handled.add(pai_ean)
                        out_rows.append(self._row_prazo(pai_ean, tipo="PAI", grupo3="ENVIO IMEDIATO", prazo=0, estoque_seg=0, imediata=True))
                        report.append(ReportLine(pai_ean, "PAI", marca_pai, "", "ALINHADO COM PA (IMEDIATA)"))

                else:
                    handled.add(pa_ean)
                    out_rows.append({"COD_BARRA": pa_ean, "GRUPO3": "OUTLET"})
                    report.append(ReportLine(pa_ean, "PA", marca, "", "RETIRADO DO SEM_GRUPO → GRUPO3 OUTLET"))

                    kit_ean = self._ean(it.get("codbarra_kit"))
                    pai_ean = self._ean(it.get("codbarra_pai"))
                    marca_kit = self._brand(it.get("fabricante_kit"))
                    marca_pai = self._brand(it.get("fabricante_pai"))

                    if kit_ean and kit_ean not in handled:
                        handled.add(kit_ean)
                        out_rows.append(self._row_prazo(kit_ean, tipo="KIT", grupo3="OUTLET", prazo=1, estoque_seg=0, imediata=False))
                        report.append(ReportLine(kit_ean, "KIT", marca_kit, "", "ALINHADO COM PA (OUTLET 1 dia)"))
                    if pai_ean and pai_ean not in handled:
                        handled.add(pai_ean)
                        out_rows.append(self._row_prazo(pai_ean, tipo="PAI", grupo3="OUTLET", prazo=1, estoque_seg=0, imediata=False))
                        report.append(ReportLine(pai_ean, "PAI", marca_pai, "", "ALINHADO COM PA (OUTLET 1 dia)"))

                continue

            # disp <= 0: não reclassifica; aplica estoque 1000 no PA e prazo fornecedor para kit/pai
            prazo = self._prazo_fornecedor(it, marca)

            handled.add(pa_ean)
            out_rows.append(self._row_prazo(pa_ean, tipo="PA", grupo3=None, prazo=prazo, estoque_seg=1000, imediata=False))
            report.append(ReportLine(pa_ean, "PA", marca, "", f"PA<=0 → INCLUIDO 1000 ESTOQUE SEG + PRAZO FORNECEDOR {prazo}"))

            kit_ean = self._ean(it.get("codbarra_kit"))
            pai_ean = self._ean(it.get("codbarra_pai"))
            marca_kit = self._brand(it.get("fabricante_kit"))
            marca_pai = self._brand(it.get("fabricante_pai"))

            if kit_ean and kit_ean not in handled:
                handled.add(kit_ean)
                out_rows.append(self._row_prazo(kit_ean, tipo="KIT", grupo3=None, prazo=prazo, estoque_seg=0, imediata=False))
                report.append(ReportLine(kit_ean, "KIT", marca_kit, "", f"PA<=0 → PRAZO FORNECEDOR {prazo}"))

            if pai_ean and pai_ean not in handled:
                handled.add(pai_ean)
                out_rows.append(self._row_prazo(pai_ean, tipo="PAI", grupo3=None, prazo=prazo, estoque_seg=0, imediata=False))
                report.append(ReportLine(pai_ean, "PAI", marca_pai, "", f"PA<=0 → PRAZO FORNECEDOR {prazo}"))

        return RuleOutput(out_rows, report)

    def _rule_estoque_compartilhado(self, rows: List[Dict[str, Any]], handled: set[str], by_pai: Dict[str, List[Dict[str, Any]]]) -> RuleOutput:
        out_rows: List[Dict[str, Any]] = []
        report: List[ReportLine] = []

        for it in rows:
            kit_ean = self._ean(it.get("codbarra_kit"))
            pai_ean = self._ean(it.get("codbarra_pai"))
            if not kit_ean:
                continue

            g3_raw = self._str(it.get("nome_grupo3")) or ""
            if g3_raw.strip().upper() != "ESTOQUE COMPARTILHADO":
                continue

            # regra: copiar prazo do PA para o kit; pai pega maior prazo dentre kits do mesmo pai
            marca = self._brand(it.get("fabricante_produto"))
            prazo = self._prazo_fornecedor(it, marca)

            if kit_ean not in handled:
                handled.add(kit_ean)
                out_rows.append(self._row_prazo(kit_ean, tipo="KIT", grupo3=None, prazo=prazo, estoque_seg=None, imediata=False))
                report.append(ReportLine(kit_ean, "KIT", marca, g3_raw, f"COPIADO PRAZO DO PA = {prazo}"))

            if pai_ean and pai_ean not in handled:
                pr = self._prazo_for_pai_maior_entre_kits(pai_ean, by_pai, fallback=prazo)
                handled.add(pai_ean)
                out_rows.append(self._row_prazo(pai_ean, tipo="PAI", grupo3=None, prazo=pr, estoque_seg=None, imediata=False))
                report.append(ReportLine(pai_ean, "PAI", marca, g3_raw, f"PAI = MAIOR PRAZO ENTRE KITS ({pr})"))

        return RuleOutput(out_rows, report)

    # =========================
    # Helpers
    # =========================
    def _row_inativo(self, ean: str, tipo: str) -> Dict[str, Any]:
        return {"COD_BARRA": ean, "TIPO": tipo, "PRODUTO_INATIVO": "T"}

    def _row_prazo(self, ean: str, tipo: str, grupo3: Optional[str], prazo: int, estoque_seg: Optional[int], imediata: bool) -> Dict[str, Any]:
        site = "Imediata" if imediata else str(prazo)
        row: Dict[str, Any] = {
            "COD_BARRA": ean,
            "TIPO": tipo,
            "DATA_ENTREGA": prazo,
            "SITE_DISPONIBILIDADE": site,
        }
        if grupo3 is not None:
            row["GRUPO3"] = grupo3
        if estoque_seg is not None:
            row["ESTOQUE_SEG"] = estoque_seg
        return row

    def _prazo_for_pai(self, pai_ean: str, by_pai: Dict[str, List[Dict[str, Any]]], default_prazo: int) -> int:
        rel = by_pai.get(pai_ean, []) or []
        # se TODOS PA >0 -> default, senão fornecedor (pior caso)
        all_gt0 = True
        max_prazo = default_prazo
        for it in rel:
            disp = self._float(it.get("disponivel"))
            if disp <= 0:
                all_gt0 = False
            marca = self._brand(it.get("fabricante_produto"))
            p = self._prazo_fornecedor(it, marca)
            if p > max_prazo:
                max_prazo = p
        return default_prazo if all_gt0 else max_prazo

    def _prazo_for_pai_maior_entre_kits(self, pai_ean: str, by_pai: Dict[str, List[Dict[str, Any]]], fallback: int) -> int:
        rel = by_pai.get(pai_ean, []) or []
        best = fallback
        for it in rel:
            marca = self._brand(it.get("fabricante_produto"))
            p = self._prazo_fornecedor(it, marca)
            if p > best:
                best = p
        return best

    def _prazo_fornecedor(self, it: Dict[str, Any], marca: str) -> int:
        grupo_prod = self._str(it.get("grupo_produto"))
        if grupo_prod and grupo_prod.strip().isdigit():
            return int(grupo_prod.strip())

        if self.supplier_prazo_lookup:
            try:
                p = self.supplier_prazo_lookup(marca)
                if p is not None:
                    return int(p)
            except Exception:
                pass

        # fallback default
        return 1

    def _normalize_row(self, r: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(r or {})
        return out

    def _only_digits(self, s: str) -> str:
        return "".join(ch for ch in (s or "") if ch.isdigit())

    def _ean(self, v: Any) -> str:
        if v is None:
            return ""
        s = str(v).strip()
        s = self._only_digits(s)
        return s

    def _str(self, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    def _upper(self, v: str) -> str:
        return (v or "").strip().upper()

    def _brand(self, v: Any) -> str:
        s = self._str(v)
        return s

    def _float(self, v: Any) -> float:
        try:
            if v is None or str(v).strip() == "":
                return 0.0
            return float(str(v).replace(",", "."))
        except Exception:
            return 0.0
