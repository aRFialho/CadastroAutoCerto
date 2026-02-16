"""
Service: AthosRunner
Responsável por:
- Ler o export do SQL (Excel)
- Ler whitelist (PRODUTOS.xls/.xlsx)
- Abrir template Athos e gerar 5 planilhas (cada uma com aba 'PRODUTOS')
- Gerar relatório consolidado

OBS:
- Agora integra AthosExcelWriter para limpar e escrever na aba PRODUTOS.
- Nesta fase, ainda NÃO aplicamos regras. Apenas valida template e pipeline:
  -> escreve EANs (teste) nas 5 planilhas para você confirmar colunas/aba.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional, Any, Dict, List

import shutil

from ..utils.logger import get_logger
from .athos_excel_writer import AthosExcelWriter

logger_default = get_logger("athos_runner")

ProgressCallback = Callable[[float, str], None]


@dataclass
class AthosRunResult:
    generated_files: List[Path]
    report_path: Optional[Path] = None


class AthosRunner:
    """
    Runner principal do Robô Athos.

    Nesta fase:
    - valida entradas
    - prepara outputs
    - cria as 5 planilhas
    - limpa e escreve EANs (teste) na aba PRODUTOS
    - gera um relatório consolidado
    """

    # Ordem obrigatória definida por você
    RULE_ORDER = [
        "FORA_DE_LINHA",
        "ESTOQUE_COMPARTILHADO",
        "ENVIO_IMEDIATO",
        "SEM_GRUPO",
        "OUTLET",
    ]

    # Nomes de arquivo (saída)
    OUTPUT_NAMES = {
        "FORA_DE_LINHA": "01_FORA_DE_LINHA.xlsx",
        "ESTOQUE_COMPARTILHADO": "02_ESTOQUE_COMPARTILHADO.xlsx",
        "ENVIO_IMEDIATO": "03_ENVIO_IMEDIATO.xlsx",
        "SEM_GRUPO": "04_SEM_GRUPO.xlsx",
        "OUTLET": "05_OUTLET.xlsx",
        "RELATORIO": "RELATORIO_CONSOLIDADO.txt",
    }

    # nome da coluna no export SQL (seu arquivo tem isso)
    SQL_EAN_KEYS = ["codbarra_produto", "CODBARRA_PRODUTO", "CODBARRA_PRODUTO ".strip()]

    def __init__(self, output_dir: Path, logger=logger_default):
        self.output_dir = Path(output_dir)
        self.logger = logger
        self.writer = AthosExcelWriter(logger=logger)

    # =========================
    # Public API
    # =========================
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

        # 1) Carregar dados
        progress(0.08, "Lendo export do SQL...")
        sql_rows = self._read_excel_any(sql_export_path)

        progress(0.14, "Lendo whitelist...")
        whitelist_rows = self._read_excel_any(whitelist_path)

        context: Dict[str, Any] = {
            "sql_export_path": sql_export_path,
            "whitelist_path": whitelist_path,
            "template_path": template_path,
            "sql_rows_count": len(sql_rows),
            "whitelist_rows_count": len(whitelist_rows),
        }

        self.logger.info(f"[AthosRunner] SQL rows: {context['sql_rows_count']}")
        self.logger.info(f"[AthosRunner] Whitelist rows: {context['whitelist_rows_count']}")

        # 2) Extrair EANs do SQL (teste)
        progress(0.18, "Extraindo EANs do SQL (teste)...")
        eans = self._extract_eans_from_sql(sql_rows)
        context["sql_eans_count"] = len(eans)

        # Para não travar template/Excel pesado no começo, limitamos teste
        TEST_LIMIT = 200
        eans_test = eans[:TEST_LIMIT]
        context["sql_eans_test_count"] = len(eans_test)

        # 3) Gerar 5 planilhas (cópia do template) + limpar e escrever EAN
        progress(0.22, "Gerando planilhas base (template)...")
        generated_files: List[Path] = []

        for idx, rule_key in enumerate(self.RULE_ORDER, start=1):
            pct = 0.22 + (idx / len(self.RULE_ORDER)) * 0.45
            progress(pct, f"Preparando {rule_key.replace('_', ' ')}...")

            out_path = self.output_dir / self.OUTPUT_NAMES[rule_key]
            self._copy_template(template_path, out_path)

            # ✅ limpar e escrever (teste)
            try:
                self.writer.write_rows(
                    out_path,
                    rows=[{"EAN": ean} for ean in eans_test],
                    clear_before=True,
                )
            except Exception as e:
                # deixa claro qual arquivo falhou (template errado, cabeçalho diferente etc.)
                raise RuntimeError(
                    f"Falha ao escrever na aba PRODUTOS do arquivo gerado: {out_path}\n"
                    f"Motivo: {e}"
                )

            generated_files.append(out_path)

        # 4) Relatório consolidado
        progress(0.72, "Gerando relatório consolidado...")
        report_path = self.output_dir / self.OUTPUT_NAMES["RELATORIO"]
        self._write_report_placeholder(report_path, context)

        # 5) Final
        progress(0.90, "Finalizando...")
        self.logger.info("[AthosRunner] Saídas geradas com teste de escrita na aba PRODUTOS (EAN).")

        progress(1.0, "Concluído ✅")
        return AthosRunResult(generated_files=generated_files, report_path=report_path)

    # =========================
    # Validation & IO
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
        try:
            from openpyxl import load_workbook
        except Exception as e:
            raise RuntimeError(f"openpyxl não disponível para ler .xlsx: {e}")

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
    # Helpers
    # =========================
    def _extract_eans_from_sql(self, sql_rows: List[Dict[str, Any]]) -> List[str]:
        """
        Extrai codbarra_produto do export do SQL.
        Faz dedupe preservando ordem.
        """
        def norm_key(k: str) -> str:
            return (k or "").strip().upper()

        # mapa de keys disponíveis
        if not sql_rows:
            return []

        keys = list(sql_rows[0].keys())
        keys_norm = {norm_key(k): k for k in keys}

        # tenta achar a chave real no arquivo
        chosen_key = None
        for candidate in self.SQL_EAN_KEYS:
            c_norm = norm_key(candidate)
            if c_norm in keys_norm:
                chosen_key = keys_norm[c_norm]
                break

        if not chosen_key:
            # fallback: tenta achar por "CODBARRA" + "PRODUTO"
            for k in keys:
                kn = norm_key(k)
                if "CODBARRA" in kn and "PRODUTO" in kn:
                    chosen_key = k
                    break

        if not chosen_key:
            raise ValueError(
                "Não encontrei a coluna de EAN no export do SQL. "
                "Esperado algo como 'codbarra_produto' / 'CODBARRA_PRODUTO'. "
                f"Colunas encontradas: {keys}"
            )

        seen = set()
        out: List[str] = []
        for row in sql_rows:
            v = row.get(chosen_key)
            if v is None:
                continue
            s = str(v).strip()
            if not s:
                continue
            if s in seen:
                continue
            seen.add(s)
            out.append(s)

        return out

    # =========================
    # Report
    # =========================
    def _write_report_placeholder(self, report_path: Path, context: Dict[str, Any]) -> None:
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        lines: List[str] = []
        lines.append("RELATÓRIO CONSOLIDADO — ROBÔ ATHOS")
        lines.append(f"Gerado em: {now}")
        lines.append("")
        lines.append("Entradas:")
        lines.append(f"- SQL export: {context.get('sql_export_path')}")
        lines.append(f"- Whitelist: {context.get('whitelist_path')}")
        lines.append(f"- Template: {context.get('template_path')}")
        lines.append("")
        lines.append("Resumo de leitura:")
        lines.append(f"- Linhas SQL (aprox): {context.get('sql_rows_count')}")
        lines.append(f"- Linhas whitelist (aprox): {context.get('whitelist_rows_count')}")
        lines.append(f"- EANs encontrados no SQL: {context.get('sql_eans_count', 0)}")
        lines.append(f"- EANs escritos (teste): {context.get('sql_eans_test_count', 0)}")
        lines.append("")
        lines.append("Ordem de processamento configurada:")
        for r in self.RULE_ORDER:
            lines.append(f"- {r}")
        lines.append("")
        lines.append("Ações (fase atual):")
        lines.append("- ✅ Planilhas geradas a partir do template.")
        lines.append("- ✅ Aba 'PRODUTOS' limpa e preenchida com EANs (teste).")
        lines.append("- ⏭️ Próximo passo: aplicar as regras e preencher colunas específicas por regra.")
        lines.append("")

        report_path.write_text("\n".join(lines), encoding="utf-8")
