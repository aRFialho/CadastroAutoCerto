"""Banco de dados para catálogo de produtos finais"""

import sqlite3
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class ProdutoCatalogo:
    """Representa um produto do catálogo - 13 colunas essenciais da imagem"""
    id: Optional[int] = None

    # ✅ AS 13 COLUNAS EXATAS DA IMAGEM
    cod_auxiliar: str = ""
    cod_barra: str = ""
    cod_fabric: str = ""
    marca: str = ""
    disponivel: str = ""
    preco: str = ""
    promocao: str = ""
    complemento: str = ""
    categoria: str = ""
    estoque_seg: str = ""
    custo_total: str = ""
    dias_p_entrega: str = ""
    site_disponibilidade: str = ""

    # Metadados do sistema
    status: str = "Ativo"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class ProductCatalogDatabase:
    """Gerenciador do banco de dados do catálogo de produtos"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()

    def init_database(self):
        """Inicializa o banco de dados com as tabelas"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # ✅ VERIFICAR SE TABELA EXISTE E QUAL ESTRUTURA TEM
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='produtos_catalogo'
                """)

                table_exists = cursor.fetchone() is not None

                if table_exists:
                    # ✅ VERIFICAR SE PRECISA MIGRAR
                    try:
                        cursor.execute("SELECT cod_auxiliar FROM produtos_catalogo LIMIT 1")
                        logger.info("Tabela já está na estrutura correta")
                    except sqlite3.OperationalError:
                        # ✅ TABELA EXISTE MAS TEM ESTRUTURA ANTIGA - MIGRAR
                        logger.info("Detectada estrutura antiga - iniciando migração...")
                        self.migrate_database(cursor)
                else:
                    # ✅ TABELA NÃO EXISTE - CRIAR NOVA
                    logger.info("Criando nova tabela de catálogo...")
                    self.create_new_table(cursor)

                conn.commit()
                logger.info(f"Banco de catálogo inicializado: {self.db_path}")

        except Exception as e:
            logger.error(f"Erro ao inicializar banco de catálogo: {e}")
            raise

    def migrate_database(self, cursor):
        """Migra banco da estrutura antiga para nova"""
        try:
            # ✅ FAZER BACKUP DOS DADOS EXISTENTES
            cursor.execute("SELECT * FROM produtos_catalogo")
            old_data = cursor.fetchall()

            # ✅ OBTER COLUNAS ANTIGAS
            cursor.execute("PRAGMA table_info(produtos_catalogo)")
            old_columns = [row[1] for row in cursor.fetchall()] # noqa: F841

            logger.info(f"Fazendo backup de {len(old_data)} registros...")

            # ✅ RENOMEAR TABELA ANTIGA
            cursor.execute("ALTER TABLE produtos_catalogo RENAME TO produtos_catalogo_backup")

            # ✅ CRIAR NOVA TABELA
            self.create_new_table(cursor)

            # ✅ MIGRAR DADOS (se houver)
            if old_data:
                logger.info("Migrando dados para nova estrutura...")
                # Por enquanto, apenas log - você pode implementar migração específica se necessário
                logger.warning("Dados antigos preservados na tabela 'produtos_catalogo_backup'")

            logger.info("Migração concluída com sucesso!")

        except Exception as e:
            logger.error(f"Erro na migração: {e}")
            raise

    def create_new_table(self, cursor):
        """Cria nova tabela com estrutura correta"""
        cursor.execute("""
            CREATE TABLE produtos_catalogo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                -- ✅ 13 COLUNAS EXATAS DA IMAGEM
                cod_auxiliar TEXT DEFAULT '',
                cod_barra TEXT DEFAULT '',
                cod_fabric TEXT DEFAULT '',
                marca TEXT DEFAULT '',
                disponivel TEXT DEFAULT '',
                preco TEXT DEFAULT '',
                promocao TEXT DEFAULT '',
                complemento TEXT DEFAULT '',
                categoria TEXT DEFAULT '',
                estoque_seg TEXT DEFAULT '',
                custo_total TEXT DEFAULT '',
                dias_p_entrega TEXT DEFAULT '',
                site_disponibilidade TEXT DEFAULT '',
                
                -- Metadados do sistema
                status TEXT DEFAULT 'Ativo',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ✅ ÍNDICES PARA CAMPOS IMPORTANTES
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cod_auxiliar ON produtos_catalogo(cod_auxiliar)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cod_barra ON produtos_catalogo(cod_barra)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cod_fabric ON produtos_catalogo(cod_fabric)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_marca ON produtos_catalogo(marca)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_categoria ON produtos_catalogo(categoria)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON produtos_catalogo(status)")

    def add_produto(self, produto: ProdutoCatalogo) -> int:
        """Adiciona um produto ao catálogo"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # ✅ LOG DETALHADO PARA DEBUG
                logger.debug(f"Adicionando produto: {produto.__dict__}")

                # Preparar dados para inserção
                fields = []
                values = []
                placeholders = []

                # Iterar sobre todos os campos do produto (exceto id, created_at, updated_at)
                for field_name, field_value in produto.__dict__.items():
                    if field_name not in ['id', 'created_at', 'updated_at'] and field_value is not None:
                        fields.append(field_name)
                        values.append(field_value)
                        placeholders.append('?')

                # ✅ LOG DOS CAMPOS QUE SERÃO INSERIDOS
                logger.debug(f"Campos a inserir: {fields}")
                logger.debug(f"Valores a inserir: {values}")

                # Construir query dinâmica
                fields_str = ', '.join(fields)
                placeholders_str = ', '.join(placeholders)

                query = f"INSERT INTO produtos_catalogo ({fields_str}) VALUES ({placeholders_str})"
                logger.debug(f"Query: {query}")

                cursor.execute(query, values)

                produto_id = cursor.lastrowid
                conn.commit()
                logger.info(
                    f"Produto adicionado ao catálogo: ID {produto_id} - {produto.marca} - {produto.cod_auxiliar}")
                return produto_id

        except Exception as e:
            logger.error(f"Erro ao adicionar produto ao catálogo: {e}")
            logger.error(f"Dados do produto: {produto.__dict__}")
            raise

    def get_produto_by_id(self, produto_id: int) -> Optional[ProdutoCatalogo]:
        """Busca produto por ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM produtos_catalogo WHERE id = ?", (produto_id,))
                row = cursor.fetchone()

                if row:
                    return self._row_to_produto(cursor, row)
                return None

        except Exception as e:
            logger.error(f"Erro ao buscar produto por ID: {e}")
            return None

    def get_produto_by_cod_auxiliar(self, cod_auxiliar: str) -> Optional[ProdutoCatalogo]:
        """Busca produto por código auxiliar"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM produtos_catalogo WHERE cod_auxiliar = ?", (cod_auxiliar,))
                row = cursor.fetchone()

                if row:
                    return self._row_to_produto(cursor, row)
                return None

        except Exception as e:
            logger.error(f"Erro ao buscar produto por código auxiliar: {e}")
            return None

    def get_produto_by_cod_barra(self, cod_barra: str) -> Optional[ProdutoCatalogo]:
        """Busca produto por código de barras"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM produtos_catalogo WHERE cod_barra = ?", (cod_barra,))
                row = cursor.fetchone()

                if row:
                    return self._row_to_produto(cursor, row)
                return None

        except Exception as e:
            logger.error(f"Erro ao buscar produto por código de barras: {e}")
            return None

    def list_produtos(self, limit: int = None, offset: int = 0, search: str = None) -> List[ProdutoCatalogo]:
        """Lista produtos do catálogo"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Construir query com filtros
                query = "SELECT * FROM produtos_catalogo WHERE 1=1"
                params = []

                if search:
                    search_term = f"%{search}%"
                    query += """ AND (
                        cod_auxiliar LIKE ? OR 
                        cod_barra LIKE ? OR 
                        cod_fabric LIKE ? OR
                        marca LIKE ? OR
                        categoria LIKE ?
                    )"""
                    params.extend([search_term, search_term, search_term, search_term, search_term])

                query += " ORDER BY marca, cod_auxiliar"

                if limit:
                    query += " LIMIT ? OFFSET ?"
                    params.extend([limit, offset])

                cursor.execute(query, params)
                rows = cursor.fetchall()

                produtos = []
                for row in rows:
                    produtos.append(self._row_to_produto(cursor, row))

                return produtos

        except Exception as e:
            logger.error(f"Erro ao listar produtos: {e}")
            return []

    def update_produto(self, produto: ProdutoCatalogo) -> bool:
        """Atualiza um produto"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Preparar dados para atualização
                fields = []
                values = []

                # Iterar sobre todos os campos (exceto id, created_at)
                for field_name, field_value in produto.__dict__.items():
                    if field_name not in ['id', 'created_at']:
                        if field_name == 'updated_at':
                            fields.append(f"{field_name} = CURRENT_TIMESTAMP")
                        else:
                            fields.append(f"{field_name} = ?")
                            values.append(field_value)

                # Adicionar ID para WHERE
                values.append(produto.id)

                # Construir query
                fields_str = ', '.join(fields)
                query = f"UPDATE produtos_catalogo SET {fields_str} WHERE id = ?"

                cursor.execute(query, values)

                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"Produto {produto.id} atualizado")
                    return True
                return False

        except Exception as e:
            logger.error(f"Erro ao atualizar produto: {e}")
            raise

    def delete_produto(self, produto_id: int) -> bool:
        """Exclui um produto"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Buscar nome do produto para log
                cursor.execute("SELECT marca, cod_auxiliar FROM produtos_catalogo WHERE id = ?", (produto_id,))
                produto_info = cursor.fetchone()

                if not produto_info:
                    return False

                # Excluir produto
                cursor.execute("DELETE FROM produtos_catalogo WHERE id = ?", (produto_id,))

                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"Produto excluído: {produto_info[0]} - {produto_info[1]} (ID: {produto_id})")
                    return True
                return False

        except Exception as e:
            logger.error(f"Erro ao excluir produto: {e}")
            raise

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do catálogo"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Total de produtos
                cursor.execute("SELECT COUNT(*) FROM produtos_catalogo WHERE status = 'Ativo'")
                total_produtos = cursor.fetchone()[0]

                # Total por marca
                cursor.execute("""
                    SELECT marca, COUNT(*) 
                    FROM produtos_catalogo 
                    WHERE status = 'Ativo' 
                    GROUP BY marca
                """)
                por_marca = dict(cursor.fetchall())

                # Total por categoria
                cursor.execute("""
                    SELECT categoria, COUNT(*) 
                    FROM produtos_catalogo 
                    WHERE status = 'Ativo' 
                    GROUP BY categoria
                """)
                por_categoria = dict(cursor.fetchall())

                # Produtos com código de barras
                cursor.execute("SELECT COUNT(*) FROM produtos_catalogo WHERE cod_barra != '' AND status = 'Ativo'")
                com_cod_barra = cursor.fetchone()[0]

                return {
                    "total_produtos": total_produtos,
                    "por_marca": por_marca,
                    "por_categoria": por_categoria,
                    "com_cod_barra": com_cod_barra,
                    "sem_cod_barra": total_produtos - com_cod_barra
                }

        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {e}")
            return {}

    def search_produtos(self, **filters) -> List[ProdutoCatalogo]:
        """Busca produtos com filtros específicos"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Construir query dinâmica
                conditions = []
                params = []

                for field, value in filters.items():
                    if value:
                        if field in ['marca', 'categoria', 'complemento']:
                            conditions.append(f"{field} LIKE ?")
                            params.append(f"%{value}%")
                        else:
                            conditions.append(f"{field} = ?")
                            params.append(value)

                query = "SELECT * FROM produtos_catalogo"
                if conditions:
                    query += " WHERE " + " AND ".join(conditions)
                query += " ORDER BY marca, cod_auxiliar"

                cursor.execute(query, params)
                rows = cursor.fetchall()

                produtos = []
                for row in rows:
                    produtos.append(self._row_to_produto(cursor, row))

                return produtos

        except Exception as e:
            logger.error(f"Erro na busca de produtos: {e}")
            return []

    def clear_all_data(self):
        """Limpa todos os dados do catálogo"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM produtos_catalogo")
                conn.commit()
                logger.info("Todos os dados do catálogo foram limpos")
        except Exception as e:
            logger.error(f"Erro ao limpar dados do catálogo: {e}")
            raise

    def _row_to_produto(self, cursor, row) -> ProdutoCatalogo:
        """Converte linha do banco para objeto ProdutoCatalogo"""
        try:
            # Obter nomes das colunas
            column_names = [description[0] for description in cursor.description]

            # Criar dicionário com os dados
            data = dict(zip(column_names, row))

            # Converter timestamps
            if data.get('created_at'):
                try:
                    data['created_at'] = datetime.fromisoformat(data['created_at'])
                except Exception:
                    data['created_at'] = None

            if data.get('updated_at'):
                try:
                    data['updated_at'] = datetime.fromisoformat(data['updated_at'])
                except Exception:
                    data['updated_at'] = None

            # Criar objeto ProdutoCatalogo
            return ProdutoCatalogo(**data)

        except Exception as e:
            logger.error(f"Erro ao converter linha para produto: {e}")
            raise

    def export_to_dict(self, produto_id: int) -> Dict[str, Any]:
        """Exporta produto para dicionário (útil para APIs/JSON)"""
        produto = self.get_produto_by_id(produto_id)
        if produto:
            data = produto.__dict__.copy()

            # Converter datetime para string
            if data.get('created_at'):
                data['created_at'] = data['created_at'].isoformat()
            if data.get('updated_at'):
                data['updated_at'] = data['updated_at'].isoformat()

            return data
        return {}

    def import_from_dict(self, data: Dict[str, Any]) -> int:
        """Importa produto de dicionário"""
        try:
            # Remover campos que não devem ser importados
            clean_data = data.copy()
            clean_data.pop('id', None)
            clean_data.pop('created_at', None)
            clean_data.pop('updated_at', None)

            # Criar objeto produto
            produto = ProdutoCatalogo(**clean_data)

            # Adicionar ao banco
            return self.add_produto(produto)

        except Exception as e:
            logger.error(f"Erro ao importar produto de dicionário: {e}")
            raise