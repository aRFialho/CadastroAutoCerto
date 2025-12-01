"""Importador de custos de planilhas Excel por fornecedor"""

import pandas as pd
from pathlib import Path
import logging
from typing import Dict, List, Optional, Any, Tuple
import re
from dataclasses import dataclass
from datetime import datetime

from ..core.costs_database import CostsDatabase, CustoProduto, FornecedorCustos
from ..utils.logger import get_logger

logger = get_logger("costs_importer")


@dataclass
class CostsImportResult:
    """Resultado da importação de custos"""
    success: bool = False
    fornecedor: str = ""
    total_produtos: int = 0
    produtos_novos: int = 0
    produtos_atualizados: int = 0
    produtos_ignorados: int = 0
    errors: List[str] = None
    warnings: List[str] = None
    processing_time: float = 0.0

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class CostsImporter:
    """Importador de custos por fornecedor"""

    def __init__(self, db: CostsDatabase):
        self.db = db
        self.result = CostsImportResult()

        # Mapeamentos padrão de colunas (podem ser customizados por fornecedor)
        self.default_column_mapping = {
            # Identificação do produto
            "codigo": ["codigo", "cod", "código", "code", "item", "produto"],
            "nome": ["nome", "descrição", "descricao", "produto", "item", "name"],
            "ean": ["ean", "codigo_barras", "cod_barras", "barcode"],
            "referencia": ["referencia", "ref", "reference"],

            # Custos
            "custo_unitario": ["custo", "custo_unitario", "preco_custo", "valor_custo", "cost"],
            "custo_ipi": ["custo_ipi", "ipi", "valor_ipi"],
            "custo_frete": ["custo_frete", "frete", "valor_frete"],
            "custo_total": ["custo_total", "total", "valor_total"],

            # Percentuais
            "perc_ipi": ["perc_ipi", "percentual_ipi", "ipi_perc", "%_ipi"],
            "perc_frete": ["perc_frete", "percentual_frete", "frete_perc", "%_frete"],
            "markup": ["markup", "margem", "percentual_markup", "%_markup"],

            # Preços
            "preco_venda": ["preco_venda", "valor_venda", "preco", "price"],
            "preco_promocional": ["preco_promocional", "promocao", "oferta"],

            # Outros
            "unidade": ["unidade", "un", "unit"],
            "categoria": ["categoria", "grupo", "family"],
            "estoque": ["estoque", "qtd", "quantidade", "stock"]
        }

    def import_from_excel(self, file_path: Path, fornecedor_nome: str,
                          header_row: int = 1, sheet_name: str = None,
                          column_mapping: Dict[str, str] = None,
                          update_existing: bool = True,
                          progress_callback=None, status_callback=None) -> CostsImportResult:
        """
        Importa custos de planilha Excel

        Args:
            file_path: Caminho para a planilha
            fornecedor_nome: Nome do fornecedor
            header_row: Linha onde estão os cabeçalhos (1-based)
            sheet_name: Nome da aba (None = primeira aba)
            column_mapping: Mapeamento customizado de colunas
            update_existing: Se deve atualizar produtos existentes
            progress_callback: Callback para progresso (0-100)
            status_callback: Callback para status
        """
        import time
        start_time = time.time()

        try:
            self.result.fornecedor = fornecedor_nome

            if status_callback:
                status_callback(f"📖 Lendo planilha de custos: {fornecedor_nome}")

            # Ler planilha
            df = self._read_excel_file(file_path, sheet_name, header_row)

            if df is None or df.empty:
                self.result.errors.append("Planilha vazia ou não encontrada")
                return self.result

            total_rows = len(df)
            logger.info(f"Encontradas {total_rows} linhas para {fornecedor_nome}")

            # Mapear colunas
            if column_mapping:
                mapped_columns = column_mapping
            else:
                mapped_columns = self._auto_map_columns(df.columns.tolist())

            if status_callback:
                status_callback(f"📊 Processando {total_rows} produtos de {fornecedor_nome}")

            # Processar cada linha
            for index, row in df.iterrows():
                try:
                    if progress_callback:
                        progress = (index / total_rows) * 100
                        progress_callback(progress)

                    if status_callback and index % 50 == 0:
                        status_callback(f"📦 Processando produto {index + 1} de {total_rows} - {fornecedor_nome}")

                    # Processar linha
                    self._process_row(row, fornecedor_nome, mapped_columns, update_existing, file_path,
                                      index + header_row + 1)

                except Exception as e:
                    error_msg = f"Erro na linha {index + header_row + 1}: {str(e)}"
                    logger.error(error_msg)
                    self.result.errors.append(error_msg)
                    continue

            # Atualizar estatísticas do fornecedor
            self._update_fornecedor_stats(fornecedor_nome)

            # Finalizar
            self.result.processing_time = time.time() - start_time
            self.result.success = len(self.result.errors) == 0

            if status_callback:
                if self.result.success:
                    status_callback(f"✅ Importação de {fornecedor_nome} concluída!")
                else:
                    status_callback(f"⚠️ Importação de {fornecedor_nome} com {len(self.result.errors)} erros")

            if progress_callback:
                progress_callback(100)

            logger.info(f"Importação de {fornecedor_nome} concluída: {self.result.__dict__}")
            return self.result

        except Exception as e:
            self.result.processing_time = time.time() - start_time
            self.result.success = False
            error_msg = f"Erro fatal na importação de {fornecedor_nome}: {str(e)}"
            logger.error(error_msg)
            self.result.errors.append(error_msg)
            return self.result

    def _read_excel_file(self, file_path: Path, sheet_name: str = None, header_row: int = 1) -> Optional[pd.DataFrame]:
        """
        Lê o arquivo Excel e retorna os dados como DataFrame.

        file_path : Path
            Caminho do arquivo Excel.
        sheet_name : str
            Nome da aba a ser lida, fornecida pelo usuário.
        header_row : int
            Número da linha onde o cabeçalho está localizado (1-based index).
        """
        try:
            # Ajustar índice da linha do cabeçalho (1 para 0-based no pandas)
            header_index = header_row - 1 if header_row > 0 else 0

            # Verificar se a aba existe no arquivo
            excel_file = pd.ExcelFile(file_path)
            if sheet_name and sheet_name not in excel_file.sheet_names:
                logger.error(f"Aba '{sheet_name}' não encontrada. Abas disponíveis: {excel_file.sheet_names}")
                self.result.errors.append(f"Aba '{sheet_name}' não foi encontrada no arquivo")
                return None

            # Se o sheet_name for None, usar a primeira aba por padrão
            selected_sheet = sheet_name or excel_file.sheet_names[0]

            # Ler o Excel com o header_row especificado
            df = pd.read_excel(file_path, sheet_name=selected_sheet, header=header_index)

            logger.info(f"Aba '{selected_sheet}' lida com sucesso! Número de registros: {len(df)}")
            return df

        except Exception as e:
            logger.exception(f"Erro ao ler a planilha: {e}")
            self.result.errors.append(f"Falha ao processar o arquivo Excel: {str(e)}")
            return None

    def _auto_map_columns(self, excel_columns: List[str]) -> Dict[str, str]:
        """Mapeia automaticamente colunas da planilha"""
        mapped = {}

        for field, possible_names in self.default_column_mapping.items():
            for excel_col in excel_columns:
                excel_col_clean = excel_col.lower().strip()

                for possible_name in possible_names:
                    if possible_name.lower() in excel_col_clean:
                        mapped[field] = excel_col
                        break

                if field in mapped:
                    break

        logger.debug(f"Mapeamento automático: {mapped}")
        return mapped

    def _process_row(self, row: pd.Series, fornecedor: str, column_mapping: Dict[str, str],
                     update_existing: bool, file_path: Path, line_number: int):
        """Processa uma linha da planilha"""
        try:
            # Converter linha para dados do produto
            custo_data = self._row_to_cost_data(row, fornecedor, column_mapping, file_path, line_number)

            if not custo_data:
                self.result.produtos_ignorados += 1
                return

            # Verificar se produto já existe
            existing_custo = None
            if custo_data.get("codigo_produto"):
                existing_custo = self.db.get_custo_by_codigo(custo_data["codigo_produto"], fornecedor)

            if existing_custo and update_existing:
                # Atualizar produto existente
                for key, value in custo_data.items():
                    if hasattr(existing_custo, key):
                        setattr(existing_custo, key, value)

                self.db.update_custo_produto(existing_custo)
                self.result.produtos_atualizados += 1

            elif not existing_custo:
                # Criar novo produto
                custo = CustoProduto(**custo_data)
                self.db.add_custo_produto(custo)
                self.result.produtos_novos += 1

            else:
                # Produto existe mas não deve ser atualizado
                self.result.produtos_ignorados += 1

            self.result.total_produtos += 1

        except Exception as e:
            logger.error(f"Erro ao processar linha: {e}")
            raise

    def _row_to_cost_data(self, row: pd.Series, fornecedor: str, column_mapping: Dict[str, str],
                          file_path: Path, line_number: int) -> Optional[Dict[str, Any]]:
        """Converte linha da planilha para dados de custo"""
        try:
            custo_data = {
                "fornecedor": fornecedor,
                "data_importacao": datetime.now(),
                "arquivo_origem": str(file_path.name),
                "linha_origem": line_number
            }

            # Mapear campos
            for field, excel_col in column_mapping.items():
                if excel_col in row.index:
                    value = row[excel_col]
                    processed_value = self._process_field_value(field, value)

                    # Mapear para nome correto do campo
                    db_field = self._map_field_name(field)
                    custo_data[db_field] = processed_value

            # Validar dados mínimos
            if not self._validate_minimum_data(custo_data):
                return None

            # Calcular campos derivados
            self._calculate_derived_fields(custo_data)

            return custo_data

        except Exception as e:
            logger.error(f"Erro ao converter linha: {e}")
            raise

    def _map_field_name(self, field: str) -> str:
        """Mapeia nome do campo para nome do banco"""
        mapping = {
            "codigo": "codigo_produto",
            "nome": "nome_produto",
            "custo_unitario": "custo_unitario",
            "custo_ipi": "custo_com_ipi",
            "custo_frete": "custo_com_frete",
            "custo_total": "custo_total",
            "perc_ipi": "percentual_ipi",
            "perc_frete": "percentual_frete",
            "markup": "percentual_markup",
            "preco_venda": "preco_venda_sugerido",
            "preco_promocional": "preco_promocional",
            "estoque": "estoque_atual"
        }
        return mapping.get(field, field)

    def _process_field_value(self, field_name: str, value: Any) -> Any:
        """Processa valor do campo baseado no tipo"""
        try:
            if pd.isna(value) or value is None:
                return self._get_default_value(field_name)

            # Campos numéricos
            if field_name in ["custo_unitario", "custo_ipi", "custo_frete", "custo_total",
                              "perc_ipi", "perc_frete", "markup", "preco_venda", "preco_promocional"]:
                # Limpar e converter para float
                str_value = str(value).strip()
                str_value = re.sub(r'[^\d,.-]', '', str_value)  # Remove caracteres não numéricos
                str_value = str_value.replace(',', '.')  # Troca vírgula por ponto

                try:
                    return float(str_value) if str_value else 0.0
                except:
                    return 0.0

            # Campos inteiros
            elif field_name in ["estoque"]:
                try:
                    return int(float(str(value))) if str(value).strip() else 0
                except:
                    return 0

            # Campos de texto
            else:
                return str(value).strip()

        except Exception as e:
            logger.warning(f"Erro ao processar campo {field_name}: {e}")
            return self._get_default_value(field_name)

    def _get_default_value(self, field_name: str) -> Any:
        """Retorna valor padrão para o campo"""
        if field_name in ["custo_unitario", "custo_ipi", "custo_frete", "custo_total",
                          "perc_ipi", "perc_frete", "markup", "preco_venda", "preco_promocional"]:
            return 0.0
        elif field_name in ["estoque"]:
            return 0
        else:
            return ""

    def _validate_minimum_data(self, custo_data: Dict[str, Any]) -> bool:
        """Valida se produto tem dados mínimos necessários"""
        # Pelo menos código ou nome deve estar preenchido
        has_codigo = custo_data.get("codigo_produto") and str(custo_data["codigo_produto"]).strip()
        has_nome = custo_data.get("nome_produto") and str(custo_data["nome_produto"]).strip()

        return has_codigo or has_nome

    def _calculate_derived_fields(self, custo_data: Dict[str, Any]):
        """Calcula campos derivados"""
        try:
            custo_unitario = custo_data.get("custo_unitario", 0.0)
            perc_ipi = custo_data.get("percentual_ipi", 0.0)
            perc_frete = custo_data.get("percentual_frete", 0.0)

            # Calcular custo com IPI se não informado
            if not custo_data.get("custo_com_ipi") and custo_unitario > 0 and perc_ipi > 0:
                custo_data["custo_com_ipi"] = custo_unitario * (1 + perc_ipi / 100)

            # Calcular custo com frete se não informado
            if not custo_data.get("custo_com_frete") and custo_unitario > 0 and perc_frete > 0:
                custo_base = custo_data.get("custo_com_ipi", custo_unitario)
                custo_data["custo_com_frete"] = custo_base * (1 + perc_frete / 100)

            # Calcular custo total se não informado
            if not custo_data.get("custo_total"):
                custo_total = custo_data.get("custo_com_frete") or custo_data.get("custo_com_ipi") or custo_unitario
                custo_data["custo_total"] = custo_total

            # Calcular preço de venda se não informado e há markup
            markup = custo_data.get("percentual_markup", 0.0)
            if not custo_data.get("preco_venda_sugerido") and custo_data.get("custo_total", 0) > 0 and markup > 0:
                custo_data["preco_venda_sugerido"] = custo_data["custo_total"] * (1 + markup / 100)

        except Exception as e:
            logger.warning(f"Erro ao calcular campos derivados: {e}")

    def _update_fornecedor_stats(self, fornecedor_nome: str):
        """Atualiza estatísticas do fornecedor"""
        try:
            fornecedor = self.db.get_fornecedor_by_nome(fornecedor_nome)
            if fornecedor:
                # Contar produtos do fornecedor
                custos = self.db.get_custos_by_fornecedor(fornecedor_nome)
                fornecedor.total_produtos = len(custos)
                fornecedor.ultima_importacao = datetime.now()

                self.db.update_fornecedor(fornecedor)

        except Exception as e:
            logger.warning(f"Erro ao atualizar estatísticas do fornecedor: {e}")

    def get_import_preview(self, file_path: Path, header_row: int = 1,
                           sheet_name: str = None) -> Dict[str, Any]:
        """Gera prévia da importação"""
        try:
            df = self._read_excel_file(file_path, sheet_name, header_row)

            if df is None or df.empty:
                return {"error": "Planilha vazia ou não encontrada"}

            # Auto mapear colunas
            mapped_columns = self._auto_map_columns(df.columns.tolist())

            preview = {
                "total_rows": len(df),
                "header_row": header_row,
                "columns_found": list(df.columns),
                "columns_mapped": mapped_columns,
                "sample_data": [],
                "estimated_products": 0
            }

            # Analisar primeiras 3 linhas
            sample_count = min(3, len(df))
            valid_products = 0

            for index in range(sample_count):
                try:
                    row = df.iloc[index]
                    sample_product = {}

                    for field, excel_col in mapped_columns.items():
                        if excel_col in row.index:
                            value = row[excel_col]
                            sample_product[field] = str(value)[:50] if value else ""

                    if sample_product.get("codigo") or sample_product.get("nome"):
                        valid_products += 1
                        preview["sample_data"].append({
                            "linha": index + header_row + 1,
                            **sample_product
                        })

                except Exception as e:
                    logger.debug(f"Erro na análise da linha {index}: {e}")

            # Estimar produtos válidos
            if sample_count > 0:
                success_rate = valid_products / sample_count
                preview["estimated_products"] = int(len(df) * success_rate)

            return preview

        except Exception as e:
            logger.error(f"Erro ao gerar preview: {e}")
            return {"error": str(e)}

    def clear_and_reimport(self, file_path: Path, fornecedor_nome: str,
                           header_row: int = 1, sheet_name: str = None,
                           column_mapping: Dict[str, str] = None,
                           progress_callback=None, status_callback=None) -> CostsImportResult:
        """Limpa dados do fornecedor e reimporta"""
        try:
            if status_callback:
                status_callback(f"🗑️ Limpando custos de {fornecedor_nome}...")

            self.db.delete_custos_fornecedor(fornecedor_nome)

            if status_callback:
                status_callback(f"📥 Importando custos de {fornecedor_nome}...")

            return self.import_from_excel(
                file_path, fornecedor_nome, header_row, sheet_name,
                column_mapping, update_existing=False,
                progress_callback=progress_callback,
                status_callback=status_callback
            )

        except Exception as e:
            error_msg = f"Erro na reimportação de {fornecedor_nome}: {str(e)}"
            logger.error(error_msg)
            self.result.errors.append(error_msg)
            return self.result