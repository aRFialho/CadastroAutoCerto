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
from typing import Callable, Optional, Any, Dict, List

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
        whitelist_rows = self._read_excel_any(whitelist_path)
        whitelist_eans = self._extract_whitelist_eans(whitelist_rows)

        self.logger.info(f"[AthosRunner] SQL rows: {len(sql_rows)}")
        self.logger.info(f"[AthosRunner] Whitelist EANs: {len(whitelist_eans)}")

        progress(0.22, "Aplicando regras...")
        from .athos_rules import AthosRulesEngine

        engine = AthosRulesEngine(
            sql_rows=sql_rows,
            whitelist_eans=whitelist_eans,
            supplier_prazo_lookup=self._supplier_prazo_lookup,
        )
        outputs = engine.apply_all()

        progress(0.35, "Gerando planilhas...")
        generated_files: List[Path] = []

        # ✅ Writer robusto (detecta cabeçalho mesmo se não estiver na linha 1)
        from .athos_excel_writer import AthosExcelWriter
        writer = AthosExcelWriter()

        for idx, rule_key in enumerate(self.RULE_ORDER, start=1):
            pct = 0.35 + (idx / len(self.RULE_ORDER)) * 0.45
            progress(pct, f"Escrevendo {rule_key.replace('_', ' ')}...")

            out_path = self.output_dir / self.OUTPUT_NAMES[rule_key]
            self._copy_template(template_path, out_path)

            rule_out = outputs.get(rule_key)
            rows_raw = rule_out.rows if rule_out else []
            rows_to_write = self._map_rows_for_template(rows_raw, rule_key)

            writer.write_rule_workbook(
                workbook_path=out_path,
                rows=rows_to_write,
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

    # =========================
    # Template mapping
    # =========================
    def _map_rows_for_template(self, rows_raw: List[Dict[str, Any]], rule_key: str) -> List[Dict[str, Any]]:
        """Converte as linhas do motor (athos_rules.py) para os headers reais do template.

        Motor gera chaves internas:
          COD_BARRA, GRUPO3, ESTOQUE_SEG, DATA_ENTREGA, SITE_DISPONIBILIDADE, PRODUTO_INATIVO, TIPO

        Template (cabeçalho):
          Código de Barras | GRUPO3 | Estoque de Segurança | Produto Inativo | Dias para Entrega | Site Disponibilidade

        Ajustes solicitados:
        - NÃO preencher "Tipo Produto" (ignora TIPO em todas as planilhas).
        - ESTOQUE_COMPARTILHADO: "Dias para Entrega" deve repetir o valor de "Site Disponibilidade".
        """
        mapped: List[Dict[str, Any]] = []

        for r in rows_raw or []:
            if not r:
                continue

            cod = r.get("COD_BARRA")
            if cod is None or str(cod).strip() == "":
                continue

            grupo3 = r.get("GRUPO3")
            estoque = r.get("ESTOQUE_SEG")
            dias = r.get("DATA_ENTREGA")
            site = r.get("SITE_DISPONIBILIDADE")
            inativo = r.get("PRODUTO_INATIVO")

            if rule_key == "ESTOQUE_COMPARTILHADO":
                if dias is None and site is not None:
                    dias = site
                if site is None and dias is not None:
                    site = dias

            out: Dict[str, Any] = {"Código de Barras": cod}

            if grupo3 is not None and str(grupo3).strip() != "":
                out["GRUPO3"] = grupo3
            if estoque is not None and str(estoque).strip() != "":
                out["Estoque de Segurança"] = estoque
            if inativo is not None and str(inativo).strip() != "":
                out["Produto Inativo"] = inativo
            if dias is not None and str(dias).strip() != "":
                out["Dias para Entrega"] = dias
            if site is not None and str(site).strip() != "":
                out["Site Disponibilidade"] = site

            mapped.append(out)

        return mapped

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

    def _extract_whitelist_eans(self, rows: List[Dict[str, Any]]) -> List[str]:
        """Extrai lista de EANs da whitelist.

        Aceita:
        - coluna "EAN"
        - ou primeira coluna que pareça EAN/código de barras
        """
        eans: List[str] = []
        if not rows:
            return eans

        # Tenta achar coluna EAN
        keys = list(rows[0].keys())
        ean_key = None
        for k in keys:
            ku = str(k).strip().upper()
            if ku in ("EAN", "CÓDIGO DE BARRAS", "CODIGO DE BARRAS", "CODBARRA", "COD_BARRA", "CODIGO"):
                ean_key = k
                break

        if ean_key is None:
            # fallback: primeira coluna
            ean_key = keys[0]

        for r in rows:
            v = r.get(ean_key)
            if v is None:
                continue
            s = str(v).strip()
            if not s:
                continue
            eans.append(s)

        # normaliza e remove duplicados mantendo ordem
        seen = set()
        out: List[str] = []
        for s in eans:
            s2 = "".join(ch for ch in s if ch.isdigit())
            if not s2:
                continue
            if s2 in seen:
                continue
            seen.add(s2)
            out.append(s2)
        return out

    # ===== Fornecedor (prazo) =====
    def _supplier_prazo_lookup(self, marca: str) -> Optional[int]:
        if not marca:
            return None
        try:
            from ..core.supplier_database import SupplierDatabase
            db = SupplierDatabase()
        except Exception:
            return None

        try:
            s = db.search_supplier_by_name(marca)
            prazo = getattr(s, "prazo_dias", None) if s else None
            return int(prazo) if prazo is not None else None
        except Exception:
            return None

    # ===== E-mail Athos =====
    def _send_email_athos(self, attachments: List[Path]) -> None:
        """Envia as planilhas geradas para o e-mail do RPA Athus.

        Requisito do negócio:
        - Para: rpa.athus@apoiocorp.com.br
        - Assunto: DROSSI PRODUTOS
        - Anexar todas as planilhas geradas

        Observação: usa as credenciais SMTP já configuradas em assets/config/settings.json.
        """
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
        for rule in self.RULE_ORDER:
            rule_out = outputs.get(rule)
            if not rule_out:
                continue
            for r in rule_out.report_lines:
                total += 1
                tipo = r.tipo or ""
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
