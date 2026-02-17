"""
Service: AthosRunner

Responsável por:
- Ler o export do SQL (Excel)
- Ler whitelist (PRODUTOS.xls/.xlsx) -> lista de EANs "imediatos"
- Abrir template Athos e gerar 5 planilhas (cada uma com aba 'PRODUTOS')
- Aplicar regras e preencher SOMENTE a aba 'PRODUTOS' do template
- Gerar relatório consolidado

Saídas geradas (na ordem):
01_FORA_DE_LINHA.xlsx
02_ESTOQUE_COMPARTILHADO.xlsx
03_ENVIO_IMEDIATO.xlsx
04_SEM_GRUPO.xlsx
05_OUTLET.xlsx
RELATORIO_CONSOLIDADO.txt
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional, Any, Dict, List, Set

import shutil

from ..utils.logger import get_logger

logger_default = get_logger("athos_runner")


ProgressCallback = Callable[[float, str], None]


@dataclass
class AthosRunResult:
    generated_files: List[Path]
    report_path: Optional[Path] = None


class AthosRunner:
    RULE_ORDER = [
        "FORA_DE_LINHA",
        "ESTOQUE_COMPARTILHADO",
        "ENVIO_IMEDIATO",
        "SEM_GRUPO",
        "OUTLET",
    ]

    OUTPUT_NAMES = {
        "FORA_DE_LINHA": "01_FORA_DE_LINHA.xlsx",
        "ESTOQUE_COMPARTILHADO": "02_ESTOQUE_COMPARTILHADO.xlsx",
        "ENVIO_IMEDIATO": "03_ENVIO_IMEDIATO.xlsx",
        "SEM_GRUPO": "04_SEM_GRUPO.xlsx",
        "OUTLET": "05_OUTLET.xlsx",
        "RELATORIO": "RELATORIO_CONSOLIDADO.txt",
    }

    def __init__(self, output_dir: Path, logger=logger_default):
        self.output_dir = Path(output_dir)
        self.logger = logger

    def run(
        self,
        sql_export_path: Path,
        whitelist_path: Path,
        template_path: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> AthosRunResult:
        progress = progress_callback or (lambda p, m="": None)

        sql_export_path = Path(sql_export_path)
        whitelist_path = Path(whitelist_path)
        template_path = Path(template_path)

        progress(0.02, "Validando arquivos...")
        self._validate_inputs(sql_export_path, whitelist_path, template_path)

        self.output_dir.mkdir(parents=True, exist_ok=True)

        progress(0.08, "Lendo export do SQL...")
        sql_rows = self._read_excel_any(sql_export_path)

        progress(0.14, "Lendo whitelist...")
        whitelist_rows = self._read_excel_any(whitelist_path)
        whitelist_eans = self._extract_whitelist_eans(whitelist_rows)

        self.logger.info(f"[AthosRunner] SQL rows: {len(sql_rows)}")
        self.logger.info(f"[AthosRunner] Whitelist EANs: {len(whitelist_eans)}")

        progress(0.22, "Aplicando regras...")
        from .athos_rules import AthosRulesEngine

        engine = AthosRulesEngine()
        outputs = engine.apply_all(sql_rows=sql_rows, whitelist_eans=whitelist_eans)

        progress(0.35, "Gerando planilhas...")
        generated_files: List[Path] = []

        for idx, rule_key in enumerate(self.RULE_ORDER, start=1):
            pct = 0.35 + (idx / len(self.RULE_ORDER)) * 0.45
            progress(pct, f"Escrevendo {rule_key.replace('_', ' ')}...")

            out_path = self.output_dir / self.OUTPUT_NAMES[rule_key]
            self._copy_template(template_path, out_path)

            rule_out = outputs.get(rule_key)
            rows_to_write = rule_out.rows if rule_out else []

            self._fill_template_produtos(out_path, rows_to_write)
            generated_files.append(out_path)

        progress(0.86, "Gerando relatório consolidado...")
        report_path = self.output_dir / self.OUTPUT_NAMES["RELATORIO"]
        self._write_report(report_path, outputs, sql_export_path, whitelist_path, template_path)

        progress(1.0, "Concluído ✅")
        return AthosRunResult(generated_files=generated_files, report_path=report_path)

    # ===== IO =====
    def _validate_inputs(self, sql_export_path: Path, whitelist_path: Path, template_path: Path) -> None:
        if not sql_export_path.exists():
            raise FileNotFoundError(f"Arquivo do SQL não encontrado: {sql_export_path}")
        if not whitelist_path.exists():
            raise FileNotFoundError(f"Whitelist não encontrada: {whitelist_path}")
        if not template_path.exists():
            raise FileNotFoundError(f"Template não encontrado: {template_path}")
        if template_path.suffix.lower() not in [".xlsx", ".xlsm"]:
            raise ValueError("Template precisa ser .xlsx ou .xlsm (modelo Athos).")

    def _copy_template(self, template_path: Path, output_path: Path) -> None:
        shutil.copy2(template_path, output_path)

    def _read_excel_any(self, path: Path) -> List[Dict[str, Any]]:
        suffix = path.suffix.lower()
        if suffix in [".xlsx", ".xlsm"]:
            return self._read_xlsx_openpyxl(path)
        if suffix == ".xls":
            return self._read_xls_pandas(path)
        raise ValueError(f"Formato não suportado: {suffix}. Use .xlsx/.xlsm (ou .xls com suporte xlrd).")

    def _read_xlsx_openpyxl(self, path: Path) -> List[Dict[str, Any]]:
        from openpyxl import load_workbook
        wb = load_workbook(path, data_only=True)
        ws = wb.active

        headers: List[str] = []
        rows_out: List[Dict[str, Any]] = []

        for r_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if r_idx == 1:
                headers = [str(c).strip() if c is not None else "" for c in row]
                continue

            if not any(c is not None and str(c).strip() != "" for c in row):
                continue

            item: Dict[str, Any] = {}
            for i, h in enumerate(headers):
                if not h:
                    continue
                item[h] = row[i] if i < len(row) else None

            rows_out.append(item)

        return rows_out

    def _read_xls_pandas(self, path: Path) -> List[Dict[str, Any]]:
        try:
            import pandas as pd  # type: ignore
        except Exception:
            raise RuntimeError(
                "Não consegui ler arquivo .xls (pandas não disponível). "
                "Salve a whitelist como .xlsx e tente novamente."
            )

        try:
            df = pd.read_excel(path, engine="xlrd")  # type: ignore
        except Exception:
            try:
                df = pd.read_excel(path)  # type: ignore
            except Exception as e:
                raise RuntimeError(
                    "Não consegui ler arquivo .xls. "
                    "Sugestão: abra e salve como .xlsx. "
                    f"Detalhe: {e}"
                )

        df = df.dropna(how="all")
        return df.to_dict(orient="records")

    # ===== Template writing =====
    def _fill_template_produtos(self, template_path: Path, rows: List[Dict[str, Any]]) -> None:
        """
        Preenche SOMENTE a aba 'PRODUTOS' do template.
        - Cabeçalho é lido na linha 1
        - Escreve a partir da linha 2
        - Limpa conteúdo antigo antes de escrever
        """
        from openpyxl import load_workbook

        wb = load_workbook(template_path)
        if "PRODUTOS" not in wb.sheetnames:
            raise ValueError(f"Template não possui aba 'PRODUTOS': {template_path}")

        ws = wb["PRODUTOS"]

        headers = {}
        for col in range(1, ws.max_column + 1):
            val = ws.cell(row=1, column=col).value
            if val is None:
                continue
            key = str(val).strip().upper()
            if key:
                headers[key] = col

        if ws.max_row > 1:
            ws.delete_rows(2, ws.max_row - 1)

        for r_idx, r in enumerate(rows, start=2):
            for k, v in r.items():
                if v is None:
                    continue
                col = headers.get(str(k).strip().upper())
                if not col:
                    continue
                ws.cell(row=r_idx, column=col).value = v

        wb.save(template_path)

    # ===== Whitelist =====
    def _extract_whitelist_eans(self, rows: List[Dict[str, Any]]) -> Set[str]:
        def norm_ean(v: Any) -> str:
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
            return s

        if not rows:
            return set()

        sample = rows[0]
        keys = [k for k in sample.keys() if k]
        preferred = None
        for k in keys:
            ku = str(k).strip().upper()
            if ku in ("EAN", "CODBARRA", "COD_BARRA", "COD. BARRA", "CÓD BARRA", "CODIGO_BARRA", "CODIGO DE BARRAS"):
                preferred = k
                break

        eans: Set[str] = set()
        for r in rows:
            val = None
            if preferred and preferred in r:
                val = r.get(preferred)
            else:
                for k in keys:
                    if r.get(k) is not None and str(r.get(k)).strip() != "":
                        val = r.get(k)
                        break
            e = norm_ean(val)
            if e:
                eans.add(e)
        return eans

    # ===== Report =====
    def _write_report(
        self,
        report_path: Path,
        outputs: Dict[str, Any],
        sql_export_path: Path,
        whitelist_path: Path,
        template_path: Path,
    ) -> None:
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        lines: List[str] = []
        lines.append("RELATÓRIO CONSOLIDADO — ROBÔ ATHOS")
        lines.append(f"Gerado em: {now}")
        lines.append("")
        lines.append("Entradas:")
        lines.append(f"- SQL export: {sql_export_path}")
        lines.append(f"- Whitelist: {whitelist_path}")
        lines.append(f"- Template: {template_path}")
        lines.append("")
        lines.append("ORDEM DE PROCESSAMENTO:")
        for r in self.RULE_ORDER:
            lines.append(f"- {r}")
        lines.append("")
        lines.append("AÇÕES (todas as planilhas):")
        lines.append("EAN | TIPO | MARCA | GRUPO3 | AÇÃO")
        lines.append("-" * 80)

        total = 0
        for rule_key in self.RULE_ORDER:
            rule_out = outputs.get(rule_key)
            if not rule_out:
                continue
            report = getattr(rule_out, "report", []) or []
            if not report:
                continue

            lines.append("")
            lines.append(f"[{rule_key}]")
            for r in report:
                total += 1
                lines.append(f"{r.ean} | {r.tipo} | {r.marca} | {r.grupo3} | {r.acao}")

        lines.append("")
        lines.append(f"Total de ações listadas: {total}")
        lines.append("")
        lines.append("Legenda rápida:")
        lines.append("- PA = Produto acabado (codbarra_produto)")
        lines.append("- KIT = Kit (codbarra_kit)")
        lines.append("- PAI = Pai do Kit (codbarra_pai)")
        lines.append("")

        report_path.write_text("\n".join(lines), encoding="utf-8")
