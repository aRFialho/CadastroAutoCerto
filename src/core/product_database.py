"""Banco de dados para produtos e componentes"""

import sqlite3
import logging
import json
from pathlib import Path
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Produto:
    """Representa um produto principal (aba da planilha)"""
    id: Optional[int] = None
    nome_aba: str = ""
    status: str = "Ativo"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Assento:
    """Representa um assento/modelo"""
    id: Optional[int] = None
    produto_id: int = 0
    nome: str = ""
    modelo: str = ""
    revestimento: str = ""
    ean: str = ""
    codigo: str = ""
    quantidade: int = 1  # ✅ NOVO CAMPO
    status: str = "Ativo"


@dataclass
class PeBase:
    """Representa um pé ou base"""
    id: Optional[int] = None
    produto_id: int = 0
    nome: str = ""
    ean: str = ""
    codigo: str = ""
    quantidade: int = 1
    tipo_contexto: str = ""  # ✅ NOVO: "Poltrona", "Namoradeira", "Puff"
    grupo_pes: str = ""      # ✅ NOVO: "DMOV", "DMOV2", "D'ROSSI"
    marca: str = ""          # ✅ NOVO: Para diferentes marcas
    status: str = "Ativo"

@dataclass
class ComponenteEspecial:
    """Para componentes especiais como almofadas, fórmulas, etc."""
    id: Optional[int] = None
    produto_id: int = 0
    tipo_componente: str = ""  # "almofada", "formula", "estrutura", etc.
    nome: str = ""
    ean: str = ""
    codigo: str = ""
    quantidade: int = 1
    dados_extras: str = ""     # JSON com dados específicos
    status: str = "Ativo"

@dataclass
class Combinacao:
    """Representa uma combinação assento + pé/base"""
    id: Optional[int] = None
    assento_id: int = 0
    pe_base_id: int = 0
    produto_id: int = 0
    status: str = "Ativo"

@dataclass
class LojaWebData:
    """Dados específicos para loja web"""
    id: Optional[int] = None
    produto_id: int = 0
    categoria_principal: str = ""
    nivel_adicional_1: str = ""
    nivel_adicional_2: str = ""
    titulo_produto: str = ""
    descricao_curta: str = ""
    descricao_longa: str = ""
    palavras_chave: str = ""
    status: str = "Ativo"


class ProductDatabase:
    """Gerenciador do banco de dados de produtos"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()

    def init_database(self):
        """Inicializa o banco de dados com as tabelas"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # ✅ SUAS TABELAS EXISTENTES (mantidas como estão)
                # Tabela de produtos principais
                cursor.execute("""
                              CREATE TABLE IF NOT EXISTS loja_web (
                                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                                  produto_id INTEGER NOT NULL,
                                  categoria_principal TEXT DEFAULT '',
                                  nivel_adicional_1 TEXT DEFAULT '',
                                  nivel_adicional_2 TEXT DEFAULT '',
                                  titulo_produto TEXT DEFAULT '',
                                  descricao_curta TEXT DEFAULT '',
                                  descricao_longa TEXT DEFAULT '',
                                  palavras_chave TEXT DEFAULT '',
                                  status TEXT DEFAULT 'Ativo',
                                  FOREIGN KEY (produto_id) REFERENCES produtos (id) ON DELETE CASCADE
                              )
                          """)

                # Tabela de assentos
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS assentos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        produto_id INTEGER NOT NULL,
                        nome TEXT NOT NULL,
                        modelo TEXT NOT NULL,
                        revestimento TEXT NOT NULL,
                        ean TEXT,
                        codigo TEXT,
                        status TEXT DEFAULT 'Ativo',
                        FOREIGN KEY (produto_id) REFERENCES produtos (id) ON DELETE CASCADE
                    )
                """)

                # Tabela de pés/bases
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pes_bases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        produto_id INTEGER NOT NULL,
                        nome TEXT NOT NULL,
                        ean TEXT,
                        codigo TEXT,
                        quantidade INTEGER DEFAULT 1,
                        status TEXT DEFAULT 'Ativo',
                        FOREIGN KEY (produto_id) REFERENCES produtos (id) ON DELETE CASCADE
                    )
                """)

                # Tabela de combinações
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS combinacoes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        assento_id INTEGER NOT NULL,
                        pe_base_id INTEGER NOT NULL,
                        produto_id INTEGER NOT NULL,
                        status TEXT DEFAULT 'Ativo',
                        FOREIGN KEY (assento_id) REFERENCES assentos (id) ON DELETE CASCADE,
                        FOREIGN KEY (pe_base_id) REFERENCES pes_bases (id) ON DELETE CASCADE,
                        FOREIGN KEY (produto_id) REFERENCES produtos (id) ON DELETE CASCADE,
                        UNIQUE(assento_id, pe_base_id)
                    )
                """)

                # ✅ NOVA TABELA PARA COMPONENTES ESPECIAIS
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS componentes_especiais (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        produto_id INTEGER NOT NULL,
                        tipo_componente TEXT NOT NULL,
                        nome TEXT NOT NULL,
                        ean TEXT,
                        codigo TEXT,
                        quantidade INTEGER DEFAULT 1,
                        dados_extras TEXT DEFAULT '{}',
                        status TEXT DEFAULT 'Ativo',
                        FOREIGN KEY (produto_id) REFERENCES produtos (id) ON DELETE CASCADE
                    )
                """)

                # ✅ ATUALIZAR TABELAS EXISTENTES COM NOVAS COLUNAS
                self._update_existing_tables(cursor)

                # Índices para performance (seus existentes + novos)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_assentos_produto ON assentos(produto_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_pes_produto ON pes_bases(produto_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_combinacoes_produto ON combinacoes(produto_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_assentos_ean ON assentos(ean)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_pes_ean ON pes_bases(ean)")
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_componentes_produto ON componentes_especiais(produto_id)")  # ✅ NOVO

                conn.commit()
                logger.info(f"Banco de produtos inicializado: {self.db_path}")

        except Exception as e:
            logger.error(f"Erro ao inicializar banco de produtos: {e}")
            raise

    def _update_existing_tables(self, cursor):
        """Atualiza tabelas existentes com novas colunas sem quebrar dados existentes"""
        try:
            # ✅ VERIFICAR E ADICIONAR COLUNAS NA TABELA ASSENTOS
            cursor.execute("PRAGMA table_info(assentos)")
            assento_columns = [col[1] for col in cursor.fetchall()]

            if 'quantidade' not in assento_columns:
                cursor.execute("ALTER TABLE assentos ADD COLUMN quantidade INTEGER DEFAULT 1")
                logger.info("✅ Coluna 'quantidade' adicionada à tabela assentos")

            # ✅ VERIFICAR E ADICIONAR COLUNAS NA TABELA PES_BASES
            cursor.execute("PRAGMA table_info(pes_bases)")
            pes_columns = [col[1] for col in cursor.fetchall()]

            if 'tipo_contexto' not in pes_columns:
                cursor.execute("ALTER TABLE pes_bases ADD COLUMN tipo_contexto TEXT DEFAULT ''")
                logger.info("✅ Coluna 'tipo_contexto' adicionada à tabela pes_bases")

            if 'grupo_pes' not in pes_columns:
                cursor.execute("ALTER TABLE pes_bases ADD COLUMN grupo_pes TEXT DEFAULT ''")
                logger.info("✅ Coluna 'grupo_pes' adicionada à tabela pes_bases")

            if 'marca' not in pes_columns:
                cursor.execute("ALTER TABLE pes_bases ADD COLUMN marca TEXT DEFAULT ''")
                logger.info("✅ Coluna 'marca' adicionada à tabela pes_bases")

        except Exception as e:
            logger.error(f"Erro ao atualizar tabelas existentes: {e}")

    # MÉTODOS PARA PRODUTOS
    def add_produto(self, nome_aba: str) -> int:
        """Adiciona um produto principal"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO produtos (nome_aba) VALUES (?)",
                    (nome_aba,)
                )
                produto_id = cursor.lastrowid
                conn.commit()
                logger.info(f"Produto adicionado: {nome_aba} (ID: {produto_id})")
                return produto_id
        except sqlite3.IntegrityError:
            logger.warning(f"Produto já existe: {nome_aba}")
            return self.get_produto_by_name(nome_aba).id
        except Exception as e:
            logger.error(f"Erro ao adicionar produto: {e}")
            raise

    def get_produto_by_name(self, nome_aba: str) -> Optional[Produto]:
        """Busca produto por nome da aba"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, nome_aba, status, created_at, updated_at FROM produtos WHERE nome_aba = ?",
                    (nome_aba,)
                )
                row = cursor.fetchone()
                if row:
                    return Produto(
                        id=row[0],
                        nome_aba=row[1],
                        status=row[2],
                        created_at=datetime.fromisoformat(row[3]) if row[3] else None,
                        updated_at=datetime.fromisoformat(row[4]) if row[4] else None
                    )
                return None
        except Exception as e:
            logger.error(f"Erro ao buscar produto: {e}")
            return None

    def list_produtos(self) -> List[Produto]:
        """Lista todos os produtos"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, nome_aba, status, created_at, updated_at FROM produtos ORDER BY nome_aba"
                )
                produtos = []
                for row in cursor.fetchall():
                    produtos.append(Produto(
                        id=row[0],
                        nome_aba=row[1],
                        status=row[2],
                        created_at=datetime.fromisoformat(row[3]) if row[3] else None,
                        updated_at=datetime.fromisoformat(row[4]) if row[4] else None
                    ))
                return produtos
        except Exception as e:
            logger.error(f"Erro ao listar produtos: {e}")
            return []

    # MÉTODOS PARA ASSENTOS
    def add_assento(self, produto_id: int, nome: str, modelo: str, revestimento: str,
                    ean: str = "", codigo: str = "", quantidade: int = 1) -> int:
        """Adiciona um assento com quantidade"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO assentos (produto_id, nome, modelo, revestimento, ean, codigo, quantidade) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (produto_id, nome, modelo, revestimento, ean, codigo, quantidade))
                assento_id = cursor.lastrowid
                conn.commit()
                logger.info(f"Assento adicionado: {modelo} - {revestimento} (ID: {assento_id}, Qtd: {quantidade})")
                return assento_id
        except Exception as e:
            logger.error(f"Erro ao adicionar assento: {e}")
            raise

    def list_assentos_by_produto(self, produto_id: int) -> List[Assento]:
        """Lista assentos de um produto com quantidade"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, produto_id, nome, modelo, revestimento, ean, codigo, 
                           COALESCE(quantidade, 1) as quantidade, status 
                    FROM assentos WHERE produto_id = ? ORDER BY modelo, revestimento
                """, (produto_id,))

                assentos = []
                for row in cursor.fetchall():
                    assentos.append(Assento(
                        id=row[0],
                        produto_id=row[1],
                        nome=row[2],
                        modelo=row[3],
                        revestimento=row[4],
                        ean=row[5],
                        codigo=row[6],
                        quantidade=row[7],
                        status=row[8]
                    ))
                return assentos
        except Exception as e:
            logger.error(f"Erro ao listar assentos: {e}")
            return []

    # MÉTODOS PARA PÉS/BASES
    def add_pe_base(self, produto_id: int, nome: str, ean: str = "", codigo: str = "",
                    quantidade: int = 1, tipo_contexto: str = "", grupo_pes: str = "",
                    marca: str = "") -> int:
        """Adiciona um pé ou base com contexto e grupo"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO pes_bases (produto_id, nome, ean, codigo, quantidade, tipo_contexto, grupo_pes, marca) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (produto_id, nome, ean, codigo, quantidade, tipo_contexto, grupo_pes, marca))
                pe_id = cursor.lastrowid
                conn.commit()
                logger.info(
                    f"Pé/Base adicionado: {nome} (ID: {pe_id}, Qtd: {quantidade}, Tipo: {tipo_contexto}, Grupo: {grupo_pes})")
                return pe_id
        except Exception as e:
            logger.error(f"Erro ao adicionar pé/base: {e}")
            raise

    def list_pes_bases_by_produto(self, produto_id: int) -> List[PeBase]:
        """Lista pés/bases de um produto com contexto e grupo"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, produto_id, nome, ean, codigo, quantidade, 
                           COALESCE(tipo_contexto, '') as tipo_contexto,
                           COALESCE(grupo_pes, '') as grupo_pes,
                           COALESCE(marca, '') as marca,
                           status 
                    FROM pes_bases WHERE produto_id = ? ORDER BY tipo_contexto, grupo_pes, nome
                """, (produto_id,))

                pes_bases = []
                for row in cursor.fetchall():
                    pes_bases.append(PeBase(
                        id=row[0],
                        produto_id=row[1],
                        nome=row[2],
                        ean=row[3],
                        codigo=row[4],
                        quantidade=row[5],
                        tipo_contexto=row[6],
                        grupo_pes=row[7],
                        marca=row[8],
                        status=row[9]
                    ))
                return pes_bases
        except Exception as e:
            logger.error(f"Erro ao listar pés/bases: {e}")
            return []

    # MÉTODOS PARA COMBINAÇÕES
    def add_combinacao(self, assento_id: int, pe_base_id: int, produto_id: int) -> int:
        """Adiciona uma combinação assento + pé/base"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO combinacoes (assento_id, pe_base_id, produto_id) 
                    VALUES (?, ?, ?)
                """, (assento_id, pe_base_id, produto_id))
                combinacao_id = cursor.lastrowid
                conn.commit()
                logger.info(f"Combinação adicionada: {assento_id} + {pe_base_id} (ID: {combinacao_id})")
                return combinacao_id
        except sqlite3.IntegrityError:
            logger.warning(f"Combinação já existe: {assento_id} + {pe_base_id}")
            return 0
        except Exception as e:
            logger.error(f"Erro ao adicionar combinação: {e}")
            raise

    def get_combinacoes_by_produto(self, produto_id: int) -> List[Tuple]:
        """Lista combinações de um produto com detalhes"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        c.id,
                        a.modelo, a.revestimento, a.ean as assento_ean,
                        p.nome as pe_nome, p.ean as pe_ean, p.quantidade
                    FROM combinacoes c
                    JOIN assentos a ON c.assento_id = a.id
                    JOIN pes_bases p ON c.pe_base_id = p.id
                    WHERE c.produto_id = ? AND c.status = 'Ativo'
                    ORDER BY a.modelo, a.revestimento, p.nome
                """, (produto_id,))

                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erro ao buscar combinações: {e}")
            return []

    def get_stats(self) -> dict:
        """Retorna estatísticas do banco"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT COUNT(*) FROM produtos WHERE status = 'Ativo'")
                total_produtos = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM assentos WHERE status = 'Ativo'")
                total_assentos = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM pes_bases WHERE status = 'Ativo'")
                total_pes = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM combinacoes WHERE status = 'Ativo'")
                total_combinacoes = cursor.fetchone()[0]

                return {
                    "total_produtos": total_produtos,
                    "total_assentos": total_assentos,
                    "total_pes_bases": total_pes,
                    "total_combinacoes": total_combinacoes
                }
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {e}")
            return {}

    def search_by_ean(self, ean: str) -> dict:
        """Busca produto por EAN (assento ou pé/base)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Busca em assentos
                cursor.execute("""
                    SELECT 'assento' as tipo, a.modelo, a.revestimento, p.nome_aba
                    FROM assentos a
                    JOIN produtos p ON a.produto_id = p.id
                    WHERE a.ean = ? AND a.status = 'Ativo'
                """, (ean,))

                assento = cursor.fetchone()
                if assento:
                    return {
                        "tipo": assento[0],
                        "modelo": assento[1],
                        "revestimento": assento[2],
                        "produto": assento[3]
                    }

                # Busca em pés/bases
                cursor.execute("""
                    SELECT 'pe_base' as tipo, pb.nome, p.nome_aba, pb.quantidade
                    FROM pes_bases pb
                    JOIN produtos p ON pb.produto_id = p.id
                    WHERE pb.ean = ? AND pb.status = 'Ativo'
                """, (ean,))

                pe_base = cursor.fetchone()
                if pe_base:
                    return {
                        "tipo": pe_base[0],
                        "nome": pe_base[1],
                        "produto": pe_base[2],
                        "quantidade": pe_base[3]
                    }

                return {}
        except Exception as e:
            logger.error(f"Erro ao buscar por EAN: {e}")
            return {}

    def clear_all_data(self):
        """Limpa todos os dados (para reimportação)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM combinacoes")
                cursor.execute("DELETE FROM assentos")
                cursor.execute("DELETE FROM pes_bases")
                cursor.execute("DELETE FROM produtos")
                conn.commit()
                logger.info("Todos os dados foram limpos")
        except Exception as e:
            logger.error(f"Erro ao limpar dados: {e}")
            raise

    # ✅ ADICIONAR ESTES MÉTODOS NA CLASSE ProductDatabase

    def update_produto(self, produto_id: int, nome_aba: str, status: str = "Ativo") -> bool:
        """Atualiza um produto"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE produtos 
                    SET nome_aba = ?, status = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, (nome_aba, status, produto_id))

                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"Produto {produto_id} atualizado: {nome_aba}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Erro ao atualizar produto: {e}")
            raise

    def delete_produto(self, produto_id: int) -> bool:
        """Exclui um produto e todos os seus componentes"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Buscar nome do produto para log
                cursor.execute("SELECT nome_aba FROM produtos WHERE id = ?", (produto_id,))
                produto_nome = cursor.fetchone()

                if not produto_nome:
                    return False

                # Excluir produto (CASCADE irá excluir componentes)
                cursor.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))

                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"Produto excluído: {produto_nome[0]} (ID: {produto_id})")
                    return True
                return False
        except Exception as e:
            logger.error(f"Erro ao excluir produto: {e}")
            raise

    def get_assento_by_id(self, assento_id: int) -> Optional[Assento]:
        """Busca assento por ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, produto_id, nome, modelo, revestimento, ean, codigo, status 
                    FROM assentos WHERE id = ?
                """, (assento_id,))

                row = cursor.fetchone()
                if row:
                    return Assento(
                        id=row[0],
                        produto_id=row[1],
                        nome=row[2],
                        modelo=row[3],
                        revestimento=row[4],
                        ean=row[5],
                        codigo=row[6],
                        status=row[7]
                    )
                return None
        except Exception as e:
            logger.error(f"Erro ao buscar assento: {e}")
            return None

    def update_assento(self, assento_id: int, nome: str, modelo: str, revestimento: str,
                       ean: str = "", codigo: str = "", status: str = "Ativo") -> bool:
        """Atualiza um assento"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE assentos 
                    SET nome = ?, modelo = ?, revestimento = ?, ean = ?, codigo = ?, status = ?
                    WHERE id = ?
                """, (nome, modelo, revestimento, ean, codigo, status, assento_id))

                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"Assento {assento_id} atualizado: {modelo} - {revestimento}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Erro ao atualizar assento: {e}")
            raise

    def delete_assento(self, assento_id: int) -> bool:
        """Exclui um assento"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Buscar dados do assento para log
                cursor.execute("SELECT modelo, revestimento FROM assentos WHERE id = ?", (assento_id,))
                assento_data = cursor.fetchone()

                if not assento_data:
                    return False

                # Excluir combinações relacionadas primeiro
                cursor.execute("DELETE FROM combinacoes WHERE assento_id = ?", (assento_id,))

                # Excluir assento
                cursor.execute("DELETE FROM assentos WHERE id = ?", (assento_id,))

                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"Assento excluído: {assento_data[0]} - {assento_data[1]} (ID: {assento_id})")
                    return True
                return False
        except Exception as e:
            logger.error(f"Erro ao excluir assento: {e}")
            raise

    def get_pe_base_by_id(self, pe_base_id: int) -> Optional[PeBase]:
        """Busca pé/base por ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, produto_id, nome, ean, codigo, quantidade, status 
                    FROM pes_bases WHERE id = ?
                """, (pe_base_id,))

                row = cursor.fetchone()
                if row:
                    return PeBase(
                        id=row[0],
                        produto_id=row[1],
                        nome=row[2],
                        ean=row[3],
                        codigo=row[4],
                        quantidade=row[5],
                        status=row[6]
                    )
                return None
        except Exception as e:
            logger.error(f"Erro ao buscar pé/base: {e}")
            return None

    def update_pe_base(self, pe_base_id: int, nome: str, ean: str = "", codigo: str = "",
                       quantidade: int = 1, status: str = "Ativo") -> bool:
        """Atualiza um pé/base"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE pes_bases 
                    SET nome = ?, ean = ?, codigo = ?, quantidade = ?, status = ?
                    WHERE id = ?
                """, (nome, ean, codigo, quantidade, status, pe_base_id))

                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"Pé/Base {pe_base_id} atualizado: {nome}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Erro ao atualizar pé/base: {e}")
            raise

    def delete_pe_base(self, pe_base_id: int) -> bool:
        """Exclui um pé/base"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Buscar dados do pé/base para log
                cursor.execute("SELECT nome FROM pes_bases WHERE id = ?", (pe_base_id,))
                pe_data = cursor.fetchone()

                if not pe_data:
                    return False

                # Excluir combinações relacionadas primeiro
                cursor.execute("DELETE FROM combinacoes WHERE pe_base_id = ?", (pe_base_id,))

                # Excluir pé/base
                cursor.execute("DELETE FROM pes_bases WHERE id = ?", (pe_base_id,))

                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"Pé/Base excluído: {pe_data[0]} (ID: {pe_base_id})")
                    return True
                return False
        except Exception as e:
            logger.error(f"Erro ao excluir pé/base: {e}")
            raise

    def delete_combinacao(self, combinacao_id: int) -> bool:
        """Exclui uma combinação"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM combinacoes WHERE id = ?", (combinacao_id,))

                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"Combinação excluída: ID {combinacao_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Erro ao excluir combinação: {e}")
            raise

    def clear_combinacoes_by_produto(self, produto_id: int) -> int:
        """Limpa todas as combinações de um produto"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM combinacoes WHERE produto_id = ?", (produto_id,))
                deleted_count = cursor.rowcount
                conn.commit()
                logger.info(f"Limpas {deleted_count} combinações do produto {produto_id}")
                return deleted_count
        except Exception as e:
            logger.error(f"Erro ao limpar combinações: {e}")
            raise

    def generate_combinations_for_produto(self, produto_id: int) -> int:
        """Gera todas as combinações possíveis para um produto"""
        try:
            assentos = self.list_assentos_by_produto(produto_id)
            pes_bases = self.list_pes_bases_by_produto(produto_id)

            combinations_added = 0

            for assento in assentos:
                for pe_base in pes_bases:
                    try:
                        self.add_combinacao(assento.id, pe_base.id, produto_id)
                        combinations_added += 1
                    except Exception:
                        # Combinação já existe, ignorar
                        pass

            logger.info(f"Geradas {combinations_added} novas combinações para produto {produto_id}")
            return combinations_added

        except Exception as e:
            logger.error(f"Erro ao gerar combinações: {e}")
            raise

    def add_componente_especial(self, produto_id: int, tipo_componente: str, nome: str,
                                ean: str = "", codigo: str = "", quantidade: int = 1,
                                dados_extras: Dict = None) -> int:
        """Adiciona um componente especial (almofada, fórmula, etc.)"""
        try:
            dados_json = json.dumps(dados_extras or {})

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO componentes_especiais (produto_id, tipo_componente, nome, ean, codigo, quantidade, dados_extras) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (produto_id, tipo_componente, nome, ean, codigo, quantidade, dados_json))
                comp_id = cursor.lastrowid
                conn.commit()
                logger.info(f"Componente especial adicionado: {tipo_componente} - {nome} (ID: {comp_id})")
                return comp_id
        except Exception as e:
            logger.error(f"Erro ao adicionar componente especial: {e}")
            raise

    def add_loja_web_data(self, produto_id: int, categoria_principal: str = "",
                          nivel_adicional_1: str = "", nivel_adicional_2: str = "",
                          titulo_produto: str = "", descricao_curta: str = "",
                          descricao_longa: str = "", palavras_chave: str = "") -> int:
        """Adiciona dados da loja web"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO loja_web (produto_id, categoria_principal, nivel_adicional_1, 
                                        nivel_adicional_2, titulo_produto, descricao_curta, 
                                        descricao_longa, palavras_chave) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (produto_id, categoria_principal, nivel_adicional_1, nivel_adicional_2,
                      titulo_produto, descricao_curta, descricao_longa, palavras_chave))
                loja_web_id = cursor.lastrowid
                conn.commit()
                logger.info(f"Dados loja web adicionados: {categoria_principal} (ID: {loja_web_id})")
                return loja_web_id
        except Exception as e:
            logger.error(f"Erro ao adicionar dados loja web: {e}")
            raise

    def get_loja_web_by_produto(self, produto_id: int) -> Optional[LojaWebData]:
        """Busca dados da loja web por produto"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, produto_id, categoria_principal, nivel_adicional_1, nivel_adicional_2,
                           titulo_produto, descricao_curta, descricao_longa, palavras_chave, status
                    FROM loja_web WHERE produto_id = ?
                """, (produto_id,))

                row = cursor.fetchone()
                if row:
                    return LojaWebData(
                        id=row[0], produto_id=row[1], categoria_principal=row[2],
                        nivel_adicional_1=row[3], nivel_adicional_2=row[4],
                        titulo_produto=row[5], descricao_curta=row[6],
                        descricao_longa=row[7], palavras_chave=row[8], status=row[9]
                    )
                return None
        except Exception as e:
            logger.error(f"Erro ao buscar dados loja web: {e}")
            return None

    def list_componentes_especiais_by_produto(self, produto_id: int) -> List[ComponenteEspecial]:
        """Lista componentes especiais de um produto"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, produto_id, tipo_componente, nome, ean, codigo, quantidade, dados_extras, status 
                    FROM componentes_especiais WHERE produto_id = ? ORDER BY tipo_componente, nome
                """, (produto_id,))

                componentes = []
                for row in cursor.fetchall():
                    componentes.append(ComponenteEspecial(
                        id=row[0],
                        produto_id=row[1],
                        tipo_componente=row[2],
                        nome=row[3],
                        ean=row[4],
                        codigo=row[5],
                        quantidade=row[6],
                        dados_extras=row[7],
                        status=row[8]
                    ))
                return componentes
        except Exception as e:
            logger.error(f"Erro ao listar componentes especiais: {e}")
            return []