"""Importador de catálogo de produtos da planilha Excel"""

import pandas as pd
from pathlib import Path
import logging
from typing import Dict, List, Optional, Any
import re
from dataclasses import dataclass

from ..core.product_catalog_database import ProductCatalogDatabase, ProdutoCatalogo
from ..utils.logger import get_logger

logger = get_logger("catalog_importer")

@dataclass
class CatalogImportResult:
    """Resultado da importação do catálogo"""
    success: bool = False
    total_produtos: int = 0
    produtos_atualizados: int = 0
    produtos_novos: int = 0
    produtos_ignorados: int = 0
    errors: List[str] = None
    warnings: List[str] = None
    processing_time: float = 0.0

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []

class CatalogImporter:
    """Importador de catálogo de produtos"""

    def __init__(self, db: ProductCatalogDatabase):
        self.db = db
        self.result = CatalogImportResult()

        # ✅ MAPEAMENTO CORRETO DAS 13 COLUNAS DA IMAGEM
        self.column_mapping = {
            # Colunas exatas da planilha → campos do banco
            "COD AUXILIAR": "cod_auxiliar",
            "COD BARRA": "cod_barra",
            "COD FABRIC": "cod_fabric",
            "MARCA": "marca",
            "DISPONÍVEL": "disponivel",
            "PREÇO": "preco",
            "PROMOÇÃO": "promocao",
            "COMPLEMENTO": "complemento",
            "CATEGORIA": "categoria",
            "ESTOQUE SEG": "estoque_seg",
            "CUSTO TOTAL": "custo_total",
            "DIAS P/ ENTREGA": "dias_p_entrega",
            "SITE_DISPONIBILIDADE": "site_disponibilidade",

            # ✅ VARIAÇÕES POSSÍVEIS DOS NOMES DAS COLUNAS
            "Cod Auxiliar": "cod_auxiliar",
            "Cod Barra": "cod_barra",
            "Cod Fabric": "cod_fabric",
            "Marca": "marca",
            "Disponível": "disponivel",
            "Preço": "preco",
            "Promoção": "promocao",
            "Complemento": "complemento",
            "Categoria": "categoria",
            "Estoque Seg": "estoque_seg",
            "Custo Total": "custo_total",
            "Dias p/ Entrega": "dias_p_entrega",
            "Site_Disponibilidade": "site_disponibilidade",

            # ✅ MAIS VARIAÇÕES
            "cod_auxiliar": "cod_auxiliar",
            "cod_barra": "cod_barra",
            "cod_fabric": "cod_fabric",
            "marca": "marca",
            "disponivel": "disponivel",
            "preco": "preco",
            "promocao": "promocao",
            "complemento": "complemento",
            "categoria": "categoria",
            "estoque_seg": "estoque_seg",
            "custo_total": "custo_total",
            "dias_p_entrega": "dias_p_entrega",
            "site_disponibilidade": "site_disponibilidade"
        }

    def import_from_excel(self, file_path: Path, sheet_name: str = None,
                         update_existing: bool = True, progress_callback=None,
                         status_callback=None) -> CatalogImportResult:
        """
        Importa catálogo da planilha Excel

        Args:
            file_path: Caminho para a planilha
            sheet_name: Nome da aba (None = primeira aba)
            update_existing: Se deve atualizar produtos existentes
            progress_callback: Callback para progresso (0-100)
            status_callback: Callback para status
        """
        import time
        start_time = time.time()

        try:
            if status_callback:
                status_callback("📖 Lendo planilha do catálogo...")

            # Ler planilha
            df = self._read_excel_file(file_path, sheet_name)

            if df is None or df.empty:
                self.result.errors.append("Planilha vazia ou não encontrada")
                return self.result

            total_rows = len(df)
            logger.info(f"Encontradas {total_rows} linhas na planilha")

            if status_callback:
                status_callback(f"📊 Processando {total_rows} produtos...")

            # Processar cada linha
            for index, row in df.iterrows():
                try:
                    if progress_callback:
                        progress = (index / total_rows) * 100
                        progress_callback(progress)

                    if status_callback and index % 50 == 0:
                        status_callback(f"📦 Processando produto {index + 1} de {total_rows}...")

                    # Processar linha
                    self._process_row(row, update_existing)

                except Exception as e:
                    error_msg = f"Erro na linha {index + 2}: {str(e)}"
                    logger.error(error_msg)
                    self.result.errors.append(error_msg)
                    continue

            # Finalizar
            self.result.processing_time = time.time() - start_time
            self.result.success = len(self.result.errors) == 0

            if status_callback:
                if self.result.success:
                    status_callback("✅ Importação concluída com sucesso!")
                else:
                    status_callback(f"⚠️ Importação concluída com {len(self.result.errors)} erros")

            if progress_callback:
                progress_callback(100)

            logger.info(f"Importação concluída: {self.result.__dict__}")
            return self.result

        except Exception as e:
            self.result.processing_time = time.time() - start_time
            self.result.success = False
            error_msg = f"Erro fatal na importação: {str(e)}"
            logger.error(error_msg)
            self.result.errors.append(error_msg)
            return self.result

    def _read_excel_file(self, file_path: Path, sheet_name: str = None) -> Optional[pd.DataFrame]:
        """Lê arquivo Excel"""
        try:
            # Ler Excel
            if sheet_name:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
            else:
                # Usar primeira aba
                df = pd.read_excel(file_path)

            # Limpar dados
            df = df.fillna("")  # Substituir NaN por string vazia

            # Remover linhas completamente vazias
            df = df.dropna(how='all')

            # Limpar nomes das colunas (remover espaços extras)
            df.columns = df.columns.str.strip()

            logger.info(f"Planilha lida com sucesso: {len(df)} linhas, {len(df.columns)} colunas")
            logger.debug(f"Colunas encontradas: {list(df.columns)}")

            return df

        except Exception as e:
            logger.error(f"Erro ao ler planilha: {e}")
            self.result.errors.append(f"Erro ao ler planilha: {str(e)}")
            return None

    def _process_row(self, row: pd.Series, update_existing: bool):
        """Processa uma linha da planilha"""
        try:
            # Converter linha para dicionário de produto
            produto_data = self._row_to_product_data(row)

            if not produto_data:
                self.result.produtos_ignorados += 1
                return

            # ✅ VERIFICAR SE PRODUTO JÁ EXISTE (por COD AUXILIAR ou COD BARRA)
            existing_produto = None

            if produto_data.get("cod_auxiliar"):
                existing_produto = self.db.get_produto_by_cod_auxiliar(produto_data["cod_auxiliar"])

            if not existing_produto and produto_data.get("cod_barra"):
                existing_produto = self.db.get_produto_by_cod_barra(produto_data["cod_barra"])

            # Criar objeto produto
            if existing_produto and update_existing:
                # Atualizar produto existente
                for key, value in produto_data.items():
                    if hasattr(existing_produto, key):
                        setattr(existing_produto, key, value)

                self.db.update_produto(existing_produto)
                self.result.produtos_atualizados += 1
                logger.debug(f"Produto atualizado: {existing_produto.marca} - {existing_produto.cod_auxiliar}")

            elif not existing_produto:
                # Criar novo produto
                produto = ProdutoCatalogo(**produto_data)
                self.db.add_produto(produto)
                self.result.produtos_novos += 1
                logger.debug(f"Produto criado: {produto.marca} - {produto.cod_auxiliar}")

            else:
                # Produto existe mas não deve ser atualizado
                self.result.produtos_ignorados += 1
                logger.debug(f"Produto ignorado (já existe): {produto_data.get('marca', 'N/A')} - {produto_data.get('cod_auxiliar', 'N/A')}")

            self.result.total_produtos += 1

        except Exception as e:
            logger.error(f"Erro ao processar linha: {e}")
            raise

    def _row_to_product_data(self, row: pd.Series) -> Optional[Dict[str, Any]]:
        """Converte linha da planilha para dados do produto"""
        try:
            produto_data = {}

            # ✅ MAPEAR TODAS AS 13 COLUNAS EXATAS
            for excel_col in row.index:
                excel_col_clean = str(excel_col).strip()

                # Mapear cada coluna exata
                if excel_col_clean == "COD AUXILIAR":
                    produto_data["cod_auxiliar"] = self._process_field_value("cod_auxiliar", row[excel_col])
                elif excel_col_clean == "COD BARRA":
                    produto_data["cod_barra"] = self._process_field_value("cod_barra", row[excel_col])
                elif excel_col_clean == "COD FABRIC":
                    produto_data["cod_fabric"] = self._process_field_value("cod_fabric", row[excel_col])
                elif excel_col_clean == "MARCA":
                    produto_data["marca"] = self._process_field_value("marca", row[excel_col])
                elif excel_col_clean == "DISPONÍVEL":
                    produto_data["disponivel"] = self._process_field_value("disponivel", row[excel_col])
                elif excel_col_clean == "PREÇO":
                    produto_data["preco"] = self._process_field_value("preco", row[excel_col])
                elif excel_col_clean == "PROMOÇÃO":
                    produto_data["promocao"] = self._process_field_value("promocao", row[excel_col])
                elif excel_col_clean == "COMPLEMENTO":
                    produto_data["complemento"] = self._process_field_value("complemento", row[excel_col])
                elif excel_col_clean == "CATEGORIA":
                    produto_data["categoria"] = self._process_field_value("categoria", row[excel_col])
                elif excel_col_clean == "ESTOQUE SEG":
                    produto_data["estoque_seg"] = self._process_field_value("estoque_seg", row[excel_col])
                elif excel_col_clean == "CUSTO TOTAL":
                    produto_data["custo_total"] = self._process_field_value("custo_total", row[excel_col])
                elif excel_col_clean == "DIAS P/ ENTREGA":
                    produto_data["dias_p_entrega"] = self._process_field_value("dias_p_entrega", row[excel_col])
                elif excel_col_clean == "SITE_DISPONIBILIDADE":
                    produto_data["site_disponibilidade"] = self._process_field_value("site_disponibilidade",
                                                                                     row[excel_col])

            # ✅ GARANTIR QUE TODOS OS CAMPOS EXISTAM (mesmo que vazios)
            required_fields = [
                "cod_auxiliar", "cod_barra", "cod_fabric", "marca", "disponivel",
                "preco", "promocao", "complemento", "categoria", "estoque_seg",
                "custo_total", "dias_p_entrega", "site_disponibilidade"
            ]

            for field in required_fields:
                if field not in produto_data:
                    produto_data[field] = ""

            # Validar se produto tem dados mínimos necessários
            if not self._validate_minimum_data(produto_data):
                warning_msg = f"Produto ignorado - dados insuficientes: {produto_data.get('marca', 'N/A')} - {produto_data.get('cod_auxiliar', 'N/A')}"
                logger.warning(warning_msg)
                self.result.warnings.append(warning_msg)
                return None

            # ✅ LOG PARA DEBUG - REMOVER DEPOIS
            logger.debug(f"Produto processado: {produto_data}")

            return produto_data

        except Exception as e:
            logger.error(f"Erro ao converter linha: {e}")
            raise

    def _process_field_value(self, field_name: str, value: Any) -> str:
        """Processa valor do campo (todos são strings no modelo atual)"""
        try:
            # Converter para string e limpar
            if pd.isna(value) or value is None:
                return ""

            str_value = str(value).strip()

            # ✅ TODOS OS CAMPOS SÃO TEXTO NO MODELO ATUAL
            return str_value if str_value else ""

        except Exception as e:
            logger.warning(f"Erro ao processar campo {field_name}: {e}")
            return ""

    def _get_default_value(self, field_name: str) -> str:
        """Retorna valor padrão para o campo (todos são strings)"""
        # ✅ TODOS OS CAMPOS SÃO STRINGS NO NOVO MODELO
        return ""

    def _validate_minimum_data(self, produto_data: Dict[str, Any]) -> bool:
        """Valida se produto tem dados mínimos necessários"""
        # ✅ PELO MENOS UM DOS CAMPOS PRINCIPAIS DEVE ESTAR PREENCHIDO
        required_fields = ["cod_auxiliar", "cod_barra", "marca"]

        for field in required_fields:
            value = produto_data.get(field, "")
            if value and str(value).strip():
                return True

        return False

    def get_import_preview(self, file_path: Path, sheet_name: str = None) -> Dict[str, Any]:
        """
        Gera prévia da importação sem salvar no banco

        Returns:
            Dict com informações sobre o que seria importado
        """
        try:
            # Ler planilha
            df = self._read_excel_file(file_path, sheet_name)

            if df is None or df.empty:
                return {"error": "Planilha vazia ou não encontrada"}

            preview = {
                "total_rows": len(df),
                "columns_found": list(df.columns),
                "columns_mapped": [],
                "columns_missing": [],
                "sample_data": [],
                "estimated_products": 0
            }

            # ✅ VERIFICAR MAPEAMENTO DE COLUNAS
            mapped_columns = set()
            for excel_col in df.columns:
                if excel_col in self.column_mapping:
                    db_field = self.column_mapping[excel_col]
                    if db_field not in mapped_columns:  # Evitar duplicatas
                        preview["columns_mapped"].append(f"{excel_col} → {db_field}")
                        mapped_columns.add(db_field)

            # ✅ VERIFICAR COLUNAS FALTANDO
            essential_columns = ["COD AUXILIAR", "COD BARRA", "MARCA", "CATEGORIA"]
            for col in essential_columns:
                found = any(col.lower() in excel_col.lower() for excel_col in df.columns)
                if not found:
                    preview["columns_missing"].append(col)

            # Analisar primeiras 5 linhas como amostra
            sample_count = min(5, len(df))
            valid_products = 0

            for index in range(sample_count):
                try:
                    row = df.iloc[index]
                    produto_data = self._row_to_product_data(row)

                    if produto_data:
                        valid_products += 1
                        sample_product = {
                            "linha": index + 2,  # +2 porque Excel começa em 1 e tem cabeçalho
                            "marca": produto_data.get("marca", "N/A"),
                            "cod_auxiliar": produto_data.get("cod_auxiliar", "N/A"),
                            "cod_barra": produto_data.get("cod_barra", "N/A"),
                            "categoria": produto_data.get("categoria", "N/A")
                        }
                        preview["sample_data"].append(sample_product)

                except Exception as e:
                    logger.debug(f"Erro na análise da linha {index + 2}: {e}")

            # Estimar produtos válidos baseado na amostra
            if sample_count > 0:
                success_rate = valid_products / sample_count
                preview["estimated_products"] = int(len(df) * success_rate)

            return preview

        except Exception as e:
            logger.error(f"Erro ao gerar preview: {e}")
            return {"error": str(e)}

    def clear_and_reimport(self, file_path: Path, sheet_name: str = None,
                          progress_callback=None, status_callback=None) -> CatalogImportResult:
        """Limpa dados existentes e reimporta"""
        try:
            if status_callback:
                status_callback("🗑️ Limpando catálogo existente...")

            self.db.clear_all_data()

            if status_callback:
                status_callback("📥 Iniciando nova importação...")

            return self.import_from_excel(
                file_path,
                sheet_name,
                update_existing=False,  # Não precisa atualizar se limpou tudo
                progress_callback=progress_callback,
                status_callback=status_callback
            )

        except Exception as e:
            error_msg = f"Erro na reimportação: {str(e)}"
            logger.error(error_msg)
            self.result.errors.append(error_msg)
            return self.result

    def validate_excel_structure(self, file_path: Path, sheet_name: str = None) -> Dict[str, Any]:
        """Valida estrutura da planilha Excel"""
        try:
            df = self._read_excel_file(file_path, sheet_name)

            if df is None:
                return {"valid": False, "error": "Não foi possível ler a planilha"}

            validation = {
                "valid": True,
                "total_columns": len(df.columns),
                "total_rows": len(df),
                "required_columns_found": 0,
                "missing_columns": [],
                "extra_columns": [],
                "warnings": []
            }

            # ✅ VERIFICAR COLUNAS ESSENCIAIS
            required_columns = ["COD AUXILIAR", "COD BARRA", "MARCA", "CATEGORIA"]

            for col in required_columns:
                # Busca flexível por nome de coluna
                found = any(col.lower() in excel_col.lower() for excel_col in df.columns)
                if found:
                    validation["required_columns_found"] += 1
                else:
                    validation["missing_columns"].append(col)

            # Verificar colunas extras (não mapeadas)
            mapped_columns = set(self.column_mapping.keys())
            excel_columns = set(df.columns)

            validation["extra_columns"] = list(excel_columns - mapped_columns)

            # Validações
            if validation["required_columns_found"] < 2:  # Pelo menos 2 das 4 essenciais
                validation["valid"] = False
                validation["warnings"].append("Poucas colunas obrigatórias encontradas")

            if len(df) == 0:
                validation["valid"] = False
                validation["warnings"].append("Planilha não contém dados")

            return validation

        except Exception as e:
            return {
                "valid": False,
                "error": f"Erro ao validar planilha: {str(e)}"
            }