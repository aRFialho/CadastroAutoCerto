"""Importador de dados da planilha de produtos - VERSÃO ATUALIZADA"""

import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

from ..core.product_database import ProductDatabase
from ..utils.logger import get_logger

logger = get_logger("product_importer")


@dataclass
class ImportResult:
    """Resultado da importação"""
    success: bool = False
    total_produtos: int = 0
    total_assentos: int = 0
    total_pes_bases: int = 0
    total_componentes_especiais: int = 0
    total_combinacoes: int = 0
    errors: List[str] = None
    warnings: List[str] = None
    processing_time: float = 0.0

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


@dataclass
class SheetStructure:
    """Estrutura detectada de uma aba"""
    sheet_name: str
    structure_type: str  # "simples", "dupla", "complexa", "especial"
    assentos_section: Dict
    pes_sections: List[Dict]  # Lista para múltiplas seções de pés
    componentes_especiais: List[Dict] = None
    has_formulas: bool = False

    def __post_init__(self):
        if self.componentes_especiais is None:
            self.componentes_especiais = []


class ProductImporter:
    """Importador de produtos da planilha Excel - VERSÃO ATUALIZADA"""

    def __init__(self, db_path: Path):
        self.db = ProductDatabase(db_path)
        self.result = ImportResult()

        # ✅ INICIALIZAR CATEGORY MANAGER
        try:
            from ..services.category_manager import CategoryManager
            # Buscar arquivo de categorias nos caminhos padrão
            category_db_path = self._find_category_db_path(db_path)
            if category_db_path:
                # Usar senha padrão - você pode configurar isso
                self.category_manager = CategoryManager(category_db_path, password="admin123")
                logger.info(f"✅ CategoryManager inicializado: {category_db_path}")
            else:
                logger.warning("⚠️ Arquivo de categorias não encontrado")
                self.category_manager = None
        except Exception as e:
            logger.warning(f"⚠️ CategoryManager não disponível: {e}")
            self.category_manager = None

    def _find_category_db_path(self, db_path: Path) -> Optional[Path]:
        """Encontra o arquivo de categorias nos caminhos padrão"""
        possible_paths = [
            db_path.parent / "data" / "DB_CATEGORIAS.json",
            db_path.parent / "DB_CATEGORIAS.json",
            Path("data/DB_CATEGORIAS.json"),
            Path("outputs/DB_CATEGORIAS.json"),
            Path("DB_CATEGORIAS.json")
        ]

        for path in possible_paths:
            if path.exists():
                logger.info(f"📁 Arquivo de categorias encontrado: {path}")
                return path

        logger.warning("📁 Arquivo de categorias não encontrado nos caminhos:")
        for path in possible_paths:
            logger.warning(f"  ❌ {path}")

        return None

    def import_from_excel(self, excel_path: Path, clear_existing: bool = False) -> ImportResult:
        """
        Importa dados da planilha Excel com detecção automática de estrutura
        """
        import time
        start_time = time.time()

        try:
            logger.info(f"🔍 Iniciando importação avançada de: {excel_path}")

            if clear_existing:
                logger.info("🧹 Limpando dados existentes...")
                self.db.clear_all_data()
                self.result.warnings.append("Dados existentes foram removidos")

            # Ler arquivo Excel e obter nomes das abas
            excel_file = pd.ExcelFile(excel_path)
            sheet_names = excel_file.sheet_names

            logger.info(f"📋 Encontradas {len(sheet_names)} abas: {sheet_names}")

            # ✅ PRIMEIRO: PROCESSAR ABA LOJA WEB (se existir)
            loja_web_data = {}
            if "LOJA WEB" in sheet_names:
                logger.info("🛒 Processando aba LOJA WEB...")
                loja_web_data = self._process_loja_web_sheet(excel_file)
            else:
                logger.warning("⚠️ Aba 'LOJA WEB' não encontrada")

            # Processar cada aba com detecção de estrutura
            for sheet_name in sheet_names:
                if sheet_name == "LOJA WEB":
                    continue  # Já processada acima

                try:
                    self._process_sheet_advanced(excel_file, sheet_name, loja_web_data)
                except Exception as e:
                    error_msg = f"Erro ao processar aba '{sheet_name}': {e}"
                    logger.error(error_msg)
                    self.result.errors.append(error_msg)

            logger.info("⚠️ Combinações não foram geradas automaticamente. Use o botão 'Gerar Combinações' na interface para produtos específicos.")

            # Finalizar
            self.result.processing_time = time.time() - start_time
            self.result.success = len(self.result.errors) == 0

            if self.result.success:
                logger.info(f"✅ Importação concluída com sucesso em {self.result.processing_time:.2f}s")
            else:
                logger.warning(f"⚠️ Importação concluída com {len(self.result.errors)} erros")

            return self.result

        except Exception as e:
            self.result.processing_time = time.time() - start_time
            self.result.success = False
            error_msg = f"Erro fatal na importação: {e}"
            logger.error(error_msg)
            self.result.errors.append(error_msg)
            return self.result

    def _process_loja_web_sheet(self, excel_file: pd.ExcelFile) -> Dict:
        """Processa a aba LOJA WEB e retorna dados mapeados por produto"""
        try:
            logger.info("🛒 === PROCESSANDO ABA LOJA WEB ===")

            # Ler aba LOJA WEB
            df = pd.read_excel(excel_file, sheet_name="LOJA WEB", header=None)
            df_clean = df.fillna('')

            # ✅ ENCONTRAR CABEÇALHOS
            headers_row = self._find_loja_web_headers(df_clean)
            if not headers_row:
                logger.warning("⚠️ Cabeçalhos da LOJA WEB não encontrados")
                return {}

            # ✅ EXTRAIR DADOS
            loja_web_data = self._extract_loja_web_data(df_clean, headers_row)

            logger.success(f"✅ Processados {len(loja_web_data)} produtos da LOJA WEB")
            return loja_web_data

        except Exception as e:
            logger.error(f"Erro ao processar aba LOJA WEB: {e}")
            return {}

    def _find_loja_web_headers(self, df: pd.DataFrame) -> Optional[Dict]:
        """Encontra cabeçalhos da aba LOJA WEB"""
        try:
            # ✅ CABEÇALHOS ESPERADOS
            expected_headers = {
                'produto': ['produto', 'nome produto', 'aba', 'nome da aba'],
                'categoria': ['categoria', 'codigo categoria', 'código categoria'],
                'categoria_principal': ['categoria principal tray', 'principal tray'],
                'nivel_adicional_1': ['nivel adicional 1 tray', 'nível adicional 1'],
                'nivel_adicional_2': ['nivel adicional 2 tray', 'nível adicional 2'],
                'titulo_produto': ['titulo produto', 'título produto'],
                'descricao_curta': ['descricao curta', 'descrição curta'],
                'descricao_longa': ['descricao longa', 'descrição longa'],
                'palavras_chave': ['palavras chave', 'palavras-chave', 'keywords']
            }

            # ✅ BUSCAR LINHA DE CABEÇALHOS
            for row_idx in range(min(10, len(df))):
                row = df.iloc[row_idx].astype(str).str.lower()

                # Contar quantos cabeçalhos encontrou
                found_headers = 0
                for header_group in expected_headers.values():
                    if any(any(header in cell for header in header_group)
                           for cell in row if cell and cell != 'nan'):
                        found_headers += 1

                # Se encontrou pelo menos 3 cabeçalhos, é provável que seja a linha correta
                if found_headers >= 3:
                    # ✅ MAPEAR COLUNAS
                    columns = {}
                    for col_idx, cell in enumerate(row):
                        if not cell or cell == 'nan':
                            continue

                        cell_clean = cell.strip()

                        # Mapear para campos conhecidos
                        for field, keywords in expected_headers.items():
                            if field not in columns and any(keyword in cell_clean for keyword in keywords):
                                columns[field] = col_idx
                                break

                    if columns:
                        logger.info(f"📍 Cabeçalhos LOJA WEB encontrados na linha {row_idx}")
                        logger.debug(f"Colunas mapeadas: {columns}")
                        return {
                            'header_row': row_idx,
                            'columns': columns,
                            'data_start': row_idx + 1
                        }

            return None

        except Exception as e:
            logger.error(f"Erro ao encontrar cabeçalhos LOJA WEB: {e}")
            return None

    def _extract_loja_web_data(self, df: pd.DataFrame, headers_info: Dict) -> Dict:
        """Extrai dados da aba LOJA WEB"""
        try:
            columns = headers_info['columns']
            start_row = headers_info['data_start']
            loja_web_data = {}

            logger.info(f"🔍 Extraindo dados da LOJA WEB a partir da linha {start_row}")

            for row_idx in range(start_row, len(df)):
                row = df.iloc[row_idx]

                # ✅ OBTER NOME DO PRODUTO
                produto_nome = ""
                if 'produto' in columns:
                    produto_nome = str(row.iloc[columns['produto']]).strip()

                if not produto_nome or produto_nome.lower() in ['nan', 'none', '']:
                    continue

                # ✅ OBTER CÓDIGO DA CATEGORIA
                categoria_codigo = ""
                if 'categoria' in columns:
                    categoria_codigo = str(row.iloc[columns['categoria']]).strip()

                # ✅ MAPEAR CATEGORIA USANDO CATEGORY MANAGER
                categorias = self._map_category_from_code(categoria_codigo)

                # ✅ OBTER OUTROS DADOS (se disponíveis)
                def get_cell_value(field: str) -> str:
                    if field in columns and columns[field] < len(row):
                        value = str(row.iloc[columns[field]]).strip()
                        return "" if value.lower() in ['nan', 'none'] else value
                    return ""

                loja_web_data[produto_nome] = {
                    'categoria_codigo': categoria_codigo,
                    'categoria_principal': categorias.get('categoria_principal', get_cell_value('categoria_principal')),
                    'nivel_adicional_1': categorias.get('nivel_adicional_1', get_cell_value('nivel_adicional_1')),
                    'nivel_adicional_2': categorias.get('nivel_adicional_2', get_cell_value('nivel_adicional_2')),
                    'titulo_produto': get_cell_value('titulo_produto') or produto_nome,
                    'descricao_curta': get_cell_value('descricao_curta'),
                    'descricao_longa': get_cell_value('descricao_longa'),
                    'palavras_chave': get_cell_value('palavras_chave')
                }

                logger.debug(f"Produto LOJA WEB: {produto_nome} → {categorias}")

            logger.info(f"✅ Extraídos dados de {len(loja_web_data)} produtos da LOJA WEB")
            return loja_web_data

        except Exception as e:
            logger.error(f"Erro ao extrair dados LOJA WEB: {e}")
            return {}

    def _map_category_from_code(self, categoria_codigo: str) -> Dict[str, str]:
        """Mapeia código da categoria para hierarquia usando CategoryManager"""
        try:
            if not categoria_codigo or not self.category_manager:
                return {}

            # ✅ BUSCAR CATEGORIA POR ID
            try:
                category_id = int(categoria_codigo)
            except ValueError:
                logger.warning(f"Código de categoria inválido: {categoria_codigo}")
                return {}

            # ✅ OBTER CAMINHO DA CATEGORIA
            category_path = self.category_manager.get_category_path(category_id)

            if not category_path:
                logger.warning(f"Categoria não encontrada para código: {categoria_codigo}")
                return {}

            # ✅ DIVIDIR CAMINHO EM NÍVEIS
            path_parts = [part.strip() for part in category_path.split('>')]

            result = {}
            if len(path_parts) >= 1:
                result['categoria_principal'] = path_parts[0]
            if len(path_parts) >= 2:
                result['nivel_adicional_1'] = path_parts[1]
            if len(path_parts) >= 3:
                result['nivel_adicional_2'] = path_parts[2]

            logger.debug(f"Categoria {categoria_codigo} mapeada: {category_path} → {result}")
            return result

        except Exception as e:
            logger.error(f"Erro ao mapear categoria {categoria_codigo}: {e}")
            return {}

    def _process_sheet_advanced(self, excel_file: pd.ExcelFile, sheet_name: str, loja_web_data: Dict = None):
        """Processa uma aba com detecção avançada de estrutura E dados da loja web"""
        logger.info(f"🔍 === PROCESSANDO ABA: {sheet_name} ===")

        try:
            # Ler dados da aba
            df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
            df_clean = df.fillna('')

            # ✅ DETECTAR ESTRUTURA DA ABA
            structure = self._detect_sheet_structure(df_clean, sheet_name)
            logger.info(f"📊 Estrutura detectada: {structure.structure_type}")

            # Adicionar produto principal
            produto_id = self.db.add_produto(sheet_name)
            self.result.total_produtos += 1
            logger.info(f"📦 Produto '{sheet_name}' adicionado com ID: {produto_id}")

            # ✅ PROCESSAR CATEGORIAS DA LOJA WEB (se disponível)
            if loja_web_data and sheet_name in loja_web_data:
                self._save_loja_web_data(produto_id, sheet_name, loja_web_data[sheet_name])
            else:
                logger.info(f"ℹ️ Dados da LOJA WEB não encontrados para '{sheet_name}'")

            # ✅ PROCESSAR ASSENTOS
            if structure.assentos_section:
                assentos_data = self._extract_assentos_data_advanced(df_clean, structure.assentos_section, sheet_name)
                self._save_assentos(produto_id, assentos_data, sheet_name)

            # ✅ PROCESSAR PÉS/BASES (MÚLTIPLAS SEÇÕES)
            for i, pes_section in enumerate(structure.pes_sections):
                pes_data = self._extract_pes_data_advanced(df_clean, pes_section, sheet_name, i + 1)
                self._save_pes_bases(produto_id, pes_data, sheet_name, pes_section.get('grupo', f'Grupo_{i + 1}'))

            # ✅ PROCESSAR COMPONENTES ESPECIAIS
            for comp_section in structure.componentes_especiais:
                comp_data = self._extract_componentes_especiais(df_clean, comp_section, sheet_name)
                self._save_componentes_especiais(produto_id, comp_data, sheet_name)

            logger.success(f"✅ Aba '{sheet_name}' processada com sucesso!")

        except Exception as e:
            raise Exception(f"Erro ao processar aba '{sheet_name}': {e}")

    def _save_loja_web_data(self, produto_id: int, sheet_name: str, loja_data: Dict):
        """Salva dados da loja web no banco"""
        try:
            self.db.add_loja_web_data(
                produto_id=produto_id,
                categoria_principal=loja_data.get('categoria_principal', ''),
                nivel_adicional_1=loja_data.get('nivel_adicional_1', ''),
                nivel_adicional_2=loja_data.get('nivel_adicional_2', ''),
                titulo_produto=loja_data.get('titulo_produto', sheet_name),
                descricao_curta=loja_data.get('descricao_curta', ''),
                descricao_longa=loja_data.get('descricao_longa', ''),
                palavras_chave=loja_data.get('palavras_chave', '')
            )

            logger.success(f"🏷️ Dados da loja web salvos para '{sheet_name}': {loja_data.get('categoria_principal', '')} > {loja_data.get('nivel_adicional_1', '')} > {loja_data.get('nivel_adicional_2', '')}")

        except Exception as e:
            logger.error(f"Erro ao salvar dados da loja web para '{sheet_name}': {e}")
            # Não falhar a importação por causa das categorias

    # ✅ RESTO DOS MÉTODOS PERMANECEM IGUAIS (copiando do seu código)
    def _detect_sheet_structure(self, df: pd.DataFrame, sheet_name: str) -> SheetStructure:
        """Detecta automaticamente a estrutura de uma aba baseado nos padrões encontrados"""
        logger.info(f"🔍 Detectando estrutura da aba: {sheet_name}")

        # ✅ DETECTAR SEÇÃO DE ASSENTOS
        assentos_section = self._find_assentos_section_advanced(df)

        # ✅ DETECTAR MÚLTIPLAS SEÇÕES DE PÉS/BASES
        pes_sections = self._find_multiple_pes_sections(df)

        # ✅ DETECTAR COMPONENTES ESPECIAIS
        componentes_especiais = self._find_componentes_especiais(df, sheet_name)

        # ✅ DETERMINAR TIPO DE ESTRUTURA
        structure_type = self._classify_structure_type(assentos_section, pes_sections, componentes_especiais)

        structure = SheetStructure(
            sheet_name=sheet_name,
            structure_type=structure_type,
            assentos_section=assentos_section,
            pes_sections=pes_sections,
            componentes_especiais=componentes_especiais,
            has_formulas=self._detect_formulas(df)
        )

        logger.info(f"📊 === ESTRUTURA DETECTADA PARA {sheet_name} ===")
        logger.info(f"  🏷️ Tipo: {structure_type}")
        logger.info(f"  🪑 Assentos: {'✅' if assentos_section else '❌'}")
        logger.info(f"  🦵 Seções de Pés: {len(pes_sections)}")
        logger.info(f"  🔧 Componentes Especiais: {len(componentes_especiais)}")
        logger.info(f"  📐 Tem Fórmulas: {'✅' if structure.has_formulas else '❌'}")

        return structure

    def _find_multiple_pes_sections(self, df: pd.DataFrame) -> List[Dict]:
        """Encontra múltiplas seções de pés/bases (DMOV, DMOV2, etc.)"""
        pes_sections = []

        # ✅ PADRÕES PARA DIFERENTES GRUPOS DE PÉS
        grupos_conhecidos = [
            {"nome": "DMOV", "padroes": ["dmov", "d'mov"], "contextos": ["poltrona", "namoradeira"]},
            {"nome": "DMOV2", "padroes": ["dmov2", "d'mov2"], "contextos": ["poltrona", "namoradeira"]},
            {"nome": "D'ROSSI", "padroes": ["d'rossi", "drossi"], "contextos": ["poltrona", "namoradeira", "puff"]},
            {"nome": "GERAL", "padroes": ["pé", "pe", "base"], "contextos": ["geral"]}
        ]

        # Buscar por cada grupo
        for grupo in grupos_conhecidos:
            section = self._find_pes_section_by_group(df, grupo)
            if section:
                pes_sections.append(section)

        # Se não encontrou grupos específicos, usar busca genérica
        if not pes_sections:
            generic_section = self._find_pes_section_generic(df)
            if generic_section:
                pes_sections.append(generic_section)

        logger.info(f"🦵 Encontradas {len(pes_sections)} seções de pés/bases")
        for i, section in enumerate(pes_sections):
            logger.info(f"  Seção {i+1}: {section.get('grupo', 'Genérica')} (colunas: {len(section.get('columns', {}))})")

        return pes_sections

    def _find_pes_section_by_group(self, df: pd.DataFrame, grupo: Dict) -> Optional[Dict]:
        """Encontra seção de pés específica por grupo"""
        try:
            grupo_nome = grupo["nome"]
            padroes = grupo["padroes"]

            # Buscar cabeçalhos que contenham os padrões do grupo
            for row_idx in range(min(15, len(df))):
                row = df.iloc[row_idx].astype(str).str.lower()

                # Verificar se algum padrão do grupo está presente
                grupo_encontrado = any(
                    any(padrao in cell for cell in row if cell and cell != 'nan')
                    for padrao in padroes
                )

                if grupo_encontrado:
                    # Detectar colunas desta seção
                    cols = self._detect_pes_columns_in_row(row, row_idx, df)

                    if cols and len(cols) >= 2:  # Pelo menos nome e quantidade
                        return {
                            'header_row': row_idx,
                            'columns': cols,
                            'data_start': row_idx + 1,
                            'grupo': grupo_nome,
                            'contextos': grupo["contextos"]
                        }

            return None

        except Exception as e:
            logger.error(f"Erro ao buscar seção do grupo {grupo['nome']}: {e}")
            return None

    def _detect_pes_columns_in_row(self, row: pd.Series, row_idx: int, df: pd.DataFrame) -> Dict:
        """Detecta colunas de pés em uma linha específica"""
        cols = {}

        # Mapear cabeçalhos conhecidos
        header_mappings = {
            'nome': ['nome', 'pé', 'pe', 'base', 'dmov', 'drossi'],
            'ean': ['ean', 'código de barras', 'codigo de barras'],
            'codigo': ['código', 'codigo', 'cod', 'referência', 'ref'],
            'quantidade': ['quantidade', 'qtd', 'qtde', 'quant'],
            'marca': ['marca', 'fabricante']
        }

        for col_idx, cell in enumerate(row):
            if not cell or cell == 'nan':
                continue

            cell_lower = str(cell).lower().strip()

            # Mapear para campos conhecidos
            for field, keywords in header_mappings.items():
                if field not in cols and any(keyword in cell_lower for keyword in keywords):
                    cols[field] = col_idx
                    break

        return cols

    def _find_pes_section_generic(self, df: pd.DataFrame) -> Optional[Dict]:
        """Busca genérica por seção de pés quando não encontra grupos específicos"""
        try:
            # Buscar por cabeçalhos típicos de pés/bases
            pes_headers = ['pé', 'pe', 'pés', 'pes', 'base', 'nome', 'ean', 'código', 'quantidade']

            for row_idx in range(min(10, len(df))):
                row = df.iloc[row_idx].astype(str).str.lower()

                # Contar quantos cabeçalhos de pés encontrou
                header_matches = sum(
                    1 for header in pes_headers
                    if any(header in cell for cell in row if cell and cell != 'nan')
                )

                if header_matches >= 2:  # Pelo menos 2 cabeçalhos
                    cols = self._detect_pes_columns_in_row(row, row_idx, df)

                    if cols:
                        return {
                            'header_row': row_idx,
                            'columns': cols,
                            'data_start': row_idx + 1,
                            'grupo': 'GERAL',
                            'contextos': ['geral']
                        }

            return None

        except Exception as e:
            logger.error(f"Erro na busca genérica de pés: {e}")
            return None

    def _find_componentes_especiais(self, df: pd.DataFrame, sheet_name: str) -> List[Dict]:
        """Detecta componentes especiais como almofadas, fórmulas, etc."""
        componentes = []

        # ✅ DETECTAR ALMOFADAS (como na aba Costela)
        if 'costela' in sheet_name.lower():
            almofada_section = self._find_almofada_section(df)
            if almofada_section:
                componentes.append(almofada_section)

        # ✅ DETECTAR OUTRAS ESTRUTURAS ESPECIAIS
        # Adicionar mais detectores conforme necessário

        return componentes

    def _find_almofada_section(self, df: pd.DataFrame) -> Optional[Dict]:
        """Detecta seção de almofadas"""
        try:
            # Buscar por "almofada" ou padrões similares
            for row_idx in range(min(15, len(df))):
                row = df.iloc[row_idx].astype(str).str.lower()

                if any('almofada' in cell for cell in row if cell and cell != 'nan'):
                    # Detectar colunas da almofada
                    cols = {}
                    for col_idx, cell in enumerate(row):
                        if not cell or cell == 'nan':
                            continue

                        cell_lower = str(cell).lower().strip()

                        if 'almofada' in cell_lower and 'nome' not in cols:
                            cols['nome'] = col_idx
                        elif 'ean' in cell_lower:
                            cols['ean'] = col_idx
                        elif 'código' in cell_lower or 'codigo' in cell_lower:
                            cols['codigo'] = col_idx
                        elif 'quantidade' in cell_lower or 'qtd' in cell_lower:
                            cols['quantidade'] = col_idx

                    if cols:
                        return {
                            'tipo': 'almofada',
                            'header_row': row_idx,
                            'columns': cols,
                            'data_start': row_idx + 1
                        }

            return None

        except Exception as e:
            logger.error(f"Erro ao detectar almofadas: {e}")
            return None

    def _classify_structure_type(self, assentos_section: Dict, pes_sections: List[Dict],
                                componentes_especiais: List[Dict]) -> str:
        """Classifica o tipo de estrutura da aba"""

        num_pes_sections = len(pes_sections)
        has_especiais = len(componentes_especiais) > 0

        if has_especiais:
            return "especial"
        elif num_pes_sections >= 3:
            return "muito_complexa"
        elif num_pes_sections == 2:
            return "complexa"
        elif num_pes_sections == 1:
            return "simples"
        else:
            return "sem_pes"

    def _find_assentos_section_advanced(self, df: pd.DataFrame) -> Optional[Dict]:
        """Versão avançada da detecção de assentos"""
        try:
            # Cabeçalhos típicos de assentos
            assentos_headers = ['nome', 'modelo', 'revestimento', 'ean', 'código', 'codigo', 'quantidade']

            for row_idx in range(min(10, len(df))):
                row = df.iloc[row_idx].astype(str).str.lower()

                # Verificar se a linha contém cabeçalhos de assentos
                header_matches = sum(
                    1 for header in assentos_headers
                    if any(header in cell for cell in row if cell and cell != 'nan')
                )

                if header_matches >= 3:  # Pelo menos 3 cabeçalhos encontrados
                    # Determinar colunas
                    cols = {}
                    for col_idx, cell in enumerate(row):
                        if not cell or cell == 'nan':
                            continue

                        cell_lower = str(cell).lower().strip()

                        if 'nome' in cell_lower and 'nome' not in cols:
                            cols['nome'] = col_idx
                        elif 'modelo' in cell_lower:
                            cols['modelo'] = col_idx
                        elif 'revestimento' in cell_lower:
                            cols['revestimento'] = col_idx
                        elif 'ean' in cell_lower:
                            cols['ean'] = col_idx
                        elif 'código' in cell_lower or 'codigo' in cell_lower:
                            cols['codigo'] = col_idx
                        elif 'quantidade' in cell_lower or 'qtd' in cell_lower:
                            cols['quantidade'] = col_idx

                    if len(cols) >= 3:
                        return {
                            'header_row': row_idx,
                            'columns': cols,
                            'data_start': row_idx + 1
                        }

            # Se não encontrou cabeçalhos, usar estrutura padrão
            logger.warning("Cabeçalhos de assentos não encontrados, usando estrutura padrão")
            return {
                'header_row': 0,
                'columns': {'nome': 0, 'modelo': 1, 'revestimento': 2, 'ean': 3, 'codigo': 4, 'quantidade': 5},
                'data_start': 1
            }

        except Exception as e:
            logger.error(f"Erro ao encontrar seção de assentos: {e}")
            return None

    def _extract_assentos_data_advanced(self, df: pd.DataFrame, section: Dict, sheet_name: str) -> List[Dict]:
        """Extrai dados dos assentos com suporte a quantidade"""
        assentos = []

        try:
            cols = section['columns']
            start_row = section['data_start']

            for row_idx in range(start_row, len(df)):
                row = df.iloc[row_idx]

                # Verificar se a linha tem dados válidos
                nome = str(row.iloc[cols.get('nome', 0)]).strip() if cols.get('nome', 0) < len(row) else ""
                modelo = str(row.iloc[cols.get('modelo', 1)]).strip() if cols.get('modelo', 1) < len(row) else ""
                revestimento = str(row.iloc[cols.get('revestimento', 2)]).strip() if cols.get('revestimento', 2) < len(row) else ""

                # Pular linhas vazias
                if not nome and not modelo and not revestimento:
                    continue

                # Processar campos
                if not nome:
                    nome = f"Assento {sheet_name}"
                if not modelo:
                    modelo = sheet_name
                if not revestimento:
                    revestimento = "Padrão"

                ean = str(row.iloc[cols.get('ean', 3)]).strip() if cols.get('ean', 3) < len(row) else ""
                codigo = str(row.iloc[cols.get('codigo', 4)]).strip() if cols.get('codigo', 4) < len(row) else ""

                # ✅ PROCESSAR QUANTIDADE
                quantidade_str = str(row.iloc[cols.get('quantidade', 5)]).strip() if cols.get('quantidade', 5) < len(row) else "1"
                try:
                    quantidade = int(float(quantidade_str)) if quantidade_str and quantidade_str.lower() not in ['nan', 'none', ''] else 1
                except Exception:
                    quantidade = 1

                # Limpar valores 'nan'
                ean = "" if ean.lower() in ['nan', 'none'] else ean
                codigo = "" if codigo.lower() in ['nan', 'none'] else codigo

                assento_data = {
                    'nome': nome,
                    'modelo': modelo,
                    'revestimento': revestimento,
                    'ean': ean,
                    'codigo': codigo,
                    'quantidade': quantidade
                }

                assentos.append(assento_data)
                logger.debug(f"Assento extraído: {assento_data}")

        except Exception as e:
            logger.error(f"Erro ao extrair dados de assentos: {e}")
            raise

        return assentos

    def _extract_pes_data_advanced(self, df: pd.DataFrame, section: Dict, sheet_name: str, section_num: int) -> List[Dict]:
        """Extrai dados dos pés/bases com contexto e grupo"""
        pes_bases = []

        try:
            cols = section['columns']
            start_row = section['data_start']
            grupo = section.get('grupo', f'Grupo_{section_num}')
            contextos = section.get('contextos', ['geral'])

            logger.info(f"🦵 Extraindo pés do grupo: {grupo}")

            for row_idx in range(start_row, len(df)):
                row = df.iloc[row_idx]

                # Verificar se a linha tem dados válidos
                nome = str(row.iloc[cols.get('nome', 0)]).strip() if cols.get('nome', 0) < len(row) else ""

                # Pular linhas vazias
                if not nome or nome.lower() in ['nan', 'none']:
                    continue

                ean = str(row.iloc[cols.get('ean', 1)]).strip() if cols.get('ean', 1) < len(row) else ""
                codigo = str(row.iloc[cols.get('codigo', 2)]).strip() if cols.get('codigo', 2) < len(row) else ""
                marca = str(row.iloc[cols.get('marca', 3)]).strip() if cols.get('marca', 3) < len(row) else ""

                # Processar quantidade
                quantidade_str = str(row.iloc[cols.get('quantidade', 4)]).strip() if cols.get('quantidade', 4) < len(row) else "1"
                try:
                    quantidade = int(float(quantidade_str)) if quantidade_str and quantidade_str.lower() not in ['nan', 'none', ''] else 1
                except Exception:
                    quantidade = 1

                # Limpar valores 'nan'
                ean = "" if ean.lower() in ['nan', 'none'] else ean
                codigo = "" if codigo.lower() in ['nan', 'none'] else codigo
                marca = "" if marca.lower() in ['nan', 'none'] else marca

                # ✅ DETECTAR CONTEXTO ESPECÍFICO (Poltrona, Namoradeira, Puff)
                tipo_contexto = self._detect_context_from_name(nome, contextos)

                pe_base_data = {
                    'nome': nome,
                    'ean': ean,
                    'codigo': codigo,
                    'marca': marca,
                    'quantidade': quantidade,
                    'tipo_contexto': tipo_contexto,
                    'grupo_pes': grupo
                }

                pes_bases.append(pe_base_data)
                logger.debug(f"Pé/Base extraído: {pe_base_data}")

        except Exception as e:
            logger.error(f"Erro ao extrair dados de pés/bases: {e}")
            raise

        return pes_bases

    def _detect_context_from_name(self, nome: str, contextos_possiveis: List[str]) -> str:
        """Detecta o contexto (Poltrona, Namoradeira, Puff) baseado no nome"""
        nome_lower = nome.lower()

        # Palavras-chave para cada contexto
        context_keywords = {
            'Poltrona': ['poltrona', 'cadeira', 'chair'],
            'Namoradeira': ['namoradeira', 'loveseat', 'dois lugares'],
            'Puff': ['puff', 'pufe', 'ottoman'],
            'Sofá': ['sofa', 'sofá', 'couch']
        }

        # Buscar por palavras-chave no nome
        for context, keywords in context_keywords.items():
            if any(keyword in nome_lower for keyword in keywords):
                return context

        # Se não encontrou contexto específico, usar o primeiro dos possíveis
        if contextos_possiveis and contextos_possiveis[0] != 'geral':
            return contextos_possiveis[0].title()

        return "Geral"

    def _extract_componentes_especiais(self, df: pd.DataFrame, section: Dict, sheet_name: str) -> List[Dict]:
        """Extrai componentes especiais como almofadas"""
        componentes = []

        try:
            tipo_componente = section['tipo']
            cols = section['columns']
            start_row = section['data_start']

            logger.info(f"🔧 Extraindo componentes especiais: {tipo_componente}")

            for row_idx in range(start_row, len(df)):
                row = df.iloc[row_idx]

                # Verificar se a linha tem dados válidos
                nome = str(row.iloc[cols.get('nome', 0)]).strip() if cols.get('nome', 0) < len(row) else ""

                if not nome or nome.lower() in ['nan', 'none']:
                    continue

                ean = str(row.iloc[cols.get('ean', 1)]).strip() if cols.get('ean', 1) < len(row) else ""
                codigo = str(row.iloc[cols.get('codigo', 2)]).strip() if cols.get('codigo', 2) < len(row) else ""

                # Processar quantidade
                quantidade_str = str(row.iloc[cols.get('quantidade', 3)]).strip() if cols.get('quantidade', 3) < len(row) else "1"
                try:
                    quantidade = int(float(quantidade_str)) if quantidade_str and quantidade_str.lower() not in ['nan', 'none', ''] else 1
                except Exception:
                    quantidade = 1

                # Limpar valores 'nan'
                ean = "" if ean.lower() in ['nan', 'none'] else ean
                codigo = "" if codigo.lower() in ['nan', 'none'] else codigo

                componente_data = {
                    'tipo_componente': tipo_componente,
                    'nome': nome,
                    'ean': ean,
                    'codigo': codigo,
                    'quantidade': quantidade,
                    'dados_extras': {}
                }

                componentes.append(componente_data)
                logger.debug(f"Componente especial extraído: {componente_data}")

        except Exception as e:
            logger.error(f"Erro ao extrair componentes especiais: {e}")
            raise

        return componentes

    def _detect_formulas(self, df: pd.DataFrame) -> bool:
        """Detecta se a aba contém fórmulas"""
        # Buscar por células que começam com '=' (fórmulas do Excel)
        for row_idx in range(min(20, len(df))):
            for col_idx in range(min(10, len(df.columns))):
                cell_value = str(df.iloc[row_idx, col_idx])
                if cell_value.startswith('='):
                    return True
        return False

    def _save_assentos(self, produto_id: int, assentos_data: List[Dict], sheet_name: str):
        """Salva assentos no banco"""
        for assento in assentos_data:
            try:
                self.db.add_assento(
                    produto_id=produto_id,
                    nome=assento['nome'],
                    modelo=assento['modelo'],
                    revestimento=assento['revestimento'],
                    ean=assento['ean'],
                    codigo=assento['codigo'],
                    quantidade=assento.get('quantidade', 1)
                )
                self.result.total_assentos += 1
            except Exception as e:
                error_msg = f"Erro ao salvar assento em '{sheet_name}': {e}"
                logger.error(error_msg)
                self.result.errors.append(error_msg)

    def _save_pes_bases(self, produto_id: int, pes_data: List[Dict], sheet_name: str, grupo: str):
        """Salva pés/bases no banco"""
        for pe_base in pes_data:
            try:
                self.db.add_pe_base(
                    produto_id=produto_id,
                    nome=pe_base['nome'],
                    ean=pe_base['ean'],
                    codigo=pe_base['codigo'],
                    quantidade=pe_base['quantidade'],
                    tipo_contexto=pe_base.get('tipo_contexto', ''),
                    grupo_pes=pe_base.get('grupo_pes', grupo),
                    marca=pe_base.get('marca', '')
                )
                self.result.total_pes_bases += 1
            except Exception as e:
                error_msg = f"Erro ao salvar pé/base em '{sheet_name}': {e}"
                logger.error(error_msg)
                self.result.errors.append(error_msg)

    def _save_componentes_especiais(self, produto_id: int, comp_data: List[Dict], sheet_name: str):
        """Salva componentes especiais no banco"""
        for componente in comp_data:
            try:
                self.db.add_componente_especial(
                    produto_id=produto_id,
                    tipo_componente=componente['tipo_componente'],
                    nome=componente['nome'],
                    ean=componente['ean'],
                    codigo=componente['codigo'],
                    quantidade=componente['quantidade'],
                    dados_extras=componente.get('dados_extras', {})
                )
                self.result.total_componentes_especiais += 1
            except Exception as e:
                error_msg = f"Erro ao salvar componente especial em '{sheet_name}': {e}"
                logger.error(error_msg)
                self.result.errors.append(error_msg)

    def _generate_combinations(self):
        """Gera combinações em lotes para evitar travamento"""
        try:
            logger.info("🔗 Gerando combinações automáticas em lotes...")

            produtos = self.db.list_produtos()

            for produto in produtos:
                assentos = self.db.list_assentos_by_produto(produto.id)
                pes_bases = self.db.list_pes_bases_by_produto(produto.id)

                total_combinations = len(assentos) * len(pes_bases)

                # ✅ LIMITE DE COMBINAÇÕES POR PRODUTO
                if total_combinations > 1000:
                    logger.warning(
                        f"⚠️ Produto '{produto.nome_aba}': {total_combinations} combinações possíveis - PULANDO geração automática")
                    logger.warning("    Use o botão 'Gerar Combinações' na interface para este produto específico")
                    continue

                logger.info(f"📊 Produto '{produto.nome_aba}': Gerando {total_combinations} combinações...")

                # Gerar em lotes de 100
                batch_size = 100
                combinations_added = 0

                for i, assento in enumerate(assentos):
                    for j, pe_base in enumerate(pes_bases):
                        try:
                            self.db.add_combinacao(assento.id, pe_base.id, produto.id)
                            combinations_added += 1

                            # Log de progresso a cada lote
                            if combinations_added % batch_size == 0:
                                logger.info(f"    Processadas {combinations_added}/{total_combinations} combinações...")

                        except Exception as e:
                            # Combinação já existe, ignorar
                            if "UNIQUE constraint failed" not in str(e):
                                logger.debug(f"Erro ao criar combinação: {e}")

                self.result.total_combinacoes += combinations_added
                logger.success(f"✅ Produto '{produto.nome_aba}': {combinations_added} combinações geradas")

            logger.info(f"✅ Total de combinações geradas: {self.result.total_combinacoes}")

        except Exception as e:
            error_msg = f"Erro ao gerar combinações: {e}"
            logger.error(error_msg)
            self.result.errors.append(error_msg)

    def get_import_preview(self, excel_path: Path) -> Dict:
        """Gera uma prévia da importação sem salvar no banco"""
        try:
            excel_file = pd.ExcelFile(excel_path)
            sheet_names = excel_file.sheet_names

            preview = {
                'total_sheets': len(sheet_names),
                'sheets': [],
                'estimated_products': len(sheet_names),
                'estimated_assentos': 0,
                'estimated_pes_bases': 0,
                'estimated_componentes_especiais': 0
            }

            for sheet_name in sheet_names[:5]:  # Analisar apenas as primeiras 5 abas para preview
                try:
                    df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
                    df_clean = df.fillna('')

                    structure = self._detect_sheet_structure(df_clean, sheet_name)

                    assentos_count = 0
                    pes_count = 0
                    especiais_count = 0

                    if structure.assentos_section:
                        assentos_data = self._extract_assentos_data_advanced(df_clean, structure.assentos_section, sheet_name)
                        assentos_count = len(assentos_data)

                    for pes_section in structure.pes_sections:
                        pes_data = self._extract_pes_data_advanced(df_clean, pes_section, sheet_name, 1)
                        pes_count += len(pes_data)

                    for comp_section in structure.componentes_especiais:
                        comp_data = self._extract_componentes_especiais(df_clean, comp_section, sheet_name)
                        especiais_count += len(comp_data)

                    preview['sheets'].append({
                        'name': sheet_name,
                        'structure_type': structure.structure_type,
                        'assentos': assentos_count,
                        'pes_bases': pes_count,
                        'componentes_especiais': especiais_count,
                        'combinacoes': assentos_count * pes_count
                    })

                    preview['estimated_assentos'] += assentos_count
                    preview['estimated_pes_bases'] += pes_count
                    preview['estimated_componentes_especiais'] += especiais_count

                except Exception as e:
                    logger.error(f"Erro ao analisar aba '{sheet_name}' para preview: {e}")

            if len(sheet_names) > 5:
                preview['sheets'].append({
                    'name': f'... e mais {len(sheet_names) - 5} abas',
                    'structure_type': '?',
                    'assentos': '?',
                    'pes_bases': '?',
                    'componentes_especiais': '?',
                    'combinacoes': '?'
                })

            return preview

        except Exception as e:
            logger.error(f"Erro ao gerar preview: {e}")
            return {'error': str(e)}