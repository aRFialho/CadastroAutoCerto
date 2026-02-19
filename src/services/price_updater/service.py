from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Dict, Any
import pandas as pd

from .config_manager import ConfigManager
from .excel_processor_supplier_fixed import ExcelProcessorUnified


StatusCb = Optional[Callable[[str], None]]
ProgressCb = Optional[Callable[[float], None]]


class PriceUpdaterService:
    def __init__(self):
        self.config = ConfigManager()

    def get_saved_base_file(self) -> str:
        return self.config.get_base_file_path()

    def save_base_file(self, path: str) -> None:
        self.config.set_base_file_path(path)

    def _detect_header_row(self, products_file: Path, sheet_name: str = "PRODUTO") -> int:
        preview = pd.read_excel(products_file, sheet_name=sheet_name, header=None, nrows=6, engine="openpyxl")
        for i in range(len(preview)):
            row = preview.iloc[i].astype(str).tolist()
            if any(str(x).strip() == "Código Fabricante" for x in row):
                return i
        return 0

    def run(
        self,
        base_file: Path,
        products_file: Path,
        mode: str = "Fábrica",
        apply_90_cents_rule: bool = True,
        status_callback: StatusCb = None,
        progress_callback: ProgressCb = None,
    ) -> Dict[str, Any]:
        def status(msg: str):
            if status_callback:
                status_callback(msg)

        def prog(v: float):
            if progress_callback:
                progress_callback(max(0.0, min(1.0, float(v))))

        prog(0.02)
        status("💰 Carregando base de custos...")
        engine = ExcelProcessorUnified(mode=mode)

        ok = engine.load_base_data(base_file, log_callback=status_callback)
        if not ok:
            raise RuntimeError("Falha ao carregar base de custos (verifique colunas/abas/cabeçalho).")

        prog(0.15)
        status("📖 Lendo aba PRODUTO da planilha de produtos...")

        header_row = self._detect_header_row(products_file, sheet_name="PRODUTO")
        df = pd.read_excel(products_file, sheet_name="PRODUTO", header=header_row, engine="openpyxl")

        if "Código Fabricante" not in df.columns:
            raise RuntimeError("Coluna 'Código Fabricante' não encontrada na aba PRODUTO.")

        # Garantir colunas de saída
        out_cols = ["VR Custo Total", "Custo Frete", "Custo IPI", "Preço de Venda", "Preço Promoção"]
        for c in out_cols:
            if c not in df.columns:
                df[c] = 0.0

        total = len(df)
        updated = 0
        not_found = 0
        skipped = 0

        prog(0.20)
        status("⚙️ Processando códigos e calculando preços...")

        for i, row in df.iterrows():
            code = row.get("Código Fabricante", "")
            code_str = str(code).strip() if pd.notna(code) else ""

            if not code_str:
                skipped += 1
                continue

            res = engine.process_code(code_str, log_callback=status_callback)

            if res.get("found"):
                df.at[i, "VR Custo Total"] = float(res.get("vr_custo_total", 0.0) or 0.0)
                df.at[i, "Custo Frete"] = float(res.get("custo_frete", 0.0) or 0.0)
                df.at[i, "Custo IPI"] = float(res.get("custo_ipi", 0.0) or 0.0)

                pv = float(res.get("preco_de_venda", 0.0) or 0.0)
                pp = float(res.get("preco_promocao", 0.0) or 0.0)

                if apply_90_cents_rule:
                    if pv > 0:
                        pv = engine.apply_90_cents_rule(pv)
                    if pp > 0:
                        pp = engine.apply_90_cents_rule(pp)

                df.at[i, "Preço de Venda"] = pv
                df.at[i, "Preço Promoção"] = pp
                updated += 1
            else:
                not_found += 1

            # progresso 0.20 -> 0.85
            if total > 0 and (i % 10 == 0):
                prog(0.20 + 0.65 * (i / total))

        prog(0.90)
        status("💾 Salvando na aba PRODUTO (preservando formatação)...")

        engine.save_preserving_formatting_sequential(df, products_file, log_callback=status_callback)

        prog(1.0)
        status("✅ Atualização concluída!")

        return {
            "updated": updated,
            "not_found": not_found,
            "skipped": skipped,
            "total_rows": total,
            "base_file": str(base_file),
            "products_file": str(products_file),
            "mode": mode,
        }