"""Sistema de banco de dados de fornecedores"""

import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import re

from ..utils.logger import get_logger

logger = get_logger("supplier_database")


@dataclass
class Supplier:
    """Modelo de fornecedor"""
    id: Optional[int]
    name: str
    code: int
    prazo_dias: int = 0  # ✅ NOVO CAMPO PRAZO


class SupplierDatabase:
    """Gerenciador do banco de dados de fornecedores"""

    def __init__(self, db_path: Optional[Path] = None):
        """Inicializa o banco de dados"""
        if db_path is None:
            # ✅ SEMPRE USAR OUTPUTS EM VEZ DE DATA
            project_root = Path(__file__).parent.parent.parent
            outputs_dir = project_root / "outputs"
            outputs_dir.mkdir(exist_ok=True)
            db_path = outputs_dir / "suppliers.db"

            logger.info(f"🗄️ Usando banco padrão: {db_path}")

        self.db_path = db_path
        self._init_database()

        # ✅ ADICIONAR ESTA LINHA
        self.debug_database_complete()

        logger.info(f"Banco de fornecedores inicializado: {self.db_path}")

    def _init_database(self):
        """Inicializa as tabelas do banco com migração completa de dados"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # ✅ VERIFICAR TODAS AS TABELAS EXISTENTES
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            all_tables = [row[0] for row in cursor.fetchall()]
            logger.info(f"🔍 Tabelas existentes no banco: {all_tables}")

            # ✅ VERIFICAR SE EXISTE TABELA COM ESTRUTURA ANTIGA
            old_table_found = False
            for table_name in all_tables:
                if 'suppliers' in table_name.lower():
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    columns_info = cursor.fetchall()
                    columns = [col[1] for col in columns_info]

                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    record_count = cursor.fetchone()[0]

                    logger.info(f"📋 Tabela '{table_name}': {columns}, Registros: {record_count}")

                    # ✅ SE ENCONTROU TABELA COM DADOS E ESTRUTURA ANTIGA
                    if record_count > 0 and 'created_at' in columns and 'prazo_dias' not in columns:
                        logger.warning(f"🔄 MIGRAÇÃO NECESSÁRIA: Tabela '{table_name}' tem dados na estrutura antiga!")
                        old_table_found = True

                        # ✅ CRIAR NOVA TABELA COM ESTRUTURA CORRETA
                        cursor.execute("DROP TABLE IF EXISTS suppliers_new")
                        cursor.execute("""
                            CREATE TABLE suppliers_new (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                name TEXT NOT NULL UNIQUE,
                                code INTEGER NOT NULL UNIQUE,
                                prazo_dias INTEGER DEFAULT 0
                            )
                        """)

                        # ✅ MIGRAR DADOS DA TABELA ANTIGA PARA A NOVA
                        cursor.execute(f"""
                            INSERT INTO suppliers_new (name, code, prazo_dias)
                            SELECT name, code, 0 as prazo_dias
                            FROM {table_name}
                        """)

                        migrated_count = cursor.rowcount
                        logger.success(f"✅ {migrated_count} registros migrados da tabela '{table_name}'")

                        # ✅ REMOVER TABELA ANTIGA E RENOMEAR A NOVA
                        cursor.execute(f"DROP TABLE {table_name}")
                        cursor.execute("ALTER TABLE suppliers_new RENAME TO suppliers")

                        # ✅ DEFINIR PRAZOS PADRÃO
                        default_prazos = {
                            'DMOV': 15,
                            'SPEZZIA': 10,
                            'MADETECY': 12,
                            'RIVATTI': 8,
                            'DROSSI': 7
                        }

                        updated_count = 0
                        for name_part, prazo in default_prazos.items():
                            cursor.execute(
                                "UPDATE suppliers SET prazo_dias = ? WHERE name LIKE ?",
                                (prazo, f'%{name_part}%')
                            )
                            rows_affected = cursor.rowcount
                            if rows_affected > 0:
                                updated_count += rows_affected
                                logger.success(
                                    f"✅ Prazo definido: {name_part} = {prazo} dias ({rows_affected} registros)")

                        logger.success(f"🎯 Migração completa! {updated_count} registros com prazo definido")
                        break

            # ✅ SE NÃO ENCONTROU TABELA ANTIGA, CRIAR NOVA
            if not old_table_found:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='suppliers'")
                table_exists = cursor.fetchone()

                if not table_exists:
                    logger.info("📋 Criando nova tabela suppliers...")
                    cursor.execute("""
                        CREATE TABLE suppliers (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT NOT NULL UNIQUE,
                            code INTEGER NOT NULL UNIQUE,
                            prazo_dias INTEGER DEFAULT 0
                        )
                    """)

            conn.commit()

            # ✅ VERIFICAÇÃO FINAL
            cursor.execute("SELECT COUNT(*) FROM suppliers")
            final_count = cursor.fetchone()[0]
            logger.success(f"✅ Banco inicializado! Total de fornecedores: {final_count}")

            # ✅ MOSTRAR ALGUNS REGISTROS PARA DEBUG
            if final_count > 0:
                cursor.execute("SELECT id, name, code, prazo_dias FROM suppliers LIMIT 5")
                sample_records = cursor.fetchall()
                logger.info("📋 Amostra de registros:")
                for record in sample_records:
                    logger.info(f"  - ID={record[0]}, Nome='{record[1]}', Código={record[2]}, Prazo={record[3]}")

                # ✅ VERIFICAR SE DMOV EXISTE
                cursor.execute("SELECT * FROM suppliers WHERE name LIKE '%DMOV%'")
                dmov_records = cursor.fetchall()
                if dmov_records:
                    for record in dmov_records:
                        logger.success(
                            f"🎯 DMOV encontrado: ID={record[0]}, Nome='{record[1]}', Código={record[2]}, Prazo={record[3]}")

    def add_supplier(self, name: str, code: int, prazo_dias: int = 0) -> bool:
        """Adiciona um novo fornecedor"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # ✅ INCLUIR PRAZO_DIAS NO INSERT
                cursor.execute(
                    "INSERT INTO suppliers (name, code, prazo_dias) VALUES (?, ?, ?)",
                    (name.strip(), code, prazo_dias)
                )
                conn.commit()

                logger.info(f"Fornecedor adicionado: {name} (Código: {code}, Prazo: {prazo_dias} dias)")
                return True

        except sqlite3.IntegrityError as e:
            if "name" in str(e):
                logger.error(f"Fornecedor '{name}' já existe")
            elif "code" in str(e):
                logger.error(f"Código {code} já está em uso")
            else:
                logger.error(f"Erro de integridade: {e}")
            return False
        except Exception as e:
            logger.error(f"Erro ao adicionar fornecedor: {e}")
            return False

    def update_supplier(self, supplier_id: int, name: str, code: int, prazo_dias: int = 0) -> bool:
        """Atualiza um fornecedor existente"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # ✅ INCLUIR PRAZO_DIAS NO UPDATE
                cursor.execute(
                    "UPDATE suppliers SET name = ?, code = ?, prazo_dias = ? WHERE id = ?",
                    (name.strip(), code, prazo_dias, supplier_id)
                )

                if cursor.rowcount == 0:
                    logger.warning(f"Fornecedor com ID {supplier_id} não encontrado")
                    return False

                conn.commit()
                logger.info(f"Fornecedor atualizado: {name} (Código: {code}, Prazo: {prazo_dias} dias)")
                return True

        except sqlite3.IntegrityError as e:
            if "name" in str(e):
                logger.error(f"Nome '{name}' já existe para outro fornecedor")
            elif "code" in str(e):
                logger.error(f"Código {code} já está em uso por outro fornecedor")
            else:
                logger.error(f"Erro de integridade: {e}")
            return False
        except Exception as e:
            logger.error(f"Erro ao atualizar fornecedor: {e}")
            return False

    def delete_supplier(self, supplier_id: int) -> bool:
        """Remove um fornecedor"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Buscar nome antes de deletar para log
                cursor.execute("SELECT name FROM suppliers WHERE id = ?", (supplier_id,))
                result = cursor.fetchone()

                if not result:
                    logger.warning(f"Fornecedor com ID {supplier_id} não encontrado")
                    return False

                supplier_name = result[0]

                cursor.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
                conn.commit()

                logger.info(f"Fornecedor removido: {supplier_name}")
                return True

        except Exception as e:
            logger.error(f"Erro ao remover fornecedor: {e}")
            return False

    def get_all_suppliers(self) -> List[Supplier]:
        """Retorna todos os fornecedores"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # ✅ INCLUIR PRAZO_DIAS NO SELECT
                cursor.execute("SELECT id, name, code, prazo_dias FROM suppliers ORDER BY name")
                rows = cursor.fetchall()

                return [
                    Supplier(
                        id=row[0],
                        name=row[1],
                        code=row[2],
                        prazo_dias=row[3] if row[3] is not None else 0  # ✅ GARANTIR DEFAULT
                    )
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"Erro ao buscar fornecedores: {e}")
            return []

    def get_supplier_by_id(self, supplier_id: int) -> Optional[Supplier]:
        """Busca fornecedor por ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # ✅ INCLUIR PRAZO_DIAS NO SELECT
                cursor.execute("SELECT id, name, code, prazo_dias FROM suppliers WHERE id = ?", (supplier_id,))
                row = cursor.fetchone()

                if row:
                    return Supplier(
                        id=row[0],
                        name=row[1],
                        code=row[2],
                        prazo_dias=row[3] if row[3] is not None else 0  # ✅ GARANTIR DEFAULT
                    )
                return None

        except Exception as e:
            logger.error(f"Erro ao buscar fornecedor por ID: {e}")
            return None

    def get_supplier_by_code(self, code: int) -> Optional[Supplier]:
        """Busca fornecedor por código"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # ✅ INCLUIR PRAZO_DIAS NO SELECT
                cursor.execute("SELECT id, name, code, prazo_dias FROM suppliers WHERE code = ?", (code,))
                row = cursor.fetchone()

                if row:
                    return Supplier(
                        id=row[0],
                        name=row[1],
                        code=row[2],
                        prazo_dias=row[3] if row[3] is not None else 0  # ✅ GARANTIR DEFAULT
                    )
                return None

        except Exception as e:
            logger.error(f"Erro ao buscar fornecedor por código: {e}")
            return None

    def search_supplier_by_name(self, search_name: str) -> Optional[Supplier]:
        """Busca fornecedor por nome (VERSÃO CORRIGIDA)"""
        try:
            # Normalizar nome de busca
            normalized_search = self._normalize_name(search_name)

            logger.info("🔍 === BUSCA DE FORNECEDOR ===")
            logger.info(f"  📝 Nome original: '{search_name}'")
            logger.info(f"  🔄 Nome normalizado: '{normalized_search}'")

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # ✅ QUERY CORRIGIDA - USAR APENAS COLUNAS QUE EXISTEM
                cursor.execute("SELECT id, name, code, prazo_dias FROM suppliers")
                suppliers = cursor.fetchall()

            logger.info(f"  📊 Total de fornecedores carregados: {len(suppliers)}")

            # ✅ BUSCA EXATA PRIMEIRO
            for supplier in suppliers:
                supplier_id, name, code, prazo_dias = supplier
                if self._normalize_name(name) == normalized_search:
                    logger.success(f"  ✅ BUSCA EXATA: '{name}' -> Código: {code}, Prazo: {prazo_dias}")
                    return Supplier(
                        id=supplier_id,
                        name=name,
                        code=code,
                        prazo_dias=prazo_dias if prazo_dias is not None else 0
                    )

            # ✅ BUSCA POR SIMILARIDADE
            best_match = None
            best_score = 0

            for supplier in suppliers:
                supplier_id, name, code, prazo_dias = supplier
                normalized_supplier = self._normalize_name(name)

                # Várias estratégias de matching
                scores = []

                # 1. Contém o termo
                if normalized_search in normalized_supplier or normalized_supplier in normalized_search:
                    scores.append(0.9)
                    logger.info(f"    🎯 CONTÉM: '{search_name}' ↔ '{name}' (score: 0.9)")

                # 2. Começa com o termo
                if normalized_supplier.startswith(normalized_search) or normalized_search.startswith(
                        normalized_supplier):
                    scores.append(0.85)
                    logger.info(f"    🚀 COMEÇA COM: '{search_name}' ↔ '{name}' (score: 0.85)")

                # 3. Similaridade de palavras
                score_words = self._calculate_similarity(normalized_search, normalized_supplier)
                if score_words > 0:
                    scores.append(score_words)
                    logger.info(f"    �� SIMILARIDADE: '{search_name}' ↔ '{name}' (score: {score_words:.2f})")

                # Pegar o melhor score
                if scores:
                    max_score = max(scores)
                    if max_score > best_score:
                        best_score = max_score
                        best_match = supplier

            # Threshold mais baixo para DMOV
            threshold = 0.6 if any(term in normalized_search for term in ['dmov', 'drossi', 'rossi']) else 0.8

            if best_match and best_score >= threshold:
                supplier_id, name, code, prazo_dias = best_match
                logger.success(f"  ✅ MELHOR MATCH: '{name}' (score: {best_score:.2f})")
                return Supplier(
                    id=supplier_id,
                    name=name,
                    code=code,
                    prazo_dias=prazo_dias if prazo_dias is not None else 0
                )

            logger.warning(f"  ❌ Nenhum fornecedor encontrado para: '{search_name}'")

            # Debug: Mostrar fornecedores disponíveis
            logger.info("  📋 Primeiros 5 fornecedores disponíveis:")
            for i, supplier in enumerate(suppliers[:5]):
                supplier_id, name, code, prazo_dias = supplier
                logger.info(f"    {i + 1}. '{name}' (Código: {code}, Prazo: {prazo_dias} dias)")

            return None

        except Exception as e:
            logger.error(f"Erro na busca por fornecedor: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def _match_acronym(self, search: str, supplier_name: str) -> bool:
        """Verifica se search é sigla do supplier_name"""
        if len(search) < 2:
            return False

        # Extrair primeiras letras das palavras (ignorando artigos)
        words = supplier_name.split()
        if len(words) < 2:
            return False

        # Filtrar artigos e preposições comuns
        ignore_words = {'de', 'da', 'do', 'das', 'dos', 'e', 'a', 'o', 'as', 'os'}
        significant_words = [word for word in words if word.lower() not in ignore_words and len(word) > 1]

        if not significant_words:
            return False

        # Criar sigla das palavras significativas
        acronym = ''.join([word[0] for word in significant_words])

        # Verificar se a busca corresponde à sigla
        match = search.lower() == acronym.lower()

        if match:
            logger.info(f"    🎯 SIGLA DETECTADA: '{search}' = '{acronym}' de '{supplier_name}'")

        return match

    def _match_keywords(self, search: str, supplier_name: str) -> bool:
        """Verifica se há palavras-chave importantes em comum"""
        # Palavras-chave importantes para matching
        search_words = set(search.split())
        supplier_words = set(supplier_name.split())

        # Remover palavras muito comuns
        common_words = {'de', 'da', 'do', 'das', 'dos', 'e', 'a', 'o', 'as', 'os', 'ltda', 'sa', 'eireli'}
        search_words = {w for w in search_words if w not in common_words and len(w) > 2}
        supplier_words = {w for w in supplier_words if w not in common_words and len(w) > 2}

        if not search_words or not supplier_words:
            return False

        # Verificar se há interseção significativa
        intersection = search_words.intersection(supplier_words)

        # Se pelo menos 50% das palavras da busca estão no fornecedor
        match_ratio = len(intersection) / len(search_words)

        return match_ratio >= 0.5

    def _normalize_name(self, name: str) -> str:
        """Normaliza nome para comparação MELHORADA"""
        if not name:
            return ""

        # Converter para minúsculas e remover acentos
        normalized = name.lower().strip()

        # ✅ REMOVER ACENTOS MAIS COMPLETO
        accent_map = {
            'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a', 'ä': 'a',
            'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
            'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
            'ó': 'o', 'ò': 'o', 'õ': 'o', 'ô': 'o', 'ö': 'o',
            'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
            'ç': 'c', 'ñ': 'n'
        }

        for accented, normal in accent_map.items():
            normalized = normalized.replace(accented, normal)

        # ✅ REMOVER CARACTERES ESPECIAIS MAS MANTER ESPAÇOS
        normalized = re.sub(r"[^\w\s]", "", normalized)

        # ✅ NORMALIZAR ESPAÇOS
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized


    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calcula similaridade entre duas strings"""
        if not str1 or not str2:
            return 0.0

        # Algoritmo simples de similaridade baseado em caracteres comuns
        set1 = set(str1.split())
        set2 = set(str2.split())

        if not set1 or not set2:
            return 0.0

        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))

        return intersection / union if union > 0 else 0.0

    def export_to_json(self, file_path: Path) -> bool:
        """Exporta fornecedores para JSON"""
        try:
            suppliers = self.get_all_suppliers()

            # ✅ INCLUIR PRAZO_DIAS NA EXPORTAÇÃO
            suppliers_data = [
                {
                    "id": s.id,
                    "name": s.name,
                    "code": s.code,
                    "prazo_dias": s.prazo_dias
                }
                for s in suppliers
            ]

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(suppliers_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Fornecedores exportados para: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Erro ao exportar fornecedores: {e}")
            return False

    def import_from_json(self, file_path: Path) -> bool:
        """Importa fornecedores de JSON"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                suppliers_data = json.load(f)

            success_count = 0
            for supplier_data in suppliers_data:
                name = supplier_data.get("name", "")
                code = supplier_data.get("code", 0)
                prazo_dias = supplier_data.get("prazo_dias", 0)  # ✅ INCLUIR PRAZO_DIAS

                if name and code:
                    if self.add_supplier(name, code, prazo_dias):
                        success_count += 1

            logger.info(f"Importados {success_count} fornecedores de: {file_path}")
            return success_count > 0

        except Exception as e:
            logger.error(f"Erro ao importar fornecedores: {e}")
            return False

    def import_from_spreadsheet(self, file_path: Path, sheet_name: str = None) -> Tuple[int, int]:
        """Importa fornecedores de planilha Excel - RETORNA (sucessos, erros)"""
        try:
            import pandas as pd

            # ✅ DETECTAR NOME DA ABA AUTOMATICAMENTE SE NÃO ESPECIFICADO
            if sheet_name is None:
                # Tentar nomes comuns de abas
                possible_names = ["Fornecedores", "Fornecedor", "Suppliers", "Supplier", "FORNECEDORES", "FORNECEDOR"] # noqa: F841

                # Ler todas as abas disponíveis
                try:
                    excel_file = pd.ExcelFile(file_path)
                    available_sheets = excel_file.sheet_names
                    logger.info(f"📋 Abas disponíveis: {available_sheets}")

                    # Procurar por nome que contenha "fornec" ou usar a primeira aba
                    sheet_name = None
                    for sheet in available_sheets:
                        if any(name.lower() in sheet.lower() for name in ["fornec", "supplier"]):
                            sheet_name = sheet
                            logger.info(f"✅ Aba encontrada: '{sheet_name}'")
                            break

                    # Se não encontrou, usar a primeira aba
                    if sheet_name is None and available_sheets:
                        sheet_name = available_sheets[0]
                        logger.warning(f"⚠️ Usando primeira aba disponível: '{sheet_name}'")

                    if sheet_name is None:
                        logger.error("❌ Nenhuma aba encontrada no arquivo")
                        return 0, 1

                except Exception as e:
                    logger.error(f"❌ Erro ao ler abas do arquivo: {e}")
                    return 0, 1

            # Ler planilha
            logger.info(f"📖 Lendo aba: '{sheet_name}'")
            df = pd.read_excel(file_path, sheet_name=sheet_name)

            # ✅ MOSTRAR COLUNAS DISPONÍVEIS
            logger.info(f"📊 Colunas disponíveis: {list(df.columns)}")

            # ✅ MAPEAR COLUNAS AUTOMATICAMENTE (VERSÃO MELHORADA)
            # ✅ MAPEAR COLUNAS AUTOMATICAMENTE (VERSÃO CORRIGIDA)
            column_mapping = {}

            logger.info("🔍 Iniciando mapeamento de colunas...")

            # ✅ MAPEAMENTO DIRETO PARA CASOS ESPECÍFICOS
            direct_mappings = {
                "FORNECEDOR": "nome",
                "Fornecedor": "nome",
                "fornecedor": "nome",
                "NOME": "nome",
                "Nome": "nome",
                "nome": "nome",

                "Cód": "codigo",
                "CÓD": "codigo",
                "COD": "codigo",
                "Cod": "codigo",
                "CODIGO": "codigo",
                "Codigo": "codigo",
                "codigo": "codigo",
                "ID": "codigo",
                "Id": "codigo",
                "id": "codigo",

                "PRAZO": "prazo",
                "Prazo": "prazo",
                "prazo": "prazo",
                "DIAS": "prazo",
                "Dias": "prazo",
                "dias": "prazo"
            }

            # Aplicar mapeamento direto primeiro
            for col in df.columns:
                col_stripped = str(col).strip()
                if col_stripped in direct_mappings:
                    field_name = direct_mappings[col_stripped]
                    column_mapping[field_name] = col
                    logger.success(f"  ✅ Mapeamento DIRETO: '{col}' -> {field_name}")

            # Se ainda não encontrou nome, fazer busca flexível
            if "nome" not in column_mapping:
                for col in df.columns:
                    col_lower = str(col).lower().strip()
                    if any(term in col_lower for term in ["nome", "name", "fornecedor", "supplier"]):
                        column_mapping["nome"] = col
                        logger.success(f"  ✅ Coluna NOME encontrada (busca flexível): '{col}'")
                        break

            # Se ainda não encontrou código, fazer busca flexível
            if "codigo" not in column_mapping:
                for col in df.columns:
                    col_lower = str(col).lower().strip()
                    col_clean = col_lower.replace(".", "").replace("ó", "o").replace("á", "a")

                    if any(term in col_clean for term in ["codigo", "code", "cod", "id"]):
                        column_mapping["codigo"] = col
                        logger.success(
                            f"  ✅ Coluna CÓDIGO encontrada (busca flexível): '{col}' (normalizado: '{col_clean}')")
                        break

            # Se ainda não encontrou prazo, fazer busca flexível
            if "prazo" not in column_mapping:
                for col in df.columns:
                    col_lower = str(col).lower().strip()
                    if any(term in col_lower for term in ["prazo", "dias", "entrega", "delivery"]):
                        column_mapping["prazo"] = col
                        logger.success(f"  ✅ Coluna PRAZO encontrada (busca flexível): '{col}'")
                        break

            logger.info(f"🗺️ Mapeamento final: {column_mapping}")

            # ✅ DEBUG: Mostrar primeiras linhas
            logger.info("📋 Amostra dos dados:")
            for i, row in df.head(2).iterrows():
                logger.info(
                    f"  Linha {i + 2}: FORNECEDOR='{row.get('FORNECEDOR', 'N/A')}', Cód='{row.get('Cód', 'N/A')}', PRAZO='{row.get('PRAZO', 'N/A')}'")

            # Verificar se encontrou colunas essenciais
            if "nome" not in column_mapping or "codigo" not in column_mapping:
                logger.error("❌ Colunas obrigatórias não encontradas!")
                logger.error(f"   - Nome encontrado: {'nome' in column_mapping}")
                logger.error(f"   - Código encontrado: {'codigo' in column_mapping}")
                return 0, 1

            success_count = 0
            error_count = 0
            updated_count = 0  # ✅ NOVO CONTADOR

            for index, row in df.iterrows():
                try:
                    # Extrair dados usando mapeamento
                    name = str(row[column_mapping["nome"]]).strip()
                    code = int(row[column_mapping["codigo"]])

                    # Prazo é opcional
                    prazo_dias = 0
                    if "prazo" in column_mapping:
                        try:
                            prazo_value = row[column_mapping["prazo"]]
                            # ✅ TRATAR NaN
                            if pd.isna(prazo_value):
                                prazo_dias = 0
                            else:
                                prazo_dias = int(prazo_value)
                        except (ValueError, TypeError):
                            prazo_dias = 0

                    # Validar dados
                    if name and name.lower() not in ["nan", "none", ""]:
                        # ✅ VERIFICAR SE JÁ EXISTE PARA ATUALIZAR
                        existing_supplier = self.get_supplier_by_code(code)

                        if existing_supplier:
                            # ✅ ATUALIZAR FORNECEDOR EXISTENTE
                            if self.update_supplier(existing_supplier.id, name, code, prazo_dias):
                                updated_count += 1
                                logger.info(f"🔄 Atualizado: {name} (Código: {code}, Prazo: {prazo_dias} dias)")
                            else:
                                error_count += 1
                                logger.warning(f"⚠️ Erro ao atualizar: {name}")
                        else:
                            # ✅ ADICIONAR NOVO FORNECEDOR
                            if self.add_supplier(name, code, prazo_dias):
                                success_count += 1
                                logger.info(f"✅ Adicionado: {name} (Código: {code}, Prazo: {prazo_dias} dias)")
                            else:
                                error_count += 1
                                logger.warning(f"⚠️ Erro ao adicionar: {name}")
                    else:
                        error_count += 1
                        logger.warning(f"⚠️ Nome inválido na linha {index + 2}: '{name}'")

                except (ValueError, TypeError) as e:
                    error_count += 1
                    logger.warning(f"⚠️ Erro ao processar linha {index + 2}: {e}")
                    continue

            logger.info("📊 Importação concluída:")
            logger.info(f"  ✅ Novos: {success_count}")
            logger.info(f"  🔄 Atualizados: {updated_count}")
            logger.info(f"  ❌ Erros: {error_count}")

            return success_count + updated_count, error_count  # ✅ SOMAR NOVOS + ATUALIZADOS

        except Exception as e:
            logger.error(f"❌ Erro ao importar planilha: {e}")
            return 0, 1

    def get_statistics(self) -> Dict[str, int]:
        """Retorna estatísticas do banco, incluindo total de fornecedores,
        fornecedores com prazo, prazo médio e códigos únicos."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT COUNT(*) FROM suppliers")
                total_suppliers = cursor.fetchone()[0]

                # Estatísticas de prazo
                cursor.execute("SELECT COUNT(*) FROM suppliers WHERE prazo_dias > 0")
                suppliers_with_prazo = cursor.fetchone()[0]

                cursor.execute("SELECT AVG(prazo_dias) FROM suppliers WHERE prazo_dias > 0")
                avg_prazo = cursor.fetchone()[0] or 0

                # ✅ NOVO: Contar códigos únicos
                cursor.execute("SELECT COUNT(DISTINCT code) FROM suppliers")
                unique_codes = cursor.fetchone()[0]

                return {
                    "total_suppliers": total_suppliers,
                    "suppliers_with_prazo": suppliers_with_prazo,
                    "average_prazo_dias": round(avg_prazo, 1),
                    "unique_codes": unique_codes # ✅ ADICIONADO CAMPO
                }

        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {e}")
            return {
                "total_suppliers": 0,
                "suppliers_with_prazo": 0,
                "average_prazo_dias": 0,
                "unique_codes": 0 # ✅ ADICIONADO CAMPO
            }

    def debug_database_complete(self):
            """Debug completo do banco SQLite"""
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    logger.info("🔍 === DEBUG COMPLETO DO BANCO ===")
                    logger.info(f"📁 Arquivo: {self.db_path}")
                    logger.info(f"📏 Tamanho: {self.db_path.stat().st_size} bytes")

                    # ✅ LISTAR TODAS AS TABELAS
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    all_tables = cursor.fetchall()
                    logger.info(f"📋 Todas as tabelas: {[t[0] for t in all_tables]}")

                    # ✅ PARA CADA TABELA, MOSTRAR ESTRUTURA E DADOS
                    for table in all_tables:
                        table_name = table[0]
                        logger.info(f"\n🔍 === TABELA: {table_name} ===")

                        # Estrutura
                        cursor.execute(f"PRAGMA table_info({table_name})")
                        columns = cursor.fetchall()
                        logger.info(f"📊 Colunas: {[(c[1], c[2]) for c in columns]}")

                        # Contagem
                        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                        count = cursor.fetchone()[0]
                        logger.info(f"📈 Total de registros: {count}")

                        # Amostra de dados
                        if count > 0:
                            cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
                            sample_data = cursor.fetchall()
                            logger.info("📋 Amostra de dados:")
                            for i, row in enumerate(sample_data, 1):
                                logger.info(f"  {i}. {row}")

                            # ✅ BUSCAR ESPECIFICAMENTE POR DMOV
                            try:
                                cursor.execute(
                                    f"SELECT * FROM {table_name} WHERE name LIKE '%DMOV%' OR name LIKE '%dmov%'")
                                dmov_data = cursor.fetchall()
                                if dmov_data:
                                    logger.success(f"🎯 DMOV ENCONTRADO na tabela {table_name}:")
                                    for row in dmov_data:
                                        logger.success(f"    {row}")
                                else:
                                    logger.warning(f"❌ DMOV não encontrado na tabela {table_name}")
                            except Exception as e:
                                logger.error(f"Erro ao buscar DMOV na tabela {table_name}: {e}")

            except Exception as e:
                logger.error(f"Erro no debug completo: {e}")