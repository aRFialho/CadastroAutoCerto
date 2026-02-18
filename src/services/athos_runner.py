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

    # =========================
    # Public
    # =========================
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

        # ✅ Lê whitelist pelo mesmo pipeline (suporta .xls/.xlsx) e extrai EANs por heurística
        progress(0.14, "Lendo whitelist...")
        whitelist_rows = self._read_excel_any(whitelist_path)
        whitelist_eans = self._extract_whitelist_eans(whitelist_rows)

        if not whitelist_eans:
            self.logger.warning(
                "[AthosRunner] Nenhum EAN detectado na whitelist. "
                "Verifique se existe coluna EAN/GTIN/COD_BARRA ou se a primeira coluna contém os códigos."
            )

        self.logger.info(f"[AthosRunner] SQL rows: {len(sql_rows)}")
        self.logger.info(f"[AthosRunner] Whitelist EANs: {len(whitelist_eans)}")

        progress(0.22, "Aplicando regras...")
        from .athos_rules_engine import process_rows

        # ✅ Instancia DB uma única vez (robusto e rápido)
        supplier_db = None
        try:
            from ..core.supplier_database import SupplierDatabase
            supplier_db = SupplierDatabase()
        except Exception as e:
            supplier_db = None
            self.logger.warning(f"[AthosRunner] SupplierDatabase indisponível: {e}")

        def prazo_lookup(marca: str) -> Optional[int]:
            """Lookup de prazo por marca (sem quebrar o fluxo)."""
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

        def action_to_row(a, rule) -> Dict[str, Any]:
            """
            Converte ação do motor em uma linha para o template.
            Regras pedidas:
            - Não preencher Tipo Produto (não escrever coluna Tipo).
            - Preencher Dias para Entrega (e também Data Entrega por compatibilidade).
            - Em ESTOQUE_COMPARTILHADO: Dias para Entrega deve repetir Site Disponibilidade.
            - Em ENVIO_IMEDIATO: não puxar itens de FORA_DE_LINHA (produto_inativo).
            - Ajustar nomes de headers para bater com template (tolerante).
            """
            row: Dict[str, Any] = {
                "Codigo de Barras": a.codbarra,
                # NÃO escrever Tipo/Tipo Produto
            }

            # Grupo3 (quando existir)
            if getattr(a, "grupo3", None) is not None:
                row["Grupo3"] = a.grupo3

            # Estoque de Segurança (usar os dois nomes pra bater com template)
            if getattr(a, "estoque_seguranca", None) is not None:
                row["Estoque de Segurança"] = a.estoque_seguranca
                row["Estoque Seguranca"] = a.estoque_seguranca  # fallback

            # Dias / Data entrega (usar ambos)
            dias = getattr(a, "dias_entrega", None)
            site_disp = getattr(a, "site_disponibilidade", None)

            # Regra pedida: ESTOQUE_COMPARTILHADO -> Dias para Entrega = Site Disponibilidade
            # (se o motor já mandar dias_entrega ok, a gente mantém; se não, copia do site_disp)
            if rule.value == "ESTOQUE_COMPARTILHADO":
                if dias is None and site_disp is not None:
                    dias = site_disp

            if dias is not None:
                row["Dias para Entrega"] = dias
                row["Data Entrega"] = dias  # fallback (templates antigos)

            if site_disp is not None:
                row["Site Disponibilidade"] = site_disp

            # Produto Inativo (Fora de linha)
            if getattr(a, "produto_inativo", None) is not None:
                row["Produto Inativo"] = a.produto_inativo

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

            # 1) ENVIO_IMEDIATO: não puxar códigos "Fora de Linha"
            if rule.value == "ENVIO_IMEDIATO":
                actions = [a for a in actions if not getattr(a, "produto_inativo", None)]

            # 2) SEM_GRUPO: não precisa puxar marca/grupo "DMOV - MP"
            # (se existir a propriedade marca no objeto de ação)
            if rule.value == "NENHUM_GRUPO":
                actions = [a for a in actions if (getattr(a, "marca", "") or "").strip().upper() != "DMOV - MP"]

            rows_to_write = [action_to_row(a, rule) for a in actions]

            writer.write_rule_workbook(
                out_path,
                rows_to_write,
                sheet_name="PRODUTOS",
                clear_existing_data=True
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
    # Whitelist parsing
    # =========================
    def _extract_whitelist_eans(self, whitelist_rows: List[Dict[str, Any]]) -> set[str]:
        """
        Extrai EANs da whitelist (PRODUTOS.xls/.xlsx) com heurística de coluna.
        Aceita headers variados: EAN, GTIN, COD_BARRA, CODIGO_BARRA, CÓD BARRAS etc.
        Normaliza removendo .0, espaços, hífens e mantendo apenas dígitos.
        """

        def norm(v: Any) -> str:
            if v is None:
                return ""
            s = str(v).strip()
            if s.endswith(".0"):
                s = s[:-2]
            s = re.sub(r"\D", "", s)
            return s

        if not whitelist_rows:
            return set()

        headers = list(whitelist_rows[0].keys())
        header_norm = {h: re.sub(r"[^a-z0-9]+", "", str(h).lower()) for h in headers}

        candidates: List[str] = []
        for h, hn in header_norm.items():
            if any(k in hn for k in ("ean", "gtin", "codbarras", "codigobarra", "codbarra", "barras", "barcode")):
                candidates.append(h)

        chosen = candidates[0] if candidates else (headers[0] if headers else None)
        if not chosen:
            return set()

        eans: set[str] = set()
        for row in whitelist_rows:
            e = norm(row.get(chosen))
            if e:
                eans.add(e)

        return eans

    # =========================
    # IO
    # =========================
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

    # =========================
    # E-mail Athos
    # =========================
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

    # =========================
    # Report
    # =========================
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
