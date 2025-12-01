"""Banco de dados para custos de produtos por fornecedor"""

import sqlite3
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import json

logger = logging.getLogger(__name__)


@dataclass
class CustoProduto:
    """Representa um custo de produto"""
    id: Optional[int] = None

    # Identificação do produto
    codigo_produto: str = ""
    nome_produto: str = ""
    ean: str = ""
    referencia: str = ""

    # Informações do fornecedor
    fornecedor: str = ""
    codigo_fornecedor: str = ""

    # Custos
    custo_unitario: float = 0.0
    custo_com_ipi: float = 0.0
    custo_com_frete: float = 0.0
    custo_total: float = 0.0

    # Percentuais
    percentual_ipi: float = 0.0
    percentual_frete: float = 0.0
    percentual_markup: float = 0.0

    # Preços sugeridos
    preco_venda_sugerido: float = 0.0
    preco_promocional: float = 0.0

    # Informações adicionais
    unidade: str = "UN"
    categoria: str = ""
    subcategoria: str = ""
    observacoes: str = ""

    # Controle de estoque
    estoque_minimo: int = 0
    estoque_atual: int = 0

    # Metadados
    data_importacao: Optional[datetime] = None
    arquivo_origem: str = ""
    linha_origem: int = 0
    ativo: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class FornecedorCustos:
    """Representa um fornecedor no sistema de custos"""
    id: Optional[int] = None
    nome: str = ""
    codigo: str = ""
    cnpj: str = ""
    contato: str = ""
    email: str = ""
    telefone: str = ""
    endereco: str = ""

    # Configurações de importação
    estrutura_planilha: str = ""  # JSON com configurações
    linha_cabecalho: int = 1
    colunas_mapeamento: str = ""  # JSON com mapeamento de colunas

    # Estatísticas
    total_produtos: int = 0
    ultima_importacao: Optional[datetime] = None

    # Metadados
    ativo: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CostsDatabase:
    """Gerenciador do banco de dados de custos"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()

    def init_database(self):
        """Inicializa o banco de dados"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Tabela de fornecedores
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS fornecedores_custos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT NOT NULL,
                        codigo TEXT UNIQUE,
                        cnpj TEXT,
                        contato TEXT,
                        email TEXT,
                        telefone TEXT,
                        endereco TEXT,
                        estrutura_planilha TEXT DEFAULT '{}',
                        linha_cabecalho INTEGER DEFAULT 1,
                        colunas_mapeamento TEXT DEFAULT '{}',
                        total_produtos INTEGER DEFAULT 0,
                        ultima_importacao TIMESTAMP,
                        ativo BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Tabela de custos de produtos
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS custos_produtos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        codigo_produto TEXT,
                        nome_produto TEXT,
                        ean TEXT,
                        referencia TEXT,
                        fornecedor TEXT NOT NULL,
                        codigo_fornecedor TEXT,
                        custo_unitario REAL DEFAULT 0.0,
                        custo_com_ipi REAL DEFAULT 0.0,
                        custo_com_frete REAL DEFAULT 0.0,
                        custo_total REAL DEFAULT 0.0,
                        percentual_ipi REAL DEFAULT 0.0,
                        percentual_frete REAL DEFAULT 0.0,
                        percentual_markup REAL DEFAULT 0.0,
                        preco_venda_sugerido REAL DEFAULT 0.0,
                        preco_promocional REAL DEFAULT 0.0,
                        unidade TEXT DEFAULT 'UN',
                        categoria TEXT,
                        subcategoria TEXT,
                        observacoes TEXT,
                        estoque_minimo INTEGER DEFAULT 0,
                        estoque_atual INTEGER DEFAULT 0,
                        data_importacao TIMESTAMP,
                        arquivo_origem TEXT,
                        linha_origem INTEGER DEFAULT 0,
                        ativo BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Índices para performance
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_custos_codigo ON custos_produtos(codigo_produto)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_custos_ean ON custos_produtos(ean)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_custos_fornecedor ON custos_produtos(fornecedor)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_custos_ativo ON custos_produtos(ativo)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_fornecedores_codigo ON fornecedores_custos(codigo)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_fornecedores_ativo ON fornecedores_custos(ativo)")

                conn.commit()
                logger.info(f"Banco de custos inicializado: {self.db_path}")

        except Exception as e:
            logger.error(f"Erro ao inicializar banco de custos: {e}")
            raise

    # ========== MÉTODOS PARA FORNECEDORES ==========

    def add_fornecedor(self, fornecedor: FornecedorCustos) -> int:
        """Adiciona um fornecedor"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO fornecedores_custos 
                    (nome, codigo, cnpj, contato, email, telefone, endereco, 
                     estrutura_planilha, linha_cabecalho, colunas_mapeamento)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    fornecedor.nome, fornecedor.codigo, fornecedor.cnpj,
                    fornecedor.contato, fornecedor.email, fornecedor.telefone,
                    fornecedor.endereco, fornecedor.estrutura_planilha,
                    fornecedor.linha_cabecalho, fornecedor.colunas_mapeamento
                ))

                fornecedor_id = cursor.lastrowid
                conn.commit()
                logger.info(f"Fornecedor adicionado: {fornecedor.nome} (ID: {fornecedor_id})")
                return fornecedor_id

        except Exception as e:
            logger.error(f"Erro ao adicionar fornecedor: {e}")
            raise

    def get_fornecedor_by_id(self, fornecedor_id: int) -> Optional[FornecedorCustos]:
        """Busca fornecedor por ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM fornecedores_custos WHERE id = ?", (fornecedor_id,))
                row = cursor.fetchone()

                if row:
                    return self._row_to_fornecedor(cursor, row)
                return None

        except Exception as e:
            logger.error(f"Erro ao buscar fornecedor: {e}")
            return None

    def get_fornecedor_by_nome(self, nome: str) -> Optional[FornecedorCustos]:
        """Busca fornecedor por nome"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM fornecedores_custos WHERE nome LIKE ? AND ativo = 1", (f"%{nome}%",))
                row = cursor.fetchone()

                if row:
                    return self._row_to_fornecedor(cursor, row)
                return None

        except Exception as e:
            logger.error(f"Erro ao buscar fornecedor por nome: {e}")
            return None

    def list_fornecedores(self, ativo_apenas: bool = True) -> List[FornecedorCustos]:
        """Lista todos os fornecedores"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                query = "SELECT * FROM fornecedores_custos"
                if ativo_apenas:
                    query += " WHERE ativo = 1"
                query += " ORDER BY nome"

                cursor.execute(query)
                rows = cursor.fetchall()

                fornecedores = []
                for row in rows:
                    fornecedores.append(self._row_to_fornecedor(cursor, row))

                return fornecedores

        except Exception as e:
            logger.error(f"Erro ao listar fornecedores: {e}")
            return []

    def update_fornecedor(self, fornecedor: FornecedorCustos) -> bool:
        """Atualiza um fornecedor"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE fornecedores_custos 
                    SET nome = ?, codigo = ?, cnpj = ?, contato = ?, email = ?, 
                        telefone = ?, endereco = ?, estrutura_planilha = ?, 
                        linha_cabecalho = ?, colunas_mapeamento = ?, 
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    fornecedor.nome, fornecedor.codigo, fornecedor.cnpj,
                    fornecedor.contato, fornecedor.email, fornecedor.telefone,
                    fornecedor.endereco, fornecedor.estrutura_planilha,
                    fornecedor.linha_cabecalho, fornecedor.colunas_mapeamento,
                    fornecedor.id
                ))

                success = cursor.rowcount > 0
                conn.commit()

                if success:
                    logger.info(f"Fornecedor atualizado: {fornecedor.nome}")

                return success

        except Exception as e:
            logger.error(f"Erro ao atualizar fornecedor: {e}")
            raise

    # ========== MÉTODOS PARA CUSTOS ==========

    def add_custo_produto(self, custo: CustoProduto) -> int:
        """Adiciona um custo de produto"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Preparar dados para inserção
                fields = []
                values = []
                placeholders = []

                for field_name, field_value in custo.__dict__.items():
                    if field_name not in ['id', 'created_at', 'updated_at'] and field_value is not None:
                        fields.append(field_name)
                        values.append(field_value)
                        placeholders.append('?')

                fields_str = ', '.join(fields)
                placeholders_str = ', '.join(placeholders)

                query = f"INSERT INTO custos_produtos ({fields_str}) VALUES ({placeholders_str})"
                cursor.execute(query, values)

                custo_id = cursor.lastrowid
                conn.commit()
                logger.debug(f"Custo adicionado: {custo.nome_produto} - {custo.fornecedor}")
                return custo_id

        except Exception as e:
            logger.error(f"Erro ao adicionar custo: {e}")
            raise

    def get_custos_by_fornecedor(self, fornecedor: str, ativo_apenas: bool = True) -> List[CustoProduto]:
        """Busca custos por fornecedor"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                query = "SELECT * FROM custos_produtos WHERE fornecedor = ?"
                params = [fornecedor]

                if ativo_apenas:
                    query += " AND ativo = 1"

                query += " ORDER BY nome_produto"

                cursor.execute(query, params)
                rows = cursor.fetchall()

                custos = []
                for row in rows:
                    custos.append(self._row_to_custo(cursor, row))

                return custos

        except Exception as e:
            logger.error(f"Erro ao buscar custos por fornecedor: {e}")
            return []

    def get_custo_by_codigo(self, codigo_produto: str, fornecedor: str = None) -> Optional[CustoProduto]:
        """Busca custo por código do produto"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                query = "SELECT * FROM custos_produtos WHERE codigo_produto = ? AND ativo = 1"
                params = [codigo_produto]

                if fornecedor:
                    query += " AND fornecedor = ?"
                    params.append(fornecedor)

                query += " ORDER BY data_importacao DESC LIMIT 1"

                cursor.execute(query, params)
                row = cursor.fetchone()

                if row:
                    return self._row_to_custo(cursor, row)
                return None

        except Exception as e:
            logger.error(f"Erro ao buscar custo por código: {e}")
            return None

    def search_custos(self, **filters) -> List[CustoProduto]:
        """Busca custos com filtros"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                conditions = ["ativo = 1"]
                params = []

                for field, value in filters.items():
                    if value:
                        if field in ['nome_produto', 'categoria', 'observacoes']:
                            conditions.append(f"{field} LIKE ?")
                            params.append(f"%{value}%")
                        else:
                            conditions.append(f"{field} = ?")
                            params.append(value)

                query = "SELECT * FROM custos_produtos WHERE " + " AND ".join(conditions)
                query += " ORDER BY fornecedor, nome_produto"

                cursor.execute(query, params)
                rows = cursor.fetchall()

                custos = []
                for row in rows:
                    custos.append(self._row_to_custo(cursor, row))

                return custos

        except Exception as e:
            logger.error(f"Erro na busca de custos: {e}")
            return []

    def update_custo_produto(self, custo: CustoProduto) -> bool:
        """Atualiza um custo de produto"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Preparar dados para atualização
                fields = []
                values = []

                for field_name, field_value in custo.__dict__.items():
                    if field_name not in ['id', 'created_at']:
                        if field_name == 'updated_at':
                            fields.append(f"{field_name} = CURRENT_TIMESTAMP")
                        else:
                            fields.append(f"{field_name} = ?")
                            values.append(field_value)

                values.append(custo.id)

                fields_str = ', '.join(fields)
                query = f"UPDATE custos_produtos SET {fields_str} WHERE id = ?"

                cursor.execute(query, values)

                success = cursor.rowcount > 0
                conn.commit()

                if success:
                    logger.debug(f"Custo atualizado: {custo.nome_produto}")

                return success

        except Exception as e:
            logger.error(f"Erro ao atualizar custo: {e}")
            raise

    def delete_custos_fornecedor(self, fornecedor: str) -> int:
        """Remove todos os custos de um fornecedor"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("DELETE FROM custos_produtos WHERE fornecedor = ?", (fornecedor,))
                deleted_count = cursor.rowcount
                conn.commit()

                logger.info(f"Removidos {deleted_count} custos do fornecedor: {fornecedor}")
                return deleted_count

        except Exception as e:
            logger.error(f"Erro ao remover custos do fornecedor: {e}")
            raise

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do banco"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Total de fornecedores
                cursor.execute("SELECT COUNT(*) FROM fornecedores_custos WHERE ativo = 1")
                total_fornecedores = cursor.fetchone()[0]

                # Total de produtos
                cursor.execute("SELECT COUNT(*) FROM custos_produtos WHERE ativo = 1")
                total_produtos = cursor.fetchone()[0]

                # Produtos por fornecedor
                cursor.execute("""
                    SELECT fornecedor, COUNT(*) 
                    FROM custos_produtos 
                    WHERE ativo = 1 
                    GROUP BY fornecedor
                """)
                por_fornecedor = dict(cursor.fetchall())

                # Última importação
                cursor.execute("SELECT MAX(data_importacao) FROM custos_produtos")
                ultima_importacao = cursor.fetchone()[0]

                return {
                    "total_fornecedores": total_fornecedores,
                    "total_produtos": total_produtos,
                    "por_fornecedor": por_fornecedor,
                    "ultima_importacao": ultima_importacao
                }

        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {e}")
            return {}

    # ========== MÉTODOS AUXILIARES ==========

    def _row_to_fornecedor(self, cursor, row) -> FornecedorCustos:
        """Converte linha do banco para objeto FornecedorCustos"""
        try:
            column_names = [description[0] for description in cursor.description]
            data = dict(zip(column_names, row))

            # Converter timestamps
            for field in ['ultima_importacao', 'created_at', 'updated_at']:
                if data.get(field):
                    try:
                        data[field] = datetime.fromisoformat(data[field])
                    except:
                        data[field] = None

            return FornecedorCustos(**data)

        except Exception as e:
            logger.error(f"Erro ao converter linha para fornecedor: {e}")
            raise

    def _row_to_custo(self, cursor, row) -> CustoProduto:
        """Converte linha do banco para objeto CustoProduto"""
        try:
            column_names = [description[0] for description in cursor.description]
            data = dict(zip(column_names, row))

            # Converter timestamps
            for field in ['data_importacao', 'created_at', 'updated_at']:
                if data.get(field):
                    try:
                        data[field] = datetime.fromisoformat(data[field])
                    except:
                        data[field] = None

            return CustoProduto(**data)

        except Exception as e:
            logger.error(f"Erro ao converter linha para custo: {e}")
            raise