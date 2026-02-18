# services/costing_pricing_engine.py

import pandas as pd
import re
import math
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from loguru import logger


class CostPricingEngine:
    """Motor de precificação de custos baseado em regras de negócio"""

    # ✅ TCs válidos: inclui A+ e letras A..I
    VALID_TCS = {"A+", "A", "B", "C", "D", "E", "F", "G", "H", "I"}

    def __init__(self, mode: str = "Fábrica"):
        """
        Inicializa o motor de precificação.
        :param mode: Modo de operação ('Fábrica' ou 'Fornecedor').
        """
        self.mode = mode

        # Estrutura: {codigo: {tc: dados}}
        self.base_data: Dict[str, Dict[str, Dict[str, Any]]] = {}

        # Linhas específicas para modo Fábrica
        self.header_rows: Dict[str, int] = {
            'Poltrona': 57,
            'Namoradeira-Sofá': 24,
            'Puff-Banqueta': 40,
            'Cadeira': 25
        }
        logger.info(f"⚙️ CostPricingEngine inicializado no modo: '{self.mode}'")

    def _normalize_tc(self, tc_raw: Any) -> str:
        """Normaliza TC (ex.: 'a +' -> 'A+', ' d ' -> 'D')."""
        if tc_raw is None:
            return ""
        if isinstance(tc_raw, float) and pd.isna(tc_raw):
            return ""

        tc = str(tc_raw).strip().upper()
        tc = tc.replace(" ", "")       # "A +" -> "A+"
        tc = tc.replace("＋", "+")     # plus unicode -> '+'
        return tc

    def clean_currency_value(self, value: Any) -> float:
        """Limpar e converter valores monetários"""
        try:
            if pd.isna(value) or value == '' or value is None:
                return 0.0

            str_value = str(value).strip()

            if str_value == '' or str_value.lower() == 'nan':
                return 0.0

            # Remove R$, espaços e caracteres especiais
            cleaned = re.sub(r'[R$\s]', '', str_value)
            cleaned = cleaned.replace(',', '.')
            cleaned = re.sub(r'[^\d.]', '', cleaned)  # Garante que só números e ponto permaneçam

            if cleaned == '' or cleaned == '.':
                return 0.0

            return float(cleaned)

        except (ValueError, TypeError):
            return 0.0

    def load_base_data(self, base_file: Path) -> bool:
        """Carregar dados da planilha base (agora aceitando TC A+ e D/E/F etc.)"""
        try:
            if not base_file or not base_file.exists():
                logger.warning(f"❌ Caminho do arquivo base de custos inválido ou arquivo não encontrado: {base_file}")
                return False

            logger.info(f"📖 Carregando dados base de custos de: {base_file} no modo '{self.mode}'")

            excel_file = pd.ExcelFile(base_file, engine='openpyxl')

            for sheet_name in excel_file.sheet_names:
                # Determinar linha do cabeçalho baseado no modo
                if self.mode == "Fábrica" and sheet_name in self.header_rows:
                    header_row = self.header_rows[sheet_name] - 1
                else:
                    header_row = 1

                df = pd.read_excel(base_file, sheet_name=sheet_name, header=header_row, engine='openpyxl')

                if df.empty:
                    logger.debug(f"  ℹ️ Aba '{sheet_name}' está vazia, pulando.")
                    continue

                # Verificar colunas obrigatórias
                required_cols = ['TC', 'Código Fabricante', 'Custo For', 'Custo Fre', 'Preço De']
                if not all(col in df.columns for col in required_cols):
                    logger.warning(f"  ⚠️ Aba '{sheet_name}' não contém todas as colunas obrigatórias. Pulando.")
                    logger.debug(f"  Colunas necessárias: {required_cols}. Colunas encontradas: {df.columns.tolist()}")
                    continue

                # Verificar colunas opcionais
                has_ipi = 'IPI' in df.columns
                has_preco_por = 'Preço Por' in df.columns

                # Processar dados separando por TC (inclui A+)
                for _, row in df.iterrows():
                    codigo = str(row['Código Fabricante']).strip() if pd.notna(row['Código Fabricante']) else None
                    tc = self._normalize_tc(row['TC'])

                    if not codigo or codigo == 'nan':
                        continue

                    if not tc or tc not in self.VALID_TCS:
                        # Se quiser logar casos inválidos, descomente:
                        # logger.debug(f"  ❌ TC inválido/ignorado: codigo={codigo} tc='{tc}' aba='{sheet_name}'")
                        continue

                    if codigo not in self.base_data:
                        self.base_data[codigo] = {}

                    self.base_data[codigo][tc] = {
                        'custo_for': self.clean_currency_value(row['Custo For']),
                        'custo_fre': self.clean_currency_value(row['Custo Fre']),
                        'preco_de': self.clean_currency_value(row['Preço De']),
                        'preco_por': self.clean_currency_value(row['Preço Por']) if has_preco_por else 0.0,
                        'ipi': self.clean_currency_value(row['IPI']) if has_ipi else 0.0,
                        'aba': sheet_name,
                        'tc': tc
                    }

            excel_file.close()
            logger.success(f"✅ {len(self.base_data)} códigos de custos carregados com sucesso no modo '{self.mode}'.")
            return True

        except Exception as e:
            logger.error(f"❌ Erro ao carregar dados base de custos: {e}")
            return False

    def extract_fabric_line_and_code(self, full_code: str) -> Tuple[str, str]:
        """Extrair linha do tecido (TC) e código base - suporta A+ e letras A..I"""
        if not full_code:
            logger.debug("  ⚪ Código vazio → TC padrão 'C'")
            return "", "C"

        cleaned = str(full_code).strip().upper()
        cleaned = cleaned.replace(" ", "")
        cleaned = cleaned.replace("＋", "+")

        # ✅ Caso especial: sufixo A+ (2 caracteres)
        if cleaned.endswith("A+") and len(cleaned) > 2:
            base_code = cleaned[:-2]
            fabric_line = "A+"
            logger.debug(f"  🎯 TC VÁLIDO detectado: '{full_code}' → Base: '{base_code}' + TC: '{fabric_line}'")
            return base_code, fabric_line

        # ✅ Caso padrão: última letra A..I
        if len(cleaned) <= 1:
            logger.debug(f"  ⚪ Código muito curto: '{full_code}' → TC padrão 'C'")
            return cleaned, "C"

        last_char = cleaned[-1]
        valid_single_tcs = {t for t in self.VALID_TCS if len(t) == 1}  # A..I

        if last_char in valid_single_tcs:
            base_code = cleaned[:-1]
            fabric_line = last_char
            logger.debug(f"  🎯 TC VÁLIDO detectado: '{full_code}' → Base: '{base_code}' + TC: '{fabric_line}'")
            return base_code, fabric_line

        # Fallback
        logger.debug(f"  ❌ TC INVÁLIDO: '{full_code}' (sufixo não reconhecido) → Código completo + TC padrão 'C'")
        return cleaned, "C"

    def get_product_data_by_tc(self, code: str, tc: str) -> Optional[Dict[str, Any]]:
        """Obter dados de um produto específico por TC"""
        if code in self.base_data and tc in self.base_data[code]:
            return self.base_data[code][tc]
        return None

    def process_simple_code(self, code: str, fabric_line: str) -> Dict[str, Any]:
        """Processar código simples com busca por TC"""
        product_data = self.get_product_data_by_tc(code, fabric_line)

        if product_data:
            vr_custo_total = product_data['custo_for']
            custo_frete = product_data['custo_fre']
            custo_ipi = product_data['ipi']
            preco_de_venda = product_data['preco_de']
            preco_promocao = product_data['preco_por'] if product_data['preco_por'] > 0 else product_data['preco_de']

            return {
                'vr_custo_total': vr_custo_total,
                'custo_frete': custo_frete,
                'custo_ipi': custo_ipi,
                'preco_de_venda': preco_de_venda,
                'preco_promocao': preco_promocao,
                'found': True,
                'detail': (
                    f"Encontrado {code}(TC {fabric_line}): "
                    f"For R$ {vr_custo_total:.2f}, Fre R$ {custo_frete:.2f}"
                    + (f", IPI R$ {custo_ipi:.2f}" if custo_ipi > 0 else "")
                )
            }

        return {
            'vr_custo_total': 0.0,
            'custo_frete': 0.0,
            'custo_ipi': 0.0,
            'preco_de_venda': 0.0,
            'preco_promocao': 0.0,
            'found': False,
            'detail': f"Código não encontrado: {code} na linha TC {fabric_line}"
        }

    def process_multiplied_code(self, multiplier: float, code: str, fabric_line: str) -> Dict[str, Any]:
        """Processar código com multiplicador com TC"""
        simple_result = self.process_simple_code(code, fabric_line)

        if simple_result['found']:
            return {
                'vr_custo_total': simple_result['vr_custo_total'] * multiplier,
                'custo_frete': simple_result['custo_frete'] * multiplier,
                'custo_ipi': simple_result['custo_ipi'] * multiplier,
                'preco_de_venda': simple_result['preco_de_venda'] * multiplier,
                'preco_promocao': simple_result['preco_promocao'] * multiplier,
                'found': True,
                'detail': f"Multiplicado {multiplier}x: {simple_result['detail']}"
            }

        return simple_result

    def process_kit_with_bars(self, kit_str: str) -> Dict[str, Any]:
        """Processar kit com barras usando o TC do sufixo do código do kit (inclui A+)"""
        base_kit, fabric_line = self.extract_fabric_line_and_code(kit_str)
        components = base_kit.split('/')

        total_vr_custo_total = 0.0
        total_custo_frete = 0.0
        total_custo_ipi = 0.0
        total_preco_de_venda = 0.0
        total_preco_promocao = 0.0

        components_found = 0
        detail_parts = []

        for component in components:
            component = component.strip()
            if not component:
                continue

            multiplier = 1
            actual_code = component

            # Verificar se o componente tem multiplicador
            if '*' in component:
                parts = component.split('*')
                if len(parts) == 2:
                    try:
                        multiplier = float(parts[0])
                        actual_code = parts[1].strip()
                    except ValueError:
                        detail_parts.append(f"{component}: FORMATO MULTIPLICADOR INVÁLIDO")
                        continue

            # Processar cada componente do kit com o TC do kit
            simple_result = self.process_simple_code(actual_code, fabric_line)

            if simple_result['found']:
                total_vr_custo_total += simple_result['vr_custo_total'] * multiplier
                total_custo_frete += simple_result['custo_frete'] * multiplier
                total_custo_ipi += simple_result['custo_ipi'] * multiplier
                total_preco_de_venda += simple_result['preco_de_venda'] * multiplier
                total_preco_promocao += simple_result['preco_promocao'] * multiplier
                components_found += 1
                detail_parts.append(f"{component}(TC {fabric_line}): OK")
            else:
                detail_parts.append(f"{component}(TC {fabric_line}): NÃO ENCONTRADO")

        if components_found > 0:
            return {
                'vr_custo_total': total_vr_custo_total,
                'custo_frete': total_custo_frete,
                'custo_ipi': total_custo_ipi,
                'preco_de_venda': total_preco_de_venda,
                'preco_promocao': total_preco_promocao,
                'found': True,
                'detail': (
                    f"Kit TC {fabric_line} processado ({components_found}/{len(components)} encontrados): "
                    f"{' | '.join(detail_parts)}"
                )
            }

        return {
            'vr_custo_total': 0.0,
            'custo_frete': 0.0,
            'custo_ipi': 0.0,
            'preco_de_venda': 0.0,
            'preco_promocao': 0.0,
            'found': False,
            'detail': f"Nenhum componente encontrado no kit TC {fabric_line}: {kit_str}"
        }

    def process_code(self, code_str: Optional[str]) -> Dict[str, Any]:
        """Função unificada para processar qualquer tipo de código com TC (inclui A+)"""
        if not code_str or (isinstance(code_str, float) and pd.isna(code_str)) or str(code_str).strip() == '':
            return {
                'vr_custo_total': 0.0,
                'custo_frete': 0.0,
                'custo_ipi': 0.0,
                'preco_de_venda': 0.0,
                'preco_promocao': 0.0,
                'found': False,
                'detail': "Código vazio"
            }

        code_str_cleaned = str(code_str).strip()

        # 1) KIT
        if '/' in code_str_cleaned:
            return self.process_kit_with_bars(code_str_cleaned)

        # 2) MULTIPLICADOR
        if '*' in code_str_cleaned:
            parts = code_str_cleaned.split('*')
            if len(parts) == 2:
                try:
                    multiplier = float(parts[0])
                    base_code_with_line = parts[1].strip()
                    base_code, fabric_line = self.extract_fabric_line_and_code(base_code_with_line)
                    return self.process_multiplied_code(multiplier, base_code, fabric_line)
                except ValueError:
                    return {
                        'vr_custo_total': 0.0,
                        'custo_frete': 0.0,
                        'custo_ipi': 0.0,
                        'preco_de_venda': 0.0,
                        'preco_promocao': 0.0,
                        'found': False,
                        'detail': f"Formato de multiplicador inválido: {code_str_cleaned}"
                    }

        # 3) CÓDIGO SIMPLES
        base_code, fabric_line = self.extract_fabric_line_and_code(code_str_cleaned)
        return self.process_simple_code(base_code, fabric_line)

    def apply_90_cents_rule(self, price: float) -> float:
        """Aplicar regra dos ,90 centavos para preços"""
        if pd.isna(price) or price <= 0:
            return 0.0

        integer_part = math.floor(float(price))
        final_price = integer_part + 0.90
        return final_price