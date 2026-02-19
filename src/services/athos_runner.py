"""
Service: AthosRunner

Responsável por:
- Ler o export do SQL (Excel)
- Ler whitelist (PRODUTOS.xls/.xlsx) -> lista de EANs "imediatos"
- Abrir template Athos e gerar 5 planilhas (cada uma com aba 'PRODUTO(S)')
- Aplicar regras e preencher SOMENTE a aba 'PRODUTO(S)' do template
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
from typing import Callable, Optional, Any, Dict, List
import shutil
import re

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
        send_email: bool = True,
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
        from .athos_whitelist import load_whitelist
        wl = load_whitelist(whitelist_path)
        whitelist_eans = wl.eans

        self.logger.info(f"[AthosRunner] SQL rows: {len(sql_rows)}")
        self.logger.info(f"[AthosRunner] Whitelist EANs: {len(whitelist_eans)}")

        progress(0.22, "Aplicando regras...")
        from .athos_rules_engine import process_rows

        # ✅ Instancia DB 1x só (e não quebra se faltar)
        supplier_db = None
        try:
            from ..core.supplier_database import SupplierDatabase
            supplier_db = SupplierDatabase()
        except Exception as e:
            supplier_db = None
            self.logger.warning(f"[AthosRunner] SupplierDatabase indisponível: {e}")

        def prazo_lookup(marca: str) -> Optional[int]:
            if not marca:
                return None
            if supplier_db is None:
                return None
            try:
                s = supplier_db.search_supplier_by_name(marca)
                prazo = getattr(s, "prazo_dias", None) if s else None
                return int(prazo) if prazo is not None else None
            except Exception:
                return None

        outputs = process_rows(
            sql_rows=sql_rows,
            whitelist_imediatos=whitelist_eans,
            supplier_prazo_lookup=prazo_lookup,
        )

        progress(0.35, "Gerando planilhas...")
        from .athos_excel_writer import AthosExcelWriter
        from .athos_models import ORDERED_RULES, RuleName

        writer = AthosExcelWriter()
        generated_files: List[Path] = []

        def _parse_int_from_text(val: Any) -> Optional[int]:
            if val is None:
                return None
            if isinstance(val, (int, float)):
                try:
                    return int(val)
                except Exception:
                    return None
            s = str(val).strip()
            if not s:
                return None
            m = re.search(r"(\d+)", s)
            if not m:
                return None
            try:
                return int(m.group(1))
            except Exception:
                return None

        def _dias_para_entrega(dias: Any, site: Any) -> Any:
            """
            Regra pedida:
            - 'Dias para Entrega' deve refletir o mesmo valor lógico de 'Site Disponibilidade'
            """
            if dias is not None:
                return dias

            if site is None:
                return None

            site_s = str(site).strip()
            if not site_s:
                return None

            if site_s.lower() == "imediata":
                return 0

            n = _parse_int_from_text(site_s)
            return n if n is not None else site_s  # fallback: escreve o texto se não achar número

        # ✅ converter ações -> linhas do template (headers reais do seu modelo)
        def action_to_row(a) -> Dict[str, Any]:
            row: Dict[str, Any] = {
                "Código de Barras": a.codbarra,
            }

            # ✅ NÃO preencher Tipo Produto (pedido)
            # row["Tipo Produto"] = ...

            if a.grupo3 is not None:
                row["GRUPO3"] = a.grupo3

            if a.estoque_seguranca is not None:
                row["Estoque de Segurança"] = a.estoque_seguranca

            if a.produto_inativo is not None:
                row["Produto Inativo"] = a.produto_inativo

            if a.dias_entrega is not None:
                row["Dias para Entrega"] = a.dias_entrega

            if a.site_disponibilidade is not None:
                row["Site Disponibilidade"] = a.site_disponibilidade

            return row

        rule_to_output = {
            RuleName.FORA_DE_LINHA: "FORA_DE_LINHA",
            RuleName.ESTOQUE_COMPARTILHADO: "ESTOQUE_COMPARTILHADO",
            RuleName.ENVIO_IMEDIATO: "ENVIO_IMEDIATO",
            RuleName.NENHUM_GRUPO: "SEM_GRUPO",
            RuleName.OUTLET: "OUTLET",
        }

        for idx, rule in enumerate(ORDERED_RULES, start=1):
            pct = 0.35 + (idx / len(ORDERED_RULES)) * 0.45
            progress(pct, f"Escrevendo {rule.value}...")

            key = rule_to_output[rule]
            out_path = self.output_dir / self.OUTPUT_NAMES[key]
            self._copy_template(template_path, out_path)

            actions = outputs.actions_by_rule.get(rule, []) or []
            rows_to_write = [action_to_row(a) for a in actions]

            # ✅ writer tem fallback de aba (PRODUTO/PRODUTOS/...)
            writer.write_rule_workbook(
                out_path,
                rows_to_write,
                sheet_name="PRODUTOS",
                clear_existing_data=True,
            )
            generated_files.append(out_path)

        progress(0.86, "Gerando relatório consolidado...")
        report_path = self.output_dir / self.OUTPUT_NAMES["RELATORIO"]
        self._write_report(report_path, outputs, sql_export_path, whitelist_path, template_path)

        if send_email:
            progress(0.92, "Enviando e-mail (RPA Athus)...")
            try:
                self._send_email_athos(generated_files)
            except Exception as e:
                self.logger.warning(f"⚠️ Falha ao enviar e-mail do Athos: {e}")

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

    # ===== E-mail Athos =====
    def _send_email_athos(self, attachments: List[Path]) -> None:
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders
        import smtplib
        import ssl

        from ..core.config import load_config

        cfg = load_config()
        if not cfg.email:
            raise RuntimeError("Config de e-mail não encontrada em assets/config/settings.json")

        to_addr = "rpa.athus@apoiocorp.com.br"

        msg = MIMEMultipart()
        msg["From"] = cfg.email.from_addr or cfg.email.username
        msg["To"] = to_addr
        msg["Subject"] = "DROSSI PRODUTOS"
        msg.attach(MIMEText("Planilhas geradas pelo Robô Athos em anexo.", "plain", "utf-8"))

        for fp in attachments:
            if not fp.exists():
                continue
            part = MIMEBase("application", "octet-stream")
            part.set_payload(fp.read_bytes())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={fp.name}")
            msg.attach(part)

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(cfg.email.smtp_host, cfg.email.smtp_port, context=context) as server:
            server.login(cfg.email.username, cfg.email.password)
            server.sendmail(msg["From"], [to_addr], msg.as_string())

    # ===== Report =====
    def _write_report(
        self,
        report_path: Path,
        outputs: Any,
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
        for r in outputs.report_lines:
            total += 1
            tipo = r.tipo.value if hasattr(r.tipo, "value") else str(r.tipo)
            marca = r.marca or ""
            grupo3 = r.grupo3 or ""
            acao = r.acao or ""
            lines.append(f"{r.codbarra} | {tipo} | {marca} | {grupo3} | {acao}")

        lines.append("")
        lines.append(f"Total de ações listadas: {total}")
        lines.append("")
        lines.append("Legenda rápida:")
        lines.append("- PA = Produto acabado")
        lines.append("- KIT = Kit")
        lines.append("- PAI = Pai do Kit")
        lines.append("")

        report_path.write_text("\n".join(lines), encoding="utf-8")
