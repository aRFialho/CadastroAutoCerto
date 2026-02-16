"""
Service: AthosExcelWriter
Responsável por escrever no template Athos:
- SEMPRE na aba "PRODUTOS"
- Encontrar colunas por nome (robusto)
- Limpar dados antigos (mantendo cabeçalho)
- Inserir linhas com base em dicionários {coluna: valor}

Obs:
- Não assume posição fixa de colunas
- Evita mexer em outras abas
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils.logger import get_logger

logger_default = get_logger("athos_excel_writer")


@dataclass
class ColumnMap:
    """Mapeamento coluna->índice (1-based)"""
    by_name: Dict[str, int]
    header_row: int
    first_data_row: int


class AthosExcelWriter:
    SHEET_NAME = "PRODUTOS"

    # Aliases comuns (normalizados) -> nome canônico
    # (Você pode ampliar depois sem quebrar nada)
    CANONICAL_COLUMNS = {
        "EAN": ["EAN", "CÓD BARRA", "COD BARRA", "CODBARRA", "CÓDIGO DE BARRAS", "CODIGO DE BARRAS"],
        "ESTOQUE_SEG": ["ESTOQUE SEG", "ESTOQUE SEGURANÇA", "ESTOQUE SEGURANCA", "ESTOQUE DE SEGURANÇA"],
        "DATA_ENTREGA": ["DATA ENTREGA", "DIAS PARA ENTREGA", "DIAS PRA ENTREGA", "PRAZO", "PRAZO ENTREGA"],
        "SITE_DISP": ["SITE DISPONIBILIDADE", "SITE DISP", "DISPONIBILIDADE SITE", "DISPONIBILIDADE"],
        "GRUPO3": ["GRUPO3", "NOME GRUPO3", "GRUPO 3"],
        "GRUPO3_APAGAR": ["GRUPO3 APAGAR", "APAGAR GRUPO3", "REMOVER GRUPO3", "GRUPO3 REMOVER"],
        "PRODUTO_INATIVO": ["PRODUTO INATIVO", "INATIVO", "ATIVO?"],
        "COD_FABRICANTE": ["CÓD FABRICANTE", "COD FABRICANTE", "CODIGO FABRICANTE", "CÓDIGO FABRICANTE"],
    }

    def __init__(self, logger=logger_default):
        self.logger = logger

    # =========================
    # Public API
    # =========================
    def clear_products_sheet(self, xlsx_path: Path) -> None:
        """Limpa dados existentes na aba PRODUTOS (mantém cabeçalho)."""
        wb, ws = self._open_wb_sheet(xlsx_path)
        colmap = self._build_column_map(ws)

        # Limpa da first_data_row até last
        max_row = ws.max_row or colmap.first_data_row
        if max_row >= colmap.first_data_row:
            for r in range(colmap.first_data_row, max_row + 1):
                for c in range(1, ws.max_column + 1):
                    ws.cell(row=r, column=c).value = None

        wb.save(xlsx_path)

    def write_rows(self, xlsx_path: Path, rows: List[Dict[str, Any]], *, clear_before: bool = True) -> ColumnMap:
        """
        Escreve lista de linhas (dicts).
        keys do dict podem ser:
        - nomes canônicos (EAN, ESTOQUE_SEG, DATA_ENTREGA, SITE_DISP, GRUPO3, GRUPO3_APAGAR, PRODUTO_INATIVO, COD_FABRICANTE)
        - ou nomes "humanos" que existam no cabeçalho

        Retorna ColumnMap para debug.
        """
        wb, ws = self._open_wb_sheet(xlsx_path)
        colmap = self._build_column_map(ws)

        if clear_before:
            self._clear_ws_data(ws, colmap)

        if not rows:
            wb.save(xlsx_path)
            return colmap

        # escreve a partir de first_data_row
        r = colmap.first_data_row
        for item in rows:
            self._write_one(ws, colmap, r, item)
            r += 1

        wb.save(xlsx_path)
        return colmap

    # =========================
    # Internal
    # =========================
    def _open_wb_sheet(self, xlsx_path: Path):
        try:
            from openpyxl import load_workbook
        except Exception as e:
            raise RuntimeError(f"openpyxl necessário para escrever no template: {e}")

        wb = load_workbook(xlsx_path)
        if self.SHEET_NAME not in wb.sheetnames:
            raise ValueError(
                f"Template não possui aba '{self.SHEET_NAME}'. "
                f"Abas encontradas: {wb.sheetnames}"
            )
        ws = wb[self.SHEET_NAME]
        return wb, ws

    def _normalize(self, s: str) -> str:
        s = (s or "").strip().upper()
        # normalização leve: remove múltiplos espaços
        s = " ".join(s.split())
        return s

    def _find_header_row(self, ws, max_scan_rows: int = 30) -> int:
        """
        Encontra linha do cabeçalho procurando por 'EAN' ou 'CÓD BARRA' etc.
        Se não achar, assume 1.
        """
        target_tokens = set(self._normalize(x) for x in self.CANONICAL_COLUMNS["EAN"])
        for r in range(1, min(max_scan_rows, ws.max_row or 1) + 1):
            values = [self._normalize(str(c.value)) if c.value is not None else "" for c in ws[r]]
            if any(v in target_tokens for v in values):
                return r
        return 1

    def _build_column_map(self, ws) -> ColumnMap:
        header_row = self._find_header_row(ws)
        headers = []
        for cell in ws[header_row]:
            headers.append(self._normalize(str(cell.value)) if cell.value is not None else "")

        by_name: Dict[str, int] = {}

        # 1) mapeia cabeçalho real
        for idx, h in enumerate(headers, start=1):
            if h:
                by_name[h] = idx

        # 2) mapeia nomes canônicos -> coluna existente (via aliases)
        for canonical, aliases in self.CANONICAL_COLUMNS.items():
            found_idx = None
            for a in aliases:
                a_norm = self._normalize(a)
                if a_norm in by_name:
                    found_idx = by_name[a_norm]
                    break
            if found_idx is not None:
                by_name[canonical] = found_idx

        # Validação mínima: precisa ter EAN
        if "EAN" not in by_name:
            # tenta encontrar qualquer alias de EAN mesmo se não mapeou acima
            raise ValueError(
                "Não encontrei a coluna EAN/Cód Barra no cabeçalho da aba PRODUTOS. "
                "Confira se o template é o correto."
            )

        # primeira linha de dados = header_row + 1 (padrão)
        first_data_row = header_row + 1
        return ColumnMap(by_name=by_name, header_row=header_row, first_data_row=first_data_row)

    def _clear_ws_data(self, ws, colmap: ColumnMap) -> None:
        max_row = ws.max_row or colmap.first_data_row
        if max_row < colmap.first_data_row:
            return

        for r in range(colmap.first_data_row, max_row + 1):
            for c in range(1, ws.max_column + 1):
                ws.cell(row=r, column=c).value = None

    def _resolve_col(self, colmap: ColumnMap, key: str) -> Optional[int]:
        """
        Resolve coluna por:
        - chave canônica (EAN, ESTOQUE_SEG, ...)
        - nome exato do cabeçalho (normalizado)
        """
        k = self._normalize(key)

        # se já é canônico
        if k in colmap.by_name:
            return colmap.by_name[k]

        # se é um canônico sem normalizar (ex.: 'DATA_ENTREGA')
        if key in colmap.by_name:
            return colmap.by_name[key]

        # tenta mapear aliases canônicos
        for canonical, aliases in self.CANONICAL_COLUMNS.items():
            if k == self._normalize(canonical):
                return colmap.by_name.get(canonical)
            if any(k == self._normalize(a) for a in aliases):
                # se alias estiver no cabeçalho, resolve por ele
                idx = colmap.by_name.get(k)
                if idx is not None:
                    return idx
                return colmap.by_name.get(canonical)

        return None

    def _write_one(self, ws, colmap: ColumnMap, row_idx: int, item: Dict[str, Any]) -> None:
        """
        Escreve uma linha.
        Se o dict tiver apenas {'EAN': '...'} funciona.
        """
        # primeiro: garantir EAN
        if "EAN" not in item and "CÓD BARRA" not in item and "COD BARRA" not in item and "CODBARRA" not in item:
            # tenta achar qualquer chave parecida
            for k in list(item.keys()):
                if self._normalize(k) in [self._normalize(x) for x in self.CANONICAL_COLUMNS["EAN"]]:
                    item["EAN"] = item[k]
                    break

        if "EAN" not in item:
            raise ValueError("Linha sem EAN/Cód Barra. EAN é obrigatório para aplicar alterações no Athos.")

        for key, value in item.items():
            col = self._resolve_col(colmap, key)
            if col is None:
                # ignora campos que não existem no template
                continue
            ws.cell(row=row_idx, column=col).value = value
