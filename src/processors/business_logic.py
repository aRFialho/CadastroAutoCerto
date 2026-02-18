"""Lógicas de negócio para processamento de produtos"""

from typing import List, Dict, Tuple, Optional, Callable, Any
from pathlib import Path # ✅ ESTA LINHA DEVE ESTAR PRESENTE
from datetime import datetime
import re
import math
import html
import unicodedata

from ..core.models import (
    ProductOrigin,
    ProductDestination, VariationData, LojaWebData, KitData,
    ProcessingResult, AppConfig
)
from ..utils.logger import get_logger
from .excel_reader import ExcelReader
from .excel_writer import ExcelWriter
logger = get_logger("business_logic")

class ProductProcessor:
    """Processador principal de produtos"""

    def __init__(self, config: AppConfig):
        """Inicializa o processador.

        ⚠️ Importante: o módulo de fornecedores (SQLite) é **opcional**.
        Se o Python não tiver sqlite3 ou se o arquivo do banco não existir,
        o app não pode quebrar — apenas marca o recurso como indisponível.
        """

        self.config = config
        self.reader = ExcelReader()
        self.writer = ExcelWriter()

        # =========================
        # ✅ Fornecedores (SQLite) — opcional / fail-safe
        # =========================
        self.supplier_db = None
        self.supplier_system_available = False
        self.supplier_status_message = "Indisponível"

        self._init_supplier_database_safe()

        # ✅ INICIALIZAR MOTOR DE PRECIFICAÇÃO SE HABILITADO

        self.cost_pricing_engine = None
        if config.enable_auto_pricing and config.cost_file_path:
            try:
                from src.services.costing_pricing_engine import CostPricingEngine
                self.cost_pricing_engine = CostPricingEngine(mode=config.pricing_mode.value)
                logger.info(f"🏷️ Motor de precificação inicializado no modo: {config.pricing_mode.value}")
            except Exception as e:
                logger.error(f"❌ Erro ao inicializar motor de precificação: {e}")
                self.cost_pricing_engine = None
        else:
            logger.info("ℹ️ Precificação automática desabilitada")

        # ✅ INICIALIZAR CATEGORY MANAGER PARA ESTA CLASSE (BUSINESS LOGIC)
        self.category_manager = None
        self.init_category_manager()


    # =========================
    # ✅ Fornecedores (SQLite) — helpers
    # =========================
    def _init_supplier_database_safe(self) -> None:
        """Inicializa SupplierDatabase com tolerância a falhas.

        Regras:
        - Se sqlite3 não existir no Python, não quebra.
        - Se o arquivo do banco não existir, não quebra.
        - Se o banco não abrir, não quebra.
        """
        try:
            # sqlite3 pode não existir em builds custom
            import sqlite3  # noqa: F401
        except Exception as e:
            self.supplier_status_message = f"Indisponível (sqlite3 ausente: {e})"
            logger.warning(f"⚠️ Sistema de fornecedores indisponível: sqlite3 ausente ({e})")
            self.supplier_db = None
            self.supplier_system_available = False
            return

        try:
            from ..core.supplier_database import SupplierDatabase  # import tardio (fail-safe)
        except Exception as e:
            self.supplier_status_message = f"Indisponível (módulo SupplierDatabase: {e})"
            logger.warning(f"⚠️ Sistema de fornecedores indisponível: não consegui importar SupplierDatabase ({e})")
            self.supplier_db = None
            self.supplier_system_available = False
            return

        # garantir pasta de output
        try:
            if getattr(self.config, "output_dir", None):
                Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        # candidatos de caminho (ordem: config explícita → output_dir → outputs)
        candidates = []
        cfg_path = getattr(self.config, "suppliers_db_path", None) or getattr(self.config, "supplier_db_path", None)
        if cfg_path:
            candidates.append(Path(cfg_path))
        if getattr(self.config, "output_dir", None):
            candidates.append(Path(self.config.output_dir) / "suppliers.db")
        candidates.append(Path("outputs") / "suppliers.db")

        # escolhe o primeiro existente; se nenhum existir, escolhe o default em output_dir (para futuro)
        db_path = None
        for p in candidates:
            try:
                if p and p.exists():
                    db_path = p
                    break
            except Exception:
                continue
        if db_path is None:
            db_path = candidates[1] if len(candidates) > 1 else candidates[0]

        # se não existe, marca indisponível (sem quebrar)
        if not db_path.exists():
            self.supplier_status_message = f"Indisponível (arquivo não encontrado: {db_path})"
            logger.warning(f"⚠️ Banco de fornecedores não encontrado: {db_path} (seguindo sem fornecedores)")
            self.supplier_db = None
            self.supplier_system_available = False
            return

        # tenta abrir (teste rápido)
        try:
            import sqlite3
            with sqlite3.connect(db_path) as conn:
                cur = conn.cursor()
                # tabela pode não existir (banco vazio/corrompido)
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='suppliers'")
                has_table = cur.fetchone() is not None
                if not has_table:
                    self.supplier_status_message = f"Indisponível (tabela 'suppliers' não existe em {db_path})"
                    logger.warning(f"⚠️ Banco de fornecedores inválido: tabela 'suppliers' não existe ({db_path})")
                    self.supplier_db = None
                    self.supplier_system_available = False
                    return
        except Exception as e:
            self.supplier_status_message = f"Indisponível (falha ao abrir {db_path}: {e})"
            logger.warning(f"⚠️ Não consegui abrir o banco de fornecedores ({db_path}): {e}")
            self.supplier_db = None
            self.supplier_system_available = False
            return

        # inicializa wrapper
        try:
            self.supplier_db = SupplierDatabase(db_path)
            self.supplier_system_available = True
            self.supplier_status_message = f"Disponível ({db_path})"
            try:
                test = self.supplier_db.get_all_suppliers()
                logger.info(f"🗄️ Fornecedores carregados: {len(test)} | DB: {db_path}")
            except Exception:
                logger.info(f"🗄️ Banco de fornecedores conectado | DB: {db_path}")
        except Exception as e:
            self.supplier_status_message = f"Indisponível (erro ao inicializar: {e})"
            logger.warning(f"⚠️ Falha ao inicializar SupplierDatabase ({db_path}): {e}")
            self.supplier_db = None
            self.supplier_system_available = False

    def is_supplier_db_available(self) -> bool:
        return bool(self.supplier_system_available and self.supplier_db)


    # ===========================
    # SISTEMA DE CUBAGEM AVANÇADO
    # ===========================

    def _strip_html_tags(self, raw_html: str) -> str:
        """Remove tags HTML e normaliza espaços."""
        if not raw_html:
            return ""
        text = re.sub(r"<[^>]+>", " ", raw_html, flags=re.IGNORECASE | re.MULTILINE)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _parse_number_pt(self, num_str: str) -> float:
        """
        Converte números no formato PT/BR ou misto para float.
        Exemplos aceitos: '1.234,56', '1234,56', '1,234.56', '1234.56', '123'
        """
        s = num_str.strip()
        # Remove espaços finos e similares
        s = s.replace("\u2009", "").replace("\u00A0", " ").strip()

        # Se há vírgula e ponto, detecta qual é decimal pelo último separador
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                # vírgula é decimal -> remove pontos (milhar), troca vírgula por ponto
                s = s.replace(".", "").replace(",", ".")
            else:
                # ponto é decimal -> remove vírgulas (milhar)
                s = s.replace(",", "")
        else:
            # Só vírgula -> vírgula é decimal
            if "," in s:
                s = s.replace(".", "").replace(",", ".")
            # Só ponto -> já está ok
        return float(s)

    def _parse_caixas_from_descricao(self, descricao_html: str) -> List[Dict[str, float]]:
        """
        Extrai caixas no padrão:
        'Caixa 1: 143 x 83 x 73 cm' (variações: 'Caixa 1 -', 'x'/'×', 'cm' após cada número etc).
        Retorna lista de dicionários: [{'altura_cm': A, 'largura_cm': L, 'profundidade_cm': P}, ...]
        """
        text = self._strip_html_tags(descricao_html)

        # Permitir 'cm' após cada número e variações do 'x' (x, X, ×)
        # Aceitar separadores e espaços variados
        padrao = re.compile(
            r"Caixa\s*\d+\s*[:\-]?\s*"
            r"([\d\.,]+)\s*(?:cm)?\s*[xX×]\s*"
            r"([\d\.,]+)\s*(?:cm)?\s*[xX×]\s*"
            r"([\d\.,]+)\s*(?:cm)?",
            flags=re.IGNORECASE
        )

        caixas = []
        for m in padrao.finditer(text):
            a_str, l_str, p_str = m.group(1), m.group(2), m.group(3)
            try:
                a = self._parse_number_pt(a_str)
                L = self._parse_number_pt(l_str)
                p = self._parse_number_pt(p_str)
            except ValueError:
                continue
            # A x L x P mapeados diretamente; não reordenamos
            caixas.append({
                "altura_cm": a,
                "largura_cm": L,
                "profundidade_cm": p
            })

        return caixas

    def _parse_peso_total_kg(self, descricao_html: str) -> Optional[float]:
        """
        Extrai 'Peso total: XX kg' da descrição HTML.
        Busca preferencialmente após as informações das caixas/medidas.
        Retorna float (kg) ou None se não encontrado.
        """
        text = self._strip_html_tags(descricao_html)

        # ✅ ESTRATÉGIA 1: Buscar peso após "Medida das Embalagens" ou similar
        # Procura por seções que contenham medidas e depois peso
        secoes_medidas = [
            r"Medida\s+das?\s+Embalagens?[:\-]?(.+?)(?=\n\n|\n[A-Z]|$)",
            r"Medidas?\s+das?\s+Caixas?[:\-]?(.+?)(?=\n\n|\n[A-Z]|$)",
        ]

        for padrao_secao in secoes_medidas:
            match_secao = re.search(padrao_secao, text, flags=re.IGNORECASE | re.DOTALL)
            if match_secao:
                secao_medidas = match_secao.group(1)
                logger.info(f"  📏 Seção de medidas encontrada: '{secao_medidas[:100]}...'")

                # Busca peso dentro desta seção
                padroes_peso = [
                    r"Peso\s*total\s*(?:aproximado)?\s*[:\-]?\s*([\d\.,]+)\s*kg",
                    r"Peso\s*[:\-]?\s*([\d\.,]+)\s*kg",
                    r"(\d+(?:[,\.]\d+)?)\s*kg",  # Padrão mais simples
                ]

                for pat_peso in padroes_peso:
                    m = re.search(pat_peso, secao_medidas, flags=re.IGNORECASE)
                    if m:
                        try:
                            peso = self._parse_number_pt(m.group(1))
                            logger.success(f"  ⚖️ Peso encontrado na seção de medidas: {peso} kg")
                            return peso
                        except ValueError:
                            continue

        # ✅ ESTRATÉGIA 2: Busca geral se não encontrou na seção específica
        logger.info("  🔍 Peso não encontrado em seção específica, buscando globalmente...")

        padroes_gerais = [
            r"Peso\s*total\s*(?:aproximado)?\s*[:\-]?\s*([\d\.,]+)\s*kg",
            r"Peso\s*[:\-]?\s*([\d\.,]+)\s*kg",
            r"(\d+(?:[,\.]\d+)?)\s*kg",  # Último recurso
        ]

        for pat in padroes_gerais:
            m = re.search(pat, text, flags=re.IGNORECASE)
            if m:
                try:
                    peso = self._parse_number_pt(m.group(1))
                    logger.info(f"  ⚖️ Peso encontrado globalmente: {peso} kg")
                    return peso
                except ValueError:
                    continue

        logger.warning("  ⚠️ Peso total não encontrado na descrição")
        return None

    def _round_value(self, value: float, metodo: str = "ceil", casas: int = 0) -> float:
        """Arredonda valores conforme método especificado"""
        metodo = (metodo or "ceil").lower()
        if metodo == "ceil":
            return float(math.ceil(value)) if casas == 0 else math.ceil(value * (10 ** casas)) / (10 ** casas)
        elif metodo == "floor":
            return float(math.floor(value)) if casas == 0 else math.floor(value * (10 ** casas)) / (10 ** casas)
        elif metodo == "round":
            return round(value, casas)
        else:
            # default seguro
            return float(math.ceil(value)) if casas == 0 else math.ceil(value * (10 ** casas)) / (10 ** casas)

    def _cubagem_consolidada_quadrada(self,
                                      caixas: List[Dict[str, float]],
                                      comprimento_fixo_cm: float = 101.0,
                                      arredondamento: str = "ceil",
                                      casas_decimais: int = 0,
                                      folga_cm: float = 0.0,
                                      aplicar_folga_no_comprimento: bool = False
                                      ) -> Dict[str, Any]:
        """
        Consolida as caixas em UMA embalagem:
        - Comprimento fixo = 101 cm (padrão),
        - Seção quadrada equivalente: Altura = Largura = sqrt(Volume_total / comprimento_fixo),
        - Arredondamento (ceil por padrão) ao cm,
        - Folga opcional.
        """
        if comprimento_fixo_cm <= 0:
            raise ValueError("comprimento_fixo_cm deve ser > 0.")

        # Volume total em cm³
        vtot_cm3 = 0.0
        detalhado = []
        for c in caixas:
            a, L, p = c["altura_cm"], c["largura_cm"], c["profundidade_cm"]
            v_cm3 = a * L * p
            detalhado.append({
                "altura_cm": a,
                "largura_cm": L,
                "comprimento_cm": p,
                "volume_cm3": v_cm3,
                "volume_m3": v_cm3 / 1_000_000.0
            })
            vtot_cm3 += v_cm3

        # Área de seção requerida (cm²)
        secao_cm2 = vtot_cm3 / float(comprimento_fixo_cm)
        # Lado da seção quadrada equivalente
        lado_cm = math.sqrt(secao_cm2)

        # Aplicar folga (por padrão apenas em Altura/Largura)
        altura_calc = lado_cm + (folga_cm or 0.0)
        largura_calc = lado_cm + (folga_cm or 0.0)
        comprimento_calc = float(comprimento_fixo_cm) + (folga_cm if aplicar_folga_no_comprimento else 0.0)

        # Arredondamento
        altura_final = self._round_value(altura_calc, arredondamento, casas_decimais)
        largura_final = self._round_value(largura_calc, arredondamento, casas_decimais)
        comprimento_final = self._round_value(comprimento_calc, arredondamento, casas_decimais)

        # Volumes (antes e depois do arredondamento)
        vtot_m3 = vtot_cm3 / 1_000_000.0
        vembalagem_m3 = (altura_final * largura_final * comprimento_final) / 1_000_000.0

        return {
            "caixas_det": detalhado,
            "volume_total_m3": vtot_m3,
            "comprimento_fixo_cm": comprimento_fixo_cm,
            "secao_quadrada_cm": lado_cm,
            "altura_cm": altura_final,
            "largura_cm": largura_final,
            "comprimento_cm": comprimento_final,
            "volume_embalagem_m3": vembalagem_m3,
            "arredondamento": arredondamento,
            "casas_decimais": casas_decimais,
            "folga_cm": folga_cm,
            "aplicar_folga_no_comprimento": aplicar_folga_no_comprimento
        }

    def _calcular_peso_cubado(self, volume_total_m3: float, fator_cubagem_kg_m3: float = 300.0) -> float:
        """Calcula peso cubado"""
        if fator_cubagem_kg_m3 <= 0:
            raise ValueError("fator_cubagem_kg_m3 deve ser > 0.")
        return volume_total_m3 * fator_cubagem_kg_m3

    def _processar_descricao_para_produto(self,
                                          descricao_html: str,
                                          ean: str,
                                          comprimento_fixo_cm: float = 101.0,
                                          arredondamento: str = "ceil",
                                          casas_decimais: int = 0,
                                          folga_cm: float = 0.0,
                                          aplicar_folga_no_comprimento: bool = False,
                                          fator_cubagem_kg_m3: float = 300.0
                                          ) -> Dict[str, Any]:
        """
        Pipeline completo:
        - Extrai caixas, peso total e quantidade de volumes,
        - **NOVA LÓGICA:** Se for apenas 1 volume, usa as medidas diretas da caixa.
          Senão, consolida com comprimento fixo = 101 cm e seção quadrada equivalente.
        - Calcula peso cubado e peso taxável,
        - Retorna campos prontos para gravar na aba 'PRODUTO'.
        """

        logger.info(f"🔍 === PROCESSAMENTO AVANÇADO DE CUBAGEM - EAN: {ean} ===")

        if not descricao_html:
            logger.info("  ℹ️ Sem descrição HTML - usando valores padrão")
            return {
                "altura_cm": 0.0,
                "largura_cm": 0.0,
                "comprimento_cm": 0.0,
                "peso_bruto_kg": 0.0,
                "peso_liquido_kg": 0.0,
                "peso_cubado_kg": 0.0,
                "volume_total_m3": 0.0,
                "caixas_encontradas": 0,
                "qtde_volume": None
            }

        # ✅ EXTRAIR QUANTIDADE DE VOLUMES
        qtde_volumes = self._parse_quantidade_volumes_inteligente(descricao_html)

        # ✅ EXTRAIR CAIXAS
        caixas = self._parse_caixas_from_descricao(descricao_html)

        # ✅ EXTRAIR PESO TOTAL
        peso_total_kg = self._parse_peso_total_kg(descricao_html)
        if peso_total_kg:
            logger.success(f"  ⚖️ Peso total encontrado: {peso_total_kg} kg")
        else:
            logger.warning("  ⚠️ Peso total não encontrado na descrição")

        # --- NOVA LÓGICA DE CUBAGEM CONDICIONAL: 1 VOLUME vs MÚLTIPLOS VOLUMES ---
        # Cenário 1: Apenas 1 volume e 1 caixa detectada, OU se não detectou qtde_volumes mas só achou 1 caixa.
        if (qtde_volumes is None or qtde_volumes == 1) and len(caixas) == 1:
            logger.info("  📦 DETECTADO: APENAS 1 VOLUME OU 1 CAIXA NA DESCRIÇÃO. USANDO MEDIDAS DIRETAS DA CAIXA.")
            single_box = caixas[0]
            altura_final = single_box["altura_cm"]
            largura_final = single_box["largura_cm"]
            comprimento_final = single_box["profundidade_cm"]  # Assumindo profundidade é o comprimento

            # Calcula o volume da única caixa
            volume_m3_single_box = (altura_final * largura_final * comprimento_final) / 1_000_000.0

            # Calcula o peso cubado para essa única caixa
            peso_cubado_kg = self._calcular_peso_cubado(
                volume_m3_single_box,
                fator_cubagem_kg_m3=fator_cubagem_kg_m3
            )
            # Peso taxável é o maior entre o peso total e o peso cubado
            peso_taxavel_kg = max(peso_total_kg or 0.0, peso_cubado_kg)

            logger.success("  🎯 CUBAGEM DIRETA CALCULADA COM SUCESSO (1 VOLUME):")
            logger.success(f"    - Altura: {altura_final} cm")
            logger.success(f"    - Largura: {largura_final} cm")
            logger.success(f"    - Comprimento: {comprimento_final} cm")
            logger.success(f"    - Peso cubado: {peso_cubado_kg:.2f} kg")
            logger.success(f"    - Peso taxável: {peso_taxavel_kg:.2f} kg")
            logger.success("    - Qtde Volume: 1")

            return {
                "altura_cm": altura_final,
                "largura_cm": largura_final,
                "comprimento_cm": comprimento_final,
                "peso_bruto_kg": peso_total_kg or 0.0,
                "peso_liquido_kg": peso_total_kg or 0.0,
                "peso_cubado_kg": peso_cubado_kg,
                "peso_taxavel_kg": peso_taxavel_kg,
                "volume_total_m3": volume_m3_single_box,
                "volume_embalagem_m3": volume_m3_single_box,  # Para caixa única, o volume da embalagem é o mesmo
                "caixas_encontradas": 1,
                "qtde_volume": 1,  # Explicitamente 1 volume neste cenário
                "consolidado_completo": {  # Informações mínimas para consistência
                    "altura_cm": altura_final,
                    "largura_cm": largura_final,
                    "comprimento_cm": comprimento_final,
                    "volume_total_m3": volume_m3_single_box,
                    "volume_embalagem_m3": volume_m3_single_box
                }
            }

        # Cenário 2: Nenhuma caixa detectada. Retorna valores padrão (0s).
        if not caixas:
            logger.warning("  ⚠️ Nenhuma caixa encontrada na descrição. Retornando valores padrão.")
            return {
                "altura_cm": 0.0,
                "largura_cm": 0.0,
                "comprimento_cm": 0.0,
                "peso_bruto_kg": peso_total_kg or 0.0,
                "peso_liquido_kg": peso_total_kg or 0.0,
                "peso_cubado_kg": 0.0,
                "volume_total_m3": 0.0,
                "caixas_encontradas": 0,
                "qtde_volume": qtde_volumes  # Mantém a quantidade detectada originalmente, ou None
            }

        # Cenário 3: Múltiplos volumes (qtde_volumes > 1) ou múltiplas caixas (len(caixas) > 1)
        # Processar como antes, consolidando todas as caixas.
        logger.info(
            f"  📦 DETECTADO: MÚLTIPLOS VOLUMES ({qtde_volumes if qtde_volumes is not None else len(caixas)} volumes ou caixas). PROCESSANDO CUBAGEM CONSOLIDADA.")
        if qtde_volumes and len(caixas) != qtde_volumes:
            logger.warning(f"  ⚠️ ATENÇÃO: Volumes detectados ({qtde_volumes}) ≠ Caixas encontradas ({len(caixas)})")
            logger.warning(f"    - Usando quantidade de volumes: {qtde_volumes}")
            logger.warning(f"    - Caixas processadas: {len(caixas)}")

        try:
            # ✅ CONSOLIDAÇÃO COM CUBAGEM (lógica existente para múltiplos volumes)
            consolidado = self._cubagem_consolidada_quadrada(
                caixas=caixas,
                comprimento_fixo_cm=comprimento_fixo_cm,
                arredondamento=arredondamento,
                casas_decimais=casas_decimais,
                folga_cm=folga_cm,
                aplicar_folga_no_comprimento=aplicar_folga_no_comprimento
            )

            # ✅ PESO CUBADO
            peso_cubado_kg = self._calcular_peso_cubado(
                consolidado["volume_total_m3"],
                fator_cubagem_kg_m3=fator_cubagem_kg_m3
            )

            # ✅ PESO TAXÁVEL
            if peso_total_kg is not None:
                peso_taxavel_kg = max(peso_total_kg, peso_cubado_kg)
            else:
                peso_taxavel_kg = peso_cubado_kg

            logger.success("  🎯 CUBAGEM CONSOLIDADA CALCULADA COM SUCESSO:")
            logger.success(f"    - Volume total: {consolidado['volume_total_m3']:.6f} m³")
            logger.success(f"    - Seção quadrada: {consolidado['secao_quadrada_cm']:.2f} cm")
            logger.success(f"    - Altura final: {consolidado['altura_cm']} cm")
            logger.success(f"    - Largura final: {consolidado['largura_cm']} cm")
            logger.success(f"    - Comprimento final: {consolidado['comprimento_cm']} cm (fixo)")
            logger.success(f"    - Peso cubado: {peso_cubado_kg:.2f} kg")
            logger.success(f"    - Peso taxável: {peso_taxavel_kg:.2f} kg")
            logger.success(f"    - Qtde Volume: {qtde_volumes if qtde_volumes is not None else len(caixas)}")

            return {
                "altura_cm": consolidado["altura_cm"],
                "largura_cm": consolidado["largura_cm"],
                "comprimento_cm": consolidado["comprimento_cm"],
                "peso_bruto_kg": peso_total_kg or 0.0,
                "peso_liquido_kg": peso_total_kg or 0.0,
                "peso_cubado_kg": peso_cubado_kg,
                "peso_taxavel_kg": peso_taxavel_kg,
                "volume_total_m3": consolidado["volume_total_m3"],
                "volume_embalagem_m3": consolidado["volume_embalagem_m3"],
                "caixas_encontradas": len(caixas),
                "qtde_volume": qtde_volumes if qtde_volumes is not None else len(caixas),
                # Usa a qtde detectada ou o número de caixas encontradas
                "consolidado_completo": consolidado
            }

        except Exception as e:
            logger.error(f"  ❌ Erro no cálculo de cubagem: {e}")
            return {
                "altura_cm": 0.0,
                "largura_cm": 0.0,
                "comprimento_cm": 0.0,
                "peso_bruto_kg": peso_total_kg or 0.0,
                "peso_liquido_kg": peso_total_kg or 0.0,
                "peso_cubado_kg": 0.0,
                "volume_total_m3": 0.0,
                "caixas_encontradas": len(caixas),
                "qtde_volume": qtde_volumes if qtde_volumes is not None else len(caixas)
                # Usa a qtde detectada ou o número de caixas encontradas
            }

    def _parse_quantidade_volumes_inteligente(self, descricao_html: str) -> Optional[int]:
        """
        Extrai quantidade de volumes de forma inteligente:
        1. Primeiro tenta encontrar declaração explícita
        2. Se não encontrar ou houver conflito, conta as caixas listadas
        3. Retorna a quantidade mais confiável
        """
        text = self._strip_html_tags(descricao_html)

        logger.info("     === DETECÇÃO INTELIGENTE DE VOLUMES ===")

        # ✅ ESTRATÉGIA 1: Buscar declaração explícita
        padroes_declaracao = [
            r"Quantidade\s+de\s+Volumes?\s*[:\-]?\s*(\d+)\s+Caixas?",
            r"Quantidade\s+de\s+Volumes?\s*[:\-]?\s*(\d+)\s+Volumes?",
            r"Qtde?\s+de?\s+Volumes?\s*[:\-]?\s*(\d+)\s+Caixas?",
            r"Qtde?\s+Volumes?\s*[:\-]?\s*(\d+)\s+Caixas?",
        ]

        quantidade_declarada = None
        for pat in padroes_declaracao:
            m = re.search(pat, text, flags=re.IGNORECASE)
            if m:
                quantidade_declarada = int(m.group(1))
                logger.info(f"    📋 Quantidade DECLARADA encontrada: {quantidade_declarada}")
                break

        # ✅ ESTRATÉGIA 2: Contar caixas listadas nas medidas
        padroes_caixas = [
            r"Caixa\s*(\d+)\s*[:\-]",  # "Caixa 1:", "Caixa 2:", etc.
        ]

        caixas_encontradas = set()
        for pat in padroes_caixas:
            matches = re.finditer(pat, text, flags=re.IGNORECASE)
            for match in matches:
                numero_caixa = int(match.group(1))
                caixas_encontradas.add(numero_caixa)

        quantidade_contada = len(caixas_encontradas) if caixas_encontradas else None

        if quantidade_declarada and quantidade_contada:
            if quantidade_declarada == quantidade_contada:
                logger.success(f"    ✅ CONSISTENTE: Declarado={quantidade_declarada}, Contado={quantidade_contada}")
                return quantidade_declarada
            else:
                logger.warning(f"    ⚠️ CONFLITO: Declarado={quantidade_declarada}, Contado={quantidade_contada}")
                logger.warning(f"    🎯 USANDO quantidade CONTADA (mais confiável): {quantidade_contada}")
                return quantidade_contada
        elif quantidade_contada:
            logger.info(f"    📦 Usando quantidade CONTADA: {quantidade_contada}")
            return quantidade_contada
        elif quantidade_declarada:
            logger.info(f"    📋 Usando quantidade DECLARADA: {quantidade_declarada}")
            return quantidade_declarada
        else:
            logger.info("    ❌ Nenhuma quantidade encontrada")
            return None

    # ===========================
    # FIM DO SISTEMA DE CUBAGEM
    # ===========================

    async def process_products(
            self,
            origin_file: Path,
            sheet_name: str = "Produtos",
            progress_callback: Optional[Callable[[float], None]] = None,
            status_callback: Optional[Callable[[str], None]] = None,
            send_email: bool = True
    ) -> ProcessingResult:
        """Processa produtos da origem para destino"""

        start_time = datetime.now()

        try:
            # Callback de status
            def update_status(msg: str):
                logger.info(msg)
                if status_callback:
                    status_callback(msg)

            def update_progress(value: float):
                if progress_callback:
                    progress_callback(value)

            update_status("🔄 Iniciando processamento...")
            update_progress(0.1)

            # 1. Carregar dados de origem
            update_status("📖 Carregando produtos da origem...")
            products = self.reader.read_products(origin_file, sheet_name)
            if not products:
                end_time = datetime.now()
                return ProcessingResult(
                    success=False,
                    total_errors=1,
                    processing_time=(end_time - start_time).total_seconds(),
                    errors=["Nenhum produto encontrado na planilha de origem"]
                )

            update_progress(0.3)

            # 1.5. Carregar dados de custo se precificação habilitada
            if self.config.enable_auto_pricing and self.config.cost_file_path:
                update_status("💰 Carregando dados de custos...")

                try:
                    # garante Path
                    cost_path = Path(self.config.cost_file_path)

                    # cria engine se ainda não existir
                    if self.cost_pricing_engine is None:
                        from ..services.costing_pricing_engine import CostPricingEngine
                        self.cost_pricing_engine = CostPricingEngine(mode=self.config.pricing_mode.value)

                    cost_loaded = self.cost_pricing_engine.load_base_data(cost_path)

                    if cost_loaded:
                        logger.success("✅ Dados de custo carregados com sucesso")
                    else:
                        logger.warning("⚠️ Falha ao carregar dados de custo - precificação será pulada")
                        self.cost_pricing_engine = None

                except Exception as e:
                    logger.error(f"❌ Erro ao carregar dados de custo: {e}")
                    self.cost_pricing_engine = None
            else:
                logger.info("ℹ️ Precificação desabilitada ou planilha de custos não definida")
                self.cost_pricing_engine = None

            update_progress(0.35)

            # ✅ VERIFICAR CATEGORY MANAGER
            update_status("📂 Verificando CategoryManager...")
            if not self.category_manager:
                self.init_category_manager()

            if self.category_manager:
                total_cats = len(self.category_manager.categories) if hasattr(self.category_manager,
                                                                              'categories') else 0
                logger.success(f"✅ CategoryManager ativo com {total_cats} categorias principais")
            else:
                logger.warning("⚠️ CategoryManager não disponível - categorias não serão preenchidas")

            update_progress(0.4)

            # ✅ NOVA LÓGICA: SEPARAR PRODUTOS NORMAIS DE PAIS VAZIOS
            update_status("⚙️ Identificando pais vazios...")

            products_for_produto_lojaweb_kit = []
            parents_for_variacao_only: Dict[str, ProductOrigin] = {}

            for p in products:
                if self.should_skip_empty_parent(p):
                    # Este é um pai vazio, não vai para PRODUTO/LOJA WEB/KIT, mas é essencial para VARIACAO
                    if p.complemento_produto:  # ✅ USAR COMPLEMENTO_PRODUTO COMO CHAVE
                        parents_for_variacao_only[str(p.complemento_produto).strip()] = p
                        logger.info(
                            f"🔄 Pai vazio identificado para VARIACAO: EAN={p.ean}, Complemento='{p.complemento_produto}'")
                    else:
                        logger.warning(
                            f"⚠️ Pai vazio (EAN: {p.ean}) sem COMPLEMENTO_PRODUTO definido. Não será considerado para agrupamento de variações.")
                else:
                    # Este produto deve ir para as abas PRODUTO/LOJA WEB/KIT
                    products_for_produto_lojaweb_kit.append(p)

            logger.info(f"📊 Total de produtos originais: {len(products)}")
            logger.info(f"📦 Pais vazios identificados (apenas para VARIACAO): {len(parents_for_variacao_only)}")
            logger.info(f"📋 Produtos para PRODUTO/LOJA WEB/KIT: {len(products_for_produto_lojaweb_kit)}")

            # 3. Processar cada tipo de dados
            update_status("⚙️ Processando dados dos produtos...")

            # Produtos principais (USA A LISTA ORIGINAL para detectar separadores)
            produtos_dest = self._process_produtos(products)  # ✅ LISTA ORIGINAL
            if produtos_dest is None:
                produtos_dest = []

            update_progress(0.6)

            # Variações (usa a lista COMPLETA de produtos ORIGINAIS + pais vazios identificados)
            variacoes_dest = self._process_variacoes(products, parents_for_variacao_only)
            if variacoes_dest is None:
                variacoes_dest = []

            update_progress(0.7)

            # Loja Web (APENAS produtos que NÃO são pais vazios)
            lojaweb_dest = self._process_loja_web(products_for_produto_lojaweb_kit)
            if lojaweb_dest is None:
                lojaweb_dest = []

            update_progress(0.8)

            # Kits (APENAS produtos que NÃO são pais vazios)
            kits_dest = self._process_kits(products_for_produto_lojaweb_kit)
            if kits_dest is None:
                kits_dest = []

            update_progress(0.9)

            # 4. Gerar arquivo de saída
            update_status("💾 Gerando arquivo de saída...")
            output_file = self._generate_output_file(
                produtos_dest, variacoes_dest, lojaweb_dest, kits_dest, origin_file
            )

            # Calcular tempo antes do e-mail
            end_time = datetime.now()
            processing_time = (end_time - start_time).total_seconds()

            # Criar resultado com todos os dados
            result = ProcessingResult(
                success=True,
                total_products=len(produtos_dest),
                total_variations=len(variacoes_dest),
                total_kits=len(kits_dest),
                total_errors=0,
                processing_time=processing_time,
                output_file=output_file,
                errors=[],
                warnings=[]
            )

            # 5. Envio de e-mail
            if send_email and self.config.email:
                try:
                    update_status("📧 Enviando relatório por e-mail...")

                    from ..services.email_sender import EmailSender
                    email_sender = EmailSender(self.config.email)

                    await email_sender.send_processing_report(result, origin_file)
                    update_status("✅ E-mail enviado com sucesso!")

                except Exception as email_error:
                    logger.warning(f"⚠️ Erro ao enviar e-mail: {email_error}")
                    result.warnings.append(f"E-mail não enviado: {email_error}")

            update_progress(1.0)
            update_status(f"✅ Processamento concluído! Arquivo salvo: {output_file.name}")

            logger.success(f"Processamento concluído em {result.processing_time:.2f}s")
            return result

        except Exception as e:
            end_time = datetime.now()
            processing_time = (end_time - start_time).total_seconds()

            logger.error(f"Erro no processamento: {e}")

            return ProcessingResult(
                success=False,
                total_products=0,
                total_variations=0,
                total_kits=0,
                total_errors=1,
                processing_time=processing_time,
                output_file=None,
                errors=[str(e)],
                warnings=[]
            )

    def _process_produtos(self, products: List[ProductOrigin]) -> List[ProductDestination]:
        """Processa aba PRODUTO - MANTENDO SEPARAÇÃO DE GRUPOS"""
        produtos_dest = []

        logger.info("🔍 Iniciando processamento de produtos...")
        logger.info("📋 DETECTANDO grupos e inserindo separadores...")

        # ✅ PASSO 1: IDENTIFICAR TODOS OS GRUPOS
        grupos = []
        grupo_atual = []

        for i, product in enumerate(products):
            # Se é linha vazia (separador)
            if not product.ean or str(product.ean).strip() == "":
                if grupo_atual:
                    grupos.append(grupo_atual)
                    logger.info(f"📦 Grupo {len(grupos)} identificado com {len(grupo_atual)} produtos")
                    grupo_atual = []
                continue

            # Adicionar produto ao grupo atual
            grupo_atual.append(product)

        # Adicionar último grupo se não terminou com linha vazia
        if grupo_atual:
            grupos.append(grupo_atual)
            logger.info(f"📦 Último grupo {len(grupos)} identificado com {len(grupo_atual)} produtos")

        logger.info(f"📊 Total de grupos identificados: {len(grupos)}")

        # ✅ PASSO 2: PROCESSAR CADA GRUPO
        for grupo_num, grupo in enumerate(grupos, 1):
            logger.info(f"🔍 === PROCESSANDO GRUPO {grupo_num} ({len(grupo)} produtos) ===")

            produtos_processados_no_grupo = 0

            for product in grupo:
                # ✅ PULAR PAIS VAZIOS NA ABA PRODUTO
                if self.should_skip_empty_parent(product):
                    logger.info(f"⏭️ PULANDO pai vazio na aba PRODUTO: EAN={product.ean}")
                    continue

                # Processar produto normal
                produto_processado = self._processar_produto_individual(product, grupo_num)
                if produto_processado:
                    produtos_dest.append(produto_processado)
                    produtos_processados_no_grupo += 1

            logger.success(f"✅ Grupo {grupo_num} processado: {produtos_processados_no_grupo} produtos adicionados")

            # ✅ INSERIR LINHA VAZIA APÓS CADA GRUPO (EXCETO O ÚLTIMO)
            if grupo_num < len(grupos) and produtos_processados_no_grupo > 0:
                produto_separador = self._criar_produto_separador()
                produtos_dest.append(produto_separador)
                logger.info(f"⚪ Separador inserido após grupo {grupo_num}")

        logger.info("📊 === RESULTADO FINAL ===")
        logger.info(f"  📦 Total de grupos processados: {len(grupos)}")
        logger.info(f"  📋 Total de linhas na aba PRODUTO: {len(produtos_dest)}")
        logger.info(f"  ⚪ Separadores inseridos: {len(grupos) - 1}")
        return produtos_dest

    def _criar_produto_separador(self) -> ProductDestination:
        """Cria um produto vazio para separar grupos"""
        return ProductDestination(
            ean="",
            cod_fabricante="",
            fornecedor="",
            desc_nfe="",
            desc_compra="",
            desc_etiqueta="",
            obs_produto="",
            complemento_produto="",
            categoria="",
            grupo="",
            cor="",
            desc_site="",
            desc_html="",
            marca="",
            site_marca="",
            ncm="",
            vr_custo_total=0.0,
            custo_ipi=0.0,
            custo_frete=0.0,
            preco_de_venda=0.0,
            preco_promocao=0.0,
            fabricacao_propria="F",
            tipo_produto="0",
            site_garantia="",
            qtde_emb_venda=0,
            qtde_volume=0,
            peso_bruto=0.0,
            peso_liquido=0.0,
            largura=0.0,
            altura=0.0,
            comprimento=0.0,
            dias_entrega=0,
            site_disponibilidade=0
        )

    def _processar_produto_individual(self, product: ProductOrigin, linha_num: int) -> Optional[ProductDestination]:
        """Processa um produto individual (extraído da lógica original)"""
        try:
            logger.info(f"🔍 === PROCESSANDO EAN: {product.ean} (Linha {linha_num}) ===")
            logger.info(f"  - Tipo Produto: '{product.tipo_produto}'")
            logger.info(f"  - Cat. (para aba PRODUTO): '{product.cat}'")
            logger.info(f"  - Grupo: '{product.grupo}'")
            logger.info(f"  - Anúncio: '{product.anuncio}'")
            logger.info(f"  - Título para Compra: '{product.titulo_compra}'")
            logger.info(f"  - Cor do Produto: '{product.cor}'")

            # 1. Cor do produto (com lógica especial)
            cor_produto_valor = self._processar_cor_por_tipo(product.cor, product.tipo_produto, product.ean)

            # 2. Descrição para o site baseada no Complemento + Cor + Anúncio
            desc_site_valor = self._processar_descricao_site_por_tipo(
                product.complemento_produto,
                product.cor,
                product.anuncio,
                product.tipo_produto,
                product.ean
            )
            logger.info(f"  ✅ Descrição para o Site FINAL: '{desc_site_valor}'")

            # 3. Título para compra → Descrição para compra
            desc_compra_valor = product.titulo_compra or ""
            logger.info(f"  ✅ Descrição para Compra: '{desc_compra_valor}'")

            # 4. Descrição HTML com lógica inteligente por tipo
            desc_html_final = self._trocar_cor_na_descricao(
                product.descricao_html,
                product.cor,
                product.ean,
                product.tipo_produto
            )

            # 5. Processamento avançado de cubagem
            cubagem_resultado = self._processar_descricao_para_produto(
                descricao_html=desc_html_final,
                ean=product.ean,
                comprimento_fixo_cm=101.0,
                arredondamento="ceil",
                casas_decimais=0,
                folga_cm=0.0,
                aplicar_folga_no_comprimento=False,
                fator_cubagem_kg_m3=300.0
            )

            # 6. Usar cubagem com fallback para colunas da planilha
            altura_final = product.altura or cubagem_resultado["altura_cm"]
            largura_final = product.largura or cubagem_resultado["largura_cm"]
            comprimento_final = product.comprimento or cubagem_resultado["comprimento_cm"]
            peso_bruto_final = product.peso_bruto or cubagem_resultado["peso_bruto_kg"]

            # Priorizar cubagem quando detectada, senão usar planilha
            if cubagem_resultado["qtde_volume"] and cubagem_resultado["qtde_volume"] > 0:
                qtde_volume_final = cubagem_resultado["qtde_volume"]
                fonte_qtde = "cubagem"
            elif product.qtde_volume and product.qtde_volume > 0:
                qtde_volume_final = product.qtde_volume
                fonte_qtde = "planilha"
            else:
                qtde_volume_final = 1
                fonte_qtde = "fallback"

            # 7. Determinar código do tipo produto
            logger.info("  🏷️ === DETERMINANDO CÓDIGO DO TIPO PRODUTO ===")
            logger.info(f"    - Tipo original: '{product.tipo_produto}'")
            logger.info(f"    - Precificação automática: {self.config.enable_auto_pricing}")
            logger.info(
                f"    - Modo precificação: {self.config.pricing_mode.value if self.config.pricing_mode else 'N/A'}")
            logger.info(f"    - Marca padrão: '{self.config.default_brand}'")

            tipo_produto_code = self._get_tipo_produto_code(product.tipo_produto)
            logger.success(f"  🎯 Tipo Produto Código FINAL: {tipo_produto_code}")
            # ✅ NOVA LÓGICA: ESTOQUE DE SEGURANÇA (Fornecedor vs Fábrica)
            logger.info(f"  📦 === CALCULANDO ESTOQUE DE SEGURANÇA - EAN: {product.ean} ===")
            logger.info(f"    - Tipo produto original: '{product.tipo_produto}'")
            logger.info(f"    - Tipo produto código: '{tipo_produto_code}'")

            tipo_norm = self._norm_tipo_produto(product.tipo_produto or "")

            is_fabrica_mode = self._is_fabrica_mode()
            is_dmov = (self.config.default_brand and self.config.default_brand.lower().strip() == "dmov")
            is_fabrica = (is_fabrica_mode or is_dmov)

            is_variacao = (tipo_norm in ("variacao", "var"))
            is_unitario = (tipo_norm in ("unitario", "un", "u"))

            if not is_fabrica:
                # 🏪 FORNECEDOR: estoque_seg = 1000 só nas variações
                estoque_seg_final = 1000 if is_variacao else 0
                logger.success(f"    🏪 FORNECEDOR: variação={is_variacao} → Estoque de Segurança = {estoque_seg_final}")
            else:
                # 🏭 FÁBRICA: estoque_seg = 1000 só no unitário
                estoque_seg_final = 1000 if is_unitario else 0
                logger.success(
                    f"    🏭 FÁBRICA/DMOV: unitário={is_unitario} → Estoque de Segurança = {estoque_seg_final}")

            logger.info(f"    🎯 Estoque de Segurança FINAL: {estoque_seg_final}")

            # ✅ ADICIONAR A LÓGICA DE ESTOQUE AQUI (código acima)

            # 8. Log de dimensões finais
            logger.info(f"  📐 === DIMENSÕES FINAIS - EAN: {product.ean} ===")
            # 8. Log de dimensões finais
            logger.info(f"  📐 === DIMENSÕES FINAIS - EAN: {product.ean} ===")
            logger.info(f"    - Altura: {altura_final} cm (fonte: {'planilha' if product.altura else 'cubagem'})")
            logger.info(f"    - Largura: {largura_final} cm (fonte: {'planilha' if product.largura else 'cubagem'})")
            logger.info(
                f"    - Comprimento: {comprimento_final} cm (fonte: {'planilha' if product.comprimento else 'cubagem'})")
            logger.info(
                f"    - Peso Bruto: {peso_bruto_final} kg (fonte: {'planilha' if product.peso_bruto else 'descrição'})")
            logger.info(f"    - Qtde Volume: {qtde_volume_final} (fonte: {fonte_qtde})")
            logger.info(f"    - Caixas processadas: {cubagem_resultado['caixas_encontradas']}")

            # 9. Precificação automática (se habilitada)
            vr_custo_total = 0.0
            custo_ipi = 0.0
            custo_frete = 0.0
            preco_de_venda = 0.0
            preco_promocao = 0.0

            if self.cost_pricing_engine and product.cod_fornecedor:
                try:
                    logger.info(f"  💰 === PROCESSANDO PRECIFICAÇÃO - EAN: {product.ean} ===")
                    logger.info(f"    - Código Fornecedor: '{product.cod_fornecedor}'")
                    logger.info(f"    - Modo de precificação: {self.config.pricing_mode.value}")

                    # Processar código do fornecedor
                    pricing_result = self.cost_pricing_engine.process_code(product.cod_fornecedor)

                    if pricing_result['found']:
                        vr_custo_total = pricing_result['vr_custo_total']
                        custo_ipi = pricing_result['custo_ipi']
                        custo_frete = pricing_result['custo_frete']
                        preco_de_venda = pricing_result['preco_de_venda']
                        preco_promocao = pricing_result['preco_promocao']

                        # Aplicar regra dos 90 centavos se habilitada
                        if self.config.apply_90_cents_rule:
                            if preco_de_venda > 0:
                                preco_de_venda = self.cost_pricing_engine.apply_90_cents_rule(preco_de_venda)
                            if preco_promocao > 0:
                                preco_promocao = self.cost_pricing_engine.apply_90_cents_rule(preco_promocao)
                            logger.info("    - Regra dos 90 centavos aplicada")

                        logger.success("  💰 PRECIFICAÇÃO REALIZADA COM SUCESSO!")
                        logger.success(f"    - Custo Total: R$ {vr_custo_total:.2f}")
                        logger.success(f"    - Custo Frete: R$ {custo_frete:.2f}")
                        logger.success(f"    - Custo IPI: R$ {custo_ipi:.2f}")
                        logger.success(f"    - Preço Venda: R$ {preco_de_venda:.2f}")
                        logger.success(f"    - Preço Promoção: R$ {preco_promocao:.2f}")
                        logger.success(f"    - Detalhes: {pricing_result['detail']}")

                    else:
                        logger.warning("  ⚠️ PRECIFICAÇÃO NÃO ENCONTRADA")
                        logger.warning(f"    - Código: '{product.cod_fornecedor}'")
                        logger.warning(f"    - Motivo: {pricing_result['detail']}")

                except Exception as pricing_error:
                    logger.error(f"  ❌ ERRO NA PRECIFICAÇÃO: {pricing_error}")

            elif self.cost_pricing_engine and not product.cod_fornecedor:
                logger.warning(f"  ⚠️ Precificação pulada: Código fornecedor vazio para EAN {product.ean}")
            elif not self.cost_pricing_engine:
                logger.debug("  ℹ️ Precificação automática desabilitada")

            # ✅ NOVO: VERIFICAÇÃO DE PRAZO DE EXCEÇÃO
            dias_entrega_final = 0
            site_disponibilidade_final = 0
            fornecedor_final = ""

            if self.config.enable_exception_prazo:
                exception_prazo = self.config.exception_prazo_days
                dias_entrega_final = exception_prazo
                site_disponibilidade_final = exception_prazo
                fornecedor_final = str(self.config.supplier_code) if self.config.supplier_code else self.config.default_brand
                logger.success(f"  🎯 PRAZO DE EXCEÇÃO APLICADO: {exception_prazo} dias para EAN {product.ean}")
                logger.info(f"    - Dias para Entrega: {dias_entrega_final}")
                logger.info(f"    - Site Disponibilidade: {site_disponibilidade_final}")
            else:
                # ✅ LÓGICA EXISTENTE PARA BUSCAR FORNECEDOR E APLICAR PRAZO ESPECIAL
                fornecedor_final = str(self.config.supplier_code) if self.config.supplier_code else self.config.default_brand

                # 🔍 BUSCAR FORNECEDOR NO BANCO PARA OBTER PRAZO
                if self.config.default_brand:
                    logger.info("🔍 === BUSCANDO FORNECEDOR NO BANCO ===")
                    logger.info(f"  🏷️ Marca padrão: '{self.config.default_brand}'")

                    supplier = self.supplier_db.search_supplier_by_name(self.config.default_brand) if self.supplier_db else None

                    if supplier:
                        logger.success("  ✅ Fornecedor encontrado no banco!")
                        logger.success(f"    - Nome: {supplier.name}")
                        logger.success(f"    - Código: {supplier.code}")
                        logger.success(f"    - Prazo base: {supplier.prazo_dias} dias")

                        # ✅ USAR CÓDIGO DO BANCO
                        fornecedor_final = str(supplier.code)

                        if supplier.prazo_dias > 0:
                            # ✅ PRIMEIRO: Pegar prazo base do fornecedor
                            prazo_base = supplier.prazo_dias
                            logger.info(f"  📅 Prazo base do fornecedor: {prazo_base} dias")

                            # ✅ SEGUNDO: APLICAR LÓGICA ESPECIAL PARA DMOV (ANTES DE DEFINIR FINAL)
                            prazo_final = self._get_prazo_especial_dmov(product, prazo_base)
                            logger.info(f"  🎯 Prazo após verificação especial: {prazo_final} dias")

                            # ✅ TERCEIRO: Definir prazos finais
                            dias_entrega_final = prazo_final
                            site_disponibilidade_final = prazo_final

                            # ✅ LOG DO RESULTADO
                            if prazo_final != prazo_base:
                                logger.success(f"  🎯 PRAZO ESPECIAL APLICADO: {prazo_final} dias (base era {prazo_base})")
                            else:
                                logger.success(f"  📝 PRAZO PADRÃO MANTIDO: {prazo_final} dias")
                        else:
                            logger.info(f"  ℹ️ Fornecedor sem prazo definido, usando valor da planilha: {product.prazo}")
                            # ✅ MESMO SEM PRAZO NO BANCO, VERIFICAR ESPECIAIS DMOV
                            prazo_planilha = product.prazo or 0
                            prazo_final = self._get_prazo_especial_dmov(product, prazo_planilha)
                            dias_entrega_final = prazo_final
                            site_disponibilidade_final = prazo_final
                    else:
                        logger.warning(f"  ⚠️ Fornecedor '{self.config.default_brand}' não encontrado no banco")
                        logger.warning("  🔧 Usando configuração padrão")

                        # ✅ MESMO SEM FORNECEDOR NO BANCO, VERIFICAR ESPECIAIS DMOV
                        prazo_default = product.prazo or 0
                        prazo_final = self._get_prazo_especial_dmov(product, prazo_default)
                        dias_entrega_final = prazo_final
                        site_disponibilidade_final = prazo_final

                logger.info("  📊 === RESULTADO FINAL ===")
                logger.info(f"  📊 FORNECEDOR FINAL: '{fornecedor_final}'")
                logger.info(f"  ⏱️ PRAZO FINAL: {dias_entrega_final} dias")
                logger.info(f"  🌐 SITE DISPONIBILIDADE: {site_disponibilidade_final} dias")

            produto_dest = ProductDestination(
                # Dados básicos
                ean=product.ean,
                cod_fabricante=product.cod_fornecedor or "",
                fornecedor=fornecedor_final,  # ✅ USAR CÓDIGO DO BANCO
                desc_nfe=product.complemento_titulo or "",
                desc_compra=desc_compra_valor,
                desc_etiqueta=product.complemento_titulo or "",
                obs_produto=product.complemento_titulo or "",
                complemento_produto=self._processar_complemento_por_tipo(
                    product.complemento_produto,
                    product.cor,
                    product.tipo_produto,
                    product.ean),
                categoria=product.cat or "",
                grupo=product.grupo or "Sem Grupo",

                # Os 3 campos principais com lógica corrigida
                cor=cor_produto_valor,
                desc_site=desc_site_valor,
                desc_html=desc_html_final,

                # Novos campos de precificação
                vr_custo_total=vr_custo_total,
                custo_ipi=custo_ipi,
                custo_frete=custo_frete,
                preco_de_venda=preco_de_venda,
                preco_promocao=preco_promocao,

                # Marcas e fornecedor
                marca=self.config.default_brand,
                site_marca="DRossi",

                ncm=product.ncm or "94016100",
                fabricacao_propria="T" if product.tipo_produto and product.tipo_produto.lower() == "fábrica" else "F",
                tipo_produto=tipo_produto_code,
                site_garantia="90 dias após o recebimento do produto",

                # Dimensões com cubagem avançada
                qtde_emb_venda=product.volumes or 1,
                qtde_volume=qtde_volume_final,
                peso_bruto=peso_bruto_final,
                peso_liquido=peso_bruto_final,
                largura=largura_final,
                altura=altura_final,
                comprimento=comprimento_final,
                # ✅ PRAZO JÁ RESOLVIDO AQUI
                dias_entrega=dias_entrega_final,
                site_disponibilidade=site_disponibilidade_final,
                estoque_seg = estoque_seg_final  # ✅ ADICIONAR ESTA LINHA
            )

            # ✅ LOG FINAL DO PRODUTO
            logger.info(f"🔍 === PRODUTO FINAL - EAN: {produto_dest.ean} ===")
            logger.info("  📊 VALORES FINAIS:")
            logger.info(f"    - fornecedor: '{produto_dest.fornecedor}'")
            logger.info(f"    - dias_entrega: {produto_dest.dias_entrega}")
            logger.info(f"    - site_disponibilidade: {produto_dest.site_disponibilidade}")
            logger.success("  ✅ Produto processado com sucesso!")

            return produto_dest

        except Exception as e:
            logger.error(f"❌ Erro ao processar produto {product.ean}: {e}")
            return None

    def _processar_descricao_site_por_tipo(self, complemento: Optional[str], cor: Optional[str],
                                           anuncio: Optional[str], tipo_produto: Optional[str], ean: str) -> str:
        """Processa Descrição para o Site baseado no tipo de produto"""

        if not tipo_produto:
            tipo_produto = "unitario"  # Default se não especificado

        tipo_lower = tipo_produto.lower().strip()
        complemento_base = (complemento or "").strip()
        cor_normalizada = self._normalize_case(cor) if cor else ""
        anuncio_limpo = (anuncio or "").strip()

        logger.info(f"🌐 === PROCESSANDO DESCRIÇÃO PARA O SITE - EAN: {ean} ===")
        logger.info(f"  📝 Complemento base: '{complemento_base}'")
        logger.info(f"  🎨 Cor: '{cor_normalizada}'")
        logger.info(f"  📢 Anúncio: '{anuncio_limpo}'")
        logger.info(f"  🏷️ Tipo: '{tipo_lower}'")

        desc_parts = []

        if tipo_lower == "pai":
            # PAI: Complemento + Anúncio (SEM cor)
            if complemento_base:
                desc_parts.append(complemento_base)
            if anuncio_limpo:
                desc_parts.append(anuncio_limpo)
            logger.info("  🔵 PRODUTO PAI: Complemento + Anúncio (sem cor)")

        elif tipo_lower in ["variação", "variacao"]:
            # VARIAÇÃO: Complemento + Anúncio + Cor (cor vem APÓS o anúncio)
            if complemento_base:
                desc_parts.append(complemento_base)
            if anuncio_limpo:
                desc_parts.append(anuncio_limpo)
            if cor_normalizada:
                desc_parts.append(cor_normalizada)
            logger.info("  🟡 PRODUTO VARIAÇÃO: Complemento + Anúncio + Cor")

        elif tipo_lower in ["unitário", "unitario"]:
            # UNITÁRIO: Complemento + Cor + Anúncio (cor vem ANTES do anúncio)
            if complemento_base:
                desc_parts.append(complemento_base)
            if cor_normalizada:
                desc_parts.append(cor_normalizada)
            if anuncio_limpo:
                desc_parts.append(anuncio_limpo)
            logger.info("  🟢 PRODUTO UNITÁRIO: Complemento + Cor + Anúncio")

        else:
            # TIPO DESCONHECIDO: Usar lógica de unitário como fallback
            if complemento_base:
                desc_parts.append(complemento_base)
            if cor_normalizada:
                desc_parts.append(cor_normalizada)
            if anuncio_limpo:
                desc_parts.append(anuncio_limpo)
            logger.info(f"  ⚪ TIPO DESCONHECIDO ('{tipo_lower}'): Usando lógica de unitário")

        # Junta as partes com espaço
        resultado = " ".join(filter(None, desc_parts)).strip()

        logger.success(f"  ✅ Descrição para o Site FINAL: '{resultado}'")
        return resultado

    def _processar_complemento_por_tipo(self, complemento: Optional[str], cor: Optional[str],
                                        tipo_produto: Optional[str], ean: str) -> str:
        """Processa Complemento do Produto baseado no tipo de produto"""

        if not tipo_produto:
            tipo_produto = "unitario"  # Default se não especificado

        tipo_lower = tipo_produto.lower().strip()
        complemento_base = (complemento or "").strip()
        cor_normalizada = self._normalize_case(cor) if cor else ""

        logger.info(f"🔧 === PROCESSANDO COMPLEMENTO PARA EAN: {ean} ===")
        logger.info(f"  📝 Complemento base: '{complemento_base}'")
        logger.info(f"  🎨 Cor: '{cor_normalizada}'")
        logger.info(f"  🏷️ Tipo: '{tipo_lower}'")

        if tipo_lower == "pai":
            # PAI: Apenas o complemento base (sem cor)
            resultado = complemento_base
            logger.info("  🔵 PRODUTO PAI: Complemento mantido sem cor")

        elif tipo_lower in ["variação", "variacao"]:
            # VARIAÇÃO: Complemento + " - " + Cor
            if complemento_base and cor_normalizada:
                resultado = f"{complemento_base} - {cor_normalizada}"
            elif complemento_base:
                resultado = complemento_base  # Se não tem cor, só o complemento
            elif cor_normalizada:
                resultado = f" - {cor_normalizada}"  # Se não tem complemento, só a cor com separador
            else:
                resultado = ""  # Se não tem nenhum dos dois
            logger.info("  🟡 PRODUTO VARIAÇÃO: Complemento + ' - ' + Cor")

        elif tipo_lower in ["unitário", "unitario"]:
            # UNITÁRIO: Complemento + " " + Cor
            if complemento_base and cor_normalizada:
                resultado = f"{complemento_base} {cor_normalizada}"
            elif complemento_base:
                resultado = complemento_base  # Se não tem cor, só o complemento
            elif cor_normalizada:
                resultado = cor_normalizada  # Se não tem complemento, só a cor
            else:
                resultado = ""  # Se não tem nenhum dos dois
            logger.info("  🟢 PRODUTO UNITÁRIO: Complemento + ' ' + Cor")

        else:
            # TIPO DESCONHECIDO: Usar lógica de unitário como fallback
            if complemento_base and cor_normalizada:
                resultado = f"{complemento_base} {cor_normalizada}"
            elif complemento_base:
                resultado = complemento_base
            elif cor_normalizada:
                resultado = cor_normalizada
            else:
                resultado = ""
            logger.info(f"  ⚪ TIPO DESCONHECIDO ('{tipo_lower}'): Usando lógica de unitário")

        logger.success(f"  ✅ Complemento FINAL: '{resultado}'")
        return resultado

    def _processar_cor_por_tipo(self, cor: Optional[str], tipo_produto: Optional[str], ean: str) -> str:
        """Processa cor baseado no tipo de produto, mantendo para unitários e variações."""

        if not tipo_produto:
            tipo_produto = "unitario"  # Default se o tipo não for especificado

        tipo_lower = tipo_produto.lower().strip()
        logger.info(f"  🎨 === PROCESSANDO COR PARA TIPO: '{tipo_lower}' (EAN: {ean}) ===")

        if tipo_lower == "pai":
            # PRODUTO PAI: Cor deve ficar VAZIA (sem cor no produto PAI)
            logger.info("  🔵 PRODUTO PAI: Cor será REMOVIDA (fica vazia)")
            return ""
        elif tipo_lower in ["variação", "variacao", "unitário", "unitario"]:
            # PRODUTO VARIAÇÃO/UNITÁRIO: Cor é NORMALIZADA e MANTIDA
            cor_normalizada = self._normalize_case(cor) if cor else ""
            logger.info(f"  🟢 PRODUTO {tipo_lower.upper()}: Cor normalizada para '{cor_normalizada}'")
            return cor_normalizada
        else:
            # Outros tipos não explicitamente tratados: Cor é NORMALIZADA por padrão
            cor_normalizada = self._normalize_case(cor) if cor else ""
            logger.info(f"  ⚪ PRODUTO TIPO DESCONHECIDO ('{tipo_lower}'): Cor normalizada para '{cor_normalizada}'")
            return cor_normalizada

    def _trocar_cor_na_descricao(self, desc_html: Optional[str], cor: Optional[str], ean: str,
                                 tipo_produto: Optional[str] = None) -> str:
        """TROCA (COR) PELA COR DO PRODUTO NA DESCRIÇÃO HTML - LÓGICA CORRIGIDA"""

        logger.info(f"🎨 === PROCESSANDO DESCRIÇÃO PARA EAN: {ean} ===")
        logger.info(f"  📝 Descrição recebida: '{desc_html}'")
        logger.info(f"  🎨 Cor recebida: '{cor}'")
        logger.info(f"  🏷️ Tipo Produto: '{tipo_produto}'")

        # Se não tem descrição, retorna vazio
        if not desc_html or str(desc_html).strip() == "":
            logger.info(f"  ❌ Sem descrição HTML para EAN {ean}")
            return ""

        desc_str = str(desc_html).strip()

        # Verificação do tipo de produto
        if not tipo_produto:
            tipo_produto = "unitario"  # Default se não informado

        tipo_lower = tipo_produto.lower().strip()
        logger.info(f"  🏷️ Tipo normalizado: '{tipo_lower}'")

        # Lógica diferenciada por tipo de produto
        if tipo_lower in ["pai", "variação", "variacao"]:
            # PRODUTOS PAI/VARIAÇÃO: Remove expressões de cor
            logger.info(f"  🔵 PRODUTO {tipo_lower.upper()}: Removendo expressões de cor...")
            desc_final = self._remover_expressoes_cor(desc_str, ean)
            return desc_final
        else:
            # PRODUTOS UNITÁRIOS: Substitui (cor) pela cor real
            logger.info("  🟢 PRODUTO UNITÁRIO: Substituindo (cor) pela cor real...")
            return self._substituir_cor_unitario(desc_str, cor, ean)

    def _remover_expressoes_cor(self, desc_html: str, ean: str) -> str:
        """Remove expressões como 'na cor (cor)' e 'no tom (cor)' para produtos PAI/VARIAÇÃO"""
        import re

        desc_original = desc_html
        logger.info(f"  🔄 Removendo expressões de cor para EAN {ean}...")

        # Padrões para remover (case insensitive)
        padroes_remover = [
            r'\s*na\s+cor\s+\(cor\)',  # "na cor (cor)"
            r'\s*no\s+tom\s+\(cor\)',  # "no tom (cor)"
            r'\s*da\s+cor\s+\(cor\)',  # "da cor (cor)"
            r'\s*de\s+cor\s+\(cor\)',  # "de cor (cor)"
            r'\s*com\s+cor\s+\(cor\)',  # "com cor (cor)"
            r'\s*em\s+cor\s+\(cor\)',  # "em cor (cor)"
            r'\s*na\s+tonalidade\s+\(cor\)',  # "na tonalidade (cor)"
            r'\s*no\s+acabamento\s+\(cor\)',  # "no acabamento (cor)"
            r'\s*\(cor\)',  # "(cor)" sozinho
        ]

        desc_processada = desc_html
        expressoes_removidas = []

        for padrao in padroes_remover:
            # Busca case insensitive
            matches = re.findall(padrao, desc_processada, re.IGNORECASE)
            if matches:
                expressoes_removidas.extend(matches)
                # Remove o padrão
                desc_processada = re.sub(padrao, '', desc_processada, flags=re.IGNORECASE)

        # Limpeza final: Remove espaços duplos e ajusta pontuação
        desc_processada = re.sub(r'\s+', ' ', desc_processada)  # Remove espaços múltiplos
        desc_processada = desc_processada.strip()

        if expressoes_removidas:
            logger.success("  🎯 EXPRESSÕES REMOVIDAS COM SUCESSO!")
            logger.success(f"    - EAN: {ean}")
            logger.success(f"    - Expressões removidas: {expressoes_removidas}")
            logger.success(f"    - ANTES: '{desc_original}'")
            logger.success(f"    - DEPOIS: '{desc_processada}'")
        else:
            logger.info("  📝 Nenhuma expressão de cor encontrada para remover")
            logger.info(f"    - Descrição mantida: '{desc_processada}'")

        return desc_processada

    def _substituir_cor_unitario(self, desc_html: str, cor: Optional[str], ean: str) -> str:
        """Substitui (cor) pela cor real para produtos UNITÁRIOS"""
        import re

        # Verificação melhorada para cor vazia/nula
        cor_vazia = (
                not cor or
                str(cor).strip() == "" or
                str(cor).strip().lower() in ["none", "null", "nan", "vazio"] or
                cor is None
        )

        if cor_vazia:
            logger.warning(f"  ⚠️ COR VAZIA/NULA para EAN {ean}")
            logger.warning(f"    - Valor recebido: '{cor}'")
            logger.warning(f"    - Tipo: {type(cor)}")

            # Verifica se tem (cor) na descrição
            padrao_cor = re.compile(r'\(cor\)', re.IGNORECASE)
            ocorrencias = padrao_cor.findall(desc_html)

            if ocorrencias:
                logger.error("  🚨 PROBLEMA: Descrição tem '(cor)' mas coluna 'Cor do Produto' está vazia!")
                logger.error(f"    - EAN: {ean}")
                logger.error(f"    - Ocorrências: {ocorrencias}")
                logger.error("    - Descrição será mantida SEM substituição!")

            return desc_html

        # Normaliza a cor
        cor_normalizada = self._normalize_case(cor)
        logger.info(f"  🎨 Cor normalizada: '{cor_normalizada}'")

        # Busca e substitui (COR) - case insensitive
        padrao_cor = re.compile(r'\(cor\)', re.IGNORECASE)

        # Conta ocorrências
        ocorrencias = padrao_cor.findall(desc_html)
        total_ocorrencias = len(ocorrencias)

        if total_ocorrencias > 0:
            # Faz a substituição
            desc_final = padrao_cor.sub(cor_normalizada, desc_html)

            logger.success("  🎯 SUBSTITUIÇÃO REALIZADA COM SUCESSO!")
            logger.success(f"    - EAN: {ean}")
            logger.success(f"    - Ocorrências substituídas: {total_ocorrencias}")
            logger.success(f"    - Cor usada: '{cor_normalizada}'")
            logger.success(f"    - ANTES: '{desc_html}'")
            logger.success(f"    - DEPOIS: '{desc_final}'")

            return desc_final
        else:
            logger.info("  📝 Nenhuma ocorrência de '(cor)' encontrada na descrição")
            return desc_html

    def _get_tipo_produto_code(self, tipo_produto: Optional[str]) -> str:
        """Converte tipo de produto para código - NOVA LÓGICA (Fornecedor vs Fábrica)"""
        # Default seguro
        tipo_raw = (tipo_produto or "").strip()
        tipo_norm = self._norm_tipo_produto(tipo_raw)

        # ✅ VERIFICAR MODO FÁBRICA
        is_fabrica_mode = self._is_fabrica_mode()

        # ✅ (Opcional redundante, mas mantém compatível com seu log/legado)
        is_dmov = (self.config.default_brand and self.config.default_brand.lower().strip() == "dmov")

        logger.info(f"  🏭 Modo Fábrica ativo: {is_fabrica_mode}")
        logger.info(f"  🏷️ Tipo produto (raw): '{tipo_raw}' | (norm): '{tipo_norm}'")
        logger.info(f"  🏭 Marca DMOV: {is_dmov}")

        # 🏪 FORNECEDOR: tudo tipo 0 (regra nova)
        if not (is_fabrica_mode or is_dmov):
            logger.info("  🔵 FORNECEDOR: Tipo = 0 (regra: tudo 0)")
            return "0"

        # 🏭 FÁBRICA: Pai e Unitário = 0 | Variação = 2 | Kit = 2 (mantido)
        if tipo_norm in ("variacao", "var"):
            logger.info("  🟡 FÁBRICA/DMOV - VARIAÇÃO: Tipo = 2")
            return "2"

        if "kit" in tipo_norm:
            logger.info("  📦 FÁBRICA/DMOV - KIT: Tipo = 2")
            return "2"

        # pai, unitario, vazio, ou qualquer outro: 0 (pela regra que você pediu)
        logger.info("  🔵 FÁBRICA/DMOV - PAI/UNITÁRIO/OUTROS: Tipo = 0")
        return "0"

    def _norm_tipo_produto(self, s: str) -> str:
        s = (s or "").strip().lower()
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
        return s

    def _is_fabrica_mode(self) -> bool:
        """Verifica se está no modo Fábrica"""
        # ✅ CONDIÇÃO 1: Precificação automática habilitada E modo é FÁBRICA
        if (self.config.enable_auto_pricing and
                self.config.pricing_mode and
                self.config.pricing_mode.value == "Fábrica"):
            logger.info("  🏭 Modo Fábrica detectado via precificação automática")
            return True

        # ✅ CONDIÇÃO 2: Marca padrão é DMOV
        if (self.config.default_brand and
                self.config.default_brand.lower().strip() == "dmov"):
            logger.info("  🏭 Modo Fábrica detectado via marca padrão DMOV")
            return True

        logger.info("  🏪 Modo Fornecedor ativo")
        return False

    def _process_variacoes(self, products: List[ProductOrigin], parents_for_variacao_only: Dict[str, ProductOrigin]) -> \
    List[VariationData]:
        """Processa aba VARIACAO - AGRUPAMENTO POR COMPLEMENTO_PRODUTO (incluindo pais vazios)"""
        variacoes = []

        logger.info("🔍 Iniciando processamento de variações - Agrupamento por COMPLEMENTO_PRODUTO...")
        logger.info(f"📦 Pais vazios recebidos: {len(parents_for_variacao_only)}")

        # ✅ COMBINAR PRODUTOS NORMAIS + PAIS VAZIOS PARA A LÓGICA DE VARIACAO
        todos_produtos_para_variacao = products.copy()

        # Adicionar pais vazios apenas para a lógica de VARIACAO
        for complemento, pai_vazio in parents_for_variacao_only.items():
            logger.info(f"  🔄 Incluindo pai vazio na VARIACAO: EAN={pai_vazio.ean}, Complemento='{complemento}'")
            todos_produtos_para_variacao.append(pai_vazio)

        # PASSO 1: Identificar todos os produtos PAI (INCLUINDO PAIS VAZIOS) por COMPLEMENTO_PRODUTO
        pais_por_complemento = {}

        for product in todos_produtos_para_variacao:
            if (product.tipo_produto and product.tipo_produto.lower().strip() == "pai"):
                complemento = product.complemento_produto
                if complemento:
                    complemento_limpo = complemento.strip()
                    pais_por_complemento[complemento_limpo] = product.ean
                    logger.info(f"🔵 PAI identificado: Complemento='{complemento_limpo}' → EAN_PAI={product.ean}")
                else:
                    logger.warning(f"⚠️ Produto PAI (EAN: {product.ean}) sem COMPLEMENTO_PRODUTO definido.")

        logger.info(f"📊 Total de PAIs encontrados: {len(pais_por_complemento)}")

        # PASSO 2: Processar todas as VARIAÇÕES
        variacoes_processadas = 0
        variacoes_sem_pai = 0

        for product in products:  # ✅ USA APENAS A LISTA ORIGINAL (sem pais vazios duplicados)
            if (product.tipo_produto and product.tipo_produto.lower().strip() in ["variação", "variacao"]):
                complemento_variacao = product.complemento_produto
                ean_pai_encontrado = None

                logger.info(f"🟡 === PROCESSANDO VARIAÇÃO: EAN={product.ean} ===")
                logger.info(f"  📝 Complemento da Variação: '{complemento_variacao}'")
                logger.info(f"  🎨 Cor da Variação: '{product.cor}'")

                if complemento_variacao:
                    complemento_variacao_limpo = complemento_variacao.strip()

                    # Busca exata por complemento do produto
                    if complemento_variacao_limpo in pais_por_complemento:
                        ean_pai_encontrado = pais_por_complemento[complemento_variacao_limpo]
                        logger.success(
                            f"  ✅ PAI encontrado: '{complemento_variacao_limpo}' → EAN_PAI: {ean_pai_encontrado}")
                    else:
                        # Busca similar (case insensitive)
                        for complemento_pai, ean_pai in pais_por_complemento.items():
                            if complemento_pai.lower() == complemento_variacao_limpo.lower():
                                ean_pai_encontrado = ean_pai
                                logger.success(
                                    f"  ✅ PAI encontrado (case insensitive): '{complemento_variacao_limpo}' → EAN_PAI: {ean_pai_encontrado}")
                                break

                # Se encontrou o PAI, criar a variação
                if ean_pai_encontrado:
                    variacao = VariationData(
                        ean_filho=product.ean,
                        ean_pai=ean_pai_encontrado,
                        cor=self._normalize_case(product.cor) or ""
                    )
                    variacoes.append(variacao)
                    variacoes_processadas += 1

                    logger.success("  🎯 VARIAÇÃO CRIADA COM SUCESSO!")
                    logger.success(f"    - COMPLEMENTO: '{complemento_variacao}'")
                    logger.success(f"    - EAN_PAI: {ean_pai_encontrado}")
                    logger.success(f"    - EAN_FILHO: {product.ean}")
                    logger.success(f"    - COR: '{product.cor}'")
                else:
                    variacoes_sem_pai += 1
                    logger.error(f"  ❌ PAI NÃO ENCONTRADO para variação: {product.ean}")

        logger.info("📊 === RESULTADO FINAL DO PROCESSAMENTO DE VARIAÇÕES ===")
        logger.info(f"  ✅ Variações processadas com sucesso: {variacoes_processadas}")
        logger.info(f"  ❌ Variações sem PAI encontrado: {variacoes_sem_pai}")
        logger.info(f"  📋 Total de PAIs disponíveis: {len(pais_por_complemento)}")

        return variacoes

    def _remove_cor_do_titulo(self, titulo: str, cor: Optional[str]) -> str:
        """Remove a cor do final do título para facilitar comparação"""
        if not titulo or not cor:
            return titulo or ""

        titulo_limpo = titulo.strip()
        cor_limpa = cor.strip()

        # Remove a cor do final se estiver presente
        if cor_limpa and titulo_limpo.lower().endswith(cor_limpa.lower()):
            titulo_limpo = titulo_limpo[:-len(cor_limpa)].strip()
            # Remove separadores comuns
            titulo_limpo = titulo_limpo.rstrip(" -_/|").strip()

        return titulo_limpo

    def _process_loja_web(self, products: List[ProductOrigin]) -> List[LojaWebData]:
        """Processa aba LOJA WEB - BUSCA HIERARQUIA ASCENDENTE POR ID"""
        loja_web = []

        logger.info("🔍 === INICIANDO PROCESSAMENTO LOJA WEB ===")

        for i, product in enumerate(products):
            # ✅ PULAR LINHAS VAZIAS
            if not product.ean or str(product.ean).strip() == "":
                continue

            # ✅ NOVA LÓGICA: Pular pais vazios na aba LOJA WEB também
            if self.should_skip_empty_parent(product):
                logger.info(f"⏭️ PULANDO pai vazio na LOJA WEB: EAN={product.ean}")
                continue

        # ✅ DEBUG: Verificar CategoryManager
        logger.info(f"🔍 CategoryManager status: {self.category_manager is not None}")

        if not self.category_manager:
            logger.warning("❌ CategoryManager é None, tentando inicializar...")
            self.init_category_manager()
            logger.info(f"🔍 Após init_category_manager: {self.category_manager is not None}")

        if self.category_manager:
            total_cats = len(self.category_manager.categories) if hasattr(self.category_manager, 'categories') else 0
            logger.info(f"✅ CategoryManager ativo com {total_cats} categorias principais")

            # ✅ DEBUG: Mostrar algumas categorias
            if hasattr(self.category_manager, 'categories') and self.category_manager.categories:
                logger.info("🔍 Primeiras 3 categorias do banco:")
                for i, cat in enumerate(self.category_manager.categories[:3]):
                    logger.info(
                        f"  {i + 1}. ID={cat.id}, Nome='{cat.name}', Children={len(cat.children) if hasattr(cat, 'children') else 0}")
        else:
            logger.error("❌ CategoryManager NÃO foi inicializado!")

        # ✅ DEBUG: Verificar produtos
        logger.info(f"🔍 Total de produtos recebidos: {len(products)}")

        produtos_com_categoria = [p for p in products if
                                  p.categoria and str(p.categoria).strip() and str(p.categoria).strip() != '0']
        logger.info(f"🔍 Produtos COM categoria: {len(produtos_com_categoria)}")

        if produtos_com_categoria:
            logger.info("🔍 Primeiros 3 produtos com categoria:")
            for i, p in enumerate(produtos_com_categoria[:3]):
                logger.info(f"  {i + 1}. EAN={p.ean}, Categoria='{p.categoria}' (tipo: {type(p.categoria)})")

        for i, product in enumerate(products):
            # ✅ PULAR LINHAS VAZIAS
            if not product.ean or str(product.ean).strip() == "":
                continue

            logger.info(f"🔍 === PRODUTO {i + 1}: EAN={product.ean} ===")
            logger.info(f"  - Categoria: '{product.categoria}' (tipo: {type(product.categoria)})")

            # ✅ INICIALIZAR CAMPOS DE CATEGORIA
            categoria_principal_id = ""
            nivel_adicional_1_id = ""
            nivel_adicional_2_id = ""

            if product.categoria:
                categoria_id_origem = str(product.categoria).strip()
                logger.info(f"  - Categoria string: '{categoria_id_origem}'")

                if categoria_id_origem and categoria_id_origem != '0':
                    logger.info(f"🔍 PROCESSANDO categoria {categoria_id_origem} para EAN {product.ean}")

                    # ✅ BUSCAR HIERARQUIA ASCENDENTE USANDO CATEGORY MANAGER
                    if self.category_manager:
                        logger.info("  - CategoryManager disponível, buscando hierarquia...")

                        # ✅ TESTE: Verificar se categoria existe
                        try:
                            cat_id = int(categoria_id_origem)
                            categoria_encontrada = self.category_manager._find_category_by_id(cat_id)
                            logger.info(f"  - Categoria {cat_id} encontrada: {categoria_encontrada is not None}")
                            if categoria_encontrada:
                                logger.info(f"    Nome: '{categoria_encontrada.name}'")
                        except ValueError:
                            logger.error(f"  - ERRO: ID inválido '{categoria_id_origem}'")
                            continue
                        except Exception as e:
                            logger.error(f"  - ERRO ao buscar categoria: {e}")
                            continue

                        hierarchy_ids = self.get_category_hierarchy_ids_ascendente(categoria_id_origem)
                        logger.info(f"  - Hierarquia retornada: {hierarchy_ids}")

                        if hierarchy_ids:
                            # ✅ PREENCHER BASEADO NA QUANTIDADE DE NÍVEIS
                            total_niveis = len(hierarchy_ids)
                            logger.info(f"📊 Total de níveis encontrados: {total_niveis}")

                            if total_niveis == 1:
                                # É uma categoria principal (nível 0)
                                categoria_principal_id = hierarchy_ids[0]
                                logger.success(f"  📍 Categoria Principal: ID {categoria_principal_id}")

                            elif total_niveis == 2:
                                # É uma subcategoria (nível 1)
                                categoria_principal_id = hierarchy_ids[0]  # Categoria pai
                                nivel_adicional_1_id = hierarchy_ids[1]  # Categoria atual
                                logger.success(
                                    f"     Subcategoria: Principal={categoria_principal_id}, Nível1={nivel_adicional_1_id}")

                            elif total_niveis >= 3:
                                # É uma sub-subcategoria (nível 2 ou mais)
                                categoria_principal_id = hierarchy_ids[0]  # Categoria raiz
                                nivel_adicional_1_id = hierarchy_ids[1]  # Categoria pai
                                nivel_adicional_2_id = hierarchy_ids[2]  # Categoria atual
                                logger.success(
                                    f"  📍 Sub-subcategoria: Principal={categoria_principal_id}, Nível1={nivel_adicional_1_id}, Nível2={nivel_adicional_2_id}")

                            logger.success(
                                f"✅ Hierarquia processada para ID {categoria_id_origem}: {' > '.join(hierarchy_ids)}")
                        else:
                            logger.warning(f"⚠️ Categoria ID {categoria_id_origem} não encontrada no CategoryManager")
                    else:
                        logger.warning("⚠️ CategoryManager não disponível")
                else:
                    logger.info("  - Categoria vazia ou '0', pulando...")
            else:
                logger.info("  - Produto sem categoria")

            # ✅ CRIAR OBJETO LOJA WEB
            loja_data = LojaWebData(
                ean=product.ean,
                cod_loja="1",  # ✅ SEMPRE "1"

                # ✅ CAMPOS DE CATEGORIA COM IDs CORRETOS
                categoria_principal=categoria_principal_id,
                nivel_1=nivel_adicional_1_id,
                nivel_2=nivel_adicional_2_id,
                nivel_3="",  # Sempre vazio por enquanto

                # ✅ CAMPOS BOOLEANOS T/F
                enviar_site="T",
                disponibilizar_site="T",
                site_lancamento="F",
                site_destaque="F"
            )
            loja_web.append(loja_data)

            # ✅ LOG FINAL DO RESULTADO
            logger.info(f"✅ Loja web criada: EAN={product.ean}")
            logger.info(f"  - Categoria Principal: '{categoria_principal_id}'")
            logger.info(f"  - Nível 1: '{nivel_adicional_1_id}'")
            logger.info(f"  - Nível 2: '{nivel_adicional_2_id}'")
            logger.info("  - COD LOJA: '1'")

        logger.info(f"✅ {len(loja_web)} produtos processados para aba LOJA WEB")
        return loja_web

    def get_category_hierarchy_ids_ascendente(self, categoria_id: str) -> Optional[List[str]]:
        """Busca hierarquia ASCENDENTE retornando lista de IDs do principal até o específico"""
        try:
            if not self.category_manager:
                logger.warning("CategoryManager não disponível")
                return None

            try:
                cat_id = int(categoria_id)
            except ValueError:
                logger.warning(f"ID de categoria inválido: {categoria_id}")
                return None

            # ✅ VERIFICAR SE A CATEGORIA EXISTE
            categoria_encontrada = self.category_manager._find_category_by_id(cat_id)
            if not categoria_encontrada:
                logger.warning(f"Categoria ID {categoria_id} não encontrada")
                return None

            # ✅ CONSTRUIR HIERARQUIA ASCENDENTE USANDO BUSCA RECURSIVA
            def find_path_with_ids(categories: List, target_id: int, current_path: List[str] = []) -> Optional[
                List[str]]:
                for cat in categories:
                    new_path = current_path + [str(cat.id)]

                    # Se encontrou a categoria alvo
                    if cat.id == target_id:
                        logger.info(f"🎯 Categoria {target_id} encontrada! Caminho: {' > '.join(new_path)}")
                        return new_path

                    # Buscar nos filhos
                    if hasattr(cat, 'children') and cat.children:
                        result = find_path_with_ids(cat.children, target_id, new_path)
                        if result:
                            return result
                return None

            # Buscar na estrutura de categorias
            hierarchy_ids = None
            if hasattr(self.category_manager, 'categories') and self.category_manager.categories:
                logger.info(
                    f"🔍 Iniciando busca para categoria ID {cat_id} em {len(self.category_manager.categories)} categorias principais")
                hierarchy_ids = find_path_with_ids(self.category_manager.categories, cat_id)

            if hierarchy_ids:
                logger.success(f"✅ Hierarquia IDs encontrada para {categoria_id}: {' > '.join(hierarchy_ids)}")

                # ✅ DEBUG: Mostrar detalhes de cada nível
                for i, cat_id_str in enumerate(hierarchy_ids):
                    cat_obj = self.category_manager._find_category_by_id(int(cat_id_str))
                    if cat_obj:
                        logger.info(f"  Nível {i}: ID={cat_id_str}, Nome='{cat_obj.name}'")

                return hierarchy_ids
            else:
                logger.warning(f"❌ Não foi possível construir hierarquia para ID {categoria_id}")
                return None

        except Exception as e:
            logger.error(f"❌ Erro ao buscar hierarquia ascendente da categoria {categoria_id}: {e}")
            return None

    def _resolve_category_fallback(self, categoria_origem: Optional[str], categories: Dict) -> Tuple[str, str, str]:
        """Fallback que retorna 3 valores para os 3 níveis"""
        if not categoria_origem or not categories:
            return "", "", ""

        # Usar o método antigo mas garantir 3 valores de retorno
        try:
            result = self._resolve_category(categoria_origem, categories)
            if len(result) >= 3:
                return result[0], result[1], result[2]
            elif len(result) == 2:
                return result[0], result[1], ""
            elif len(result) == 1:
                return result[0], "", ""
            else:
                return "", "", ""
        except Exception as e:
            logger.error(f"Erro no fallback de categoria: {e}")
            return "", "", ""

    def _process_kits(self, products: List[ProductOrigin]) -> List[KitData]:
        """Processa aba KIT - LÓGICA BASEADA NO TEMPLATE CORRETO"""
        kits = []

        logger.info("🔍 Iniciando processamento de kits...")

        for product in products:
            # ✅ NOVA LÓGICA: Pular pais vazios na aba KIT também
            if self.should_skip_empty_parent(product):
                logger.info(f"⏭️ PULANDO pai vazio na aba KIT: EAN={product.ean}")
                continue
            logger.debug(f"Analisando kit: EAN={product.ean}, TIPO_PRODUTO='{product.tipo_produto}'")

            # CONDIÇÃO: TIPO DE PRODUTO = "KIT"
            if (product.tipo_produto and
                product.tipo_produto.lower().strip() == "kit"):

                logger.info(f"✅ Kit encontrado: {product.ean} (Tipo: {product.tipo_produto})")

                # BASEADO NO TEMPLATE: Todos os kits usam o mesmo componente
                kit_data = KitData(
                    ean_kit=product.ean,           # EAN do kit
                    ean_componente="7901017021596", # Componente fixo (do template)
                    quantidade=1,                   # Sempre 1
                    custo_kit=0.0,                 # Sempre 0
                    desc_venda=0.0                 # Sempre 0
                )
                kits.append(kit_data)
            else:
                logger.debug(f"❌ Não é kit: {product.ean} (Tipo: {product.tipo_produto})")

        logger.info(f"✅ {len(kits)} kits processados para aba KIT")
        return kits

    def _clean_anuncio(self, anuncio: Optional[str]) -> str:
        """Remove sufixo padrão do anúncio"""
        if not anuncio:
            return ""

        # Remove " - D'Rossi" do final
        cleaned = anuncio.replace(" - D'Rossi", "").strip()
        return cleaned

    def _normalize_case(self, text: Optional[str]) -> str:
        """Normaliza case do texto (Title Case)"""
        if not text or str(text).strip() == "":
            return ""
        return str(text).strip().title()

    def _resolve_category(self, categoria_origem: Optional[str], categories: Dict[str, Tuple[str, str, str]]) -> Tuple[str, str, str]:
        """Resolve categoria usando mapeamento (antigo fallback)"""
        if not categoria_origem or not categories:
            return "", "", ""

        # Busca exata primeiro
        categoria_clean = categoria_origem.strip()
        if categoria_clean in categories:
            return categories[categoria_clean]

        # Busca por partes se contém separadores
        if " > " in categoria_clean or "/" in categoria_clean:
            # Tenta cada parte
            parts = [p.strip() for p in categoria_clean.replace("/", " > ").split(" > ")]
            for part in reversed(parts):  # Começa pela mais específica
                if part in categories:
                    return categories[part]

        # Busca parcial (contém)
        for key, value in categories.items():
            if categoria_clean.lower() in key.lower() or key.lower() in categoria_clean.lower():
                return value

        logger.warning(f"Categoria não mapeada: {categoria_origem}")
        return "", "", ""

    def _generate_output_file(
        self,
        produtos: List[ProductDestination],
        variacoes: List[VariationData],
        loja_web: List[LojaWebData],
        kits: List[KitData],
        origin_file: Path
    ) -> Path:
        """Gera arquivo Excel de saída"""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"Planilha_Destino_processado_{timestamp}.xlsx"
        output_path = self.config.output_dir / output_filename

        # Usa o writer para criar o arquivo
        self.writer.write_excel(
            output_path=output_path,
            template_path=self.config.template_path,
            produtos=produtos,
            variacoes=variacoes,
            loja_web=loja_web,
            kits=kits,
            origin_file=origin_file
        )

        return output_path

    # ✅ MÉTODOS RELACIONADOS A CATEGORY MANAGER (MANTIDOS E CORRIGIDOS PARA O BUSINESS LOGIC)
    def init_category_manager(self):
        """Inicializa o gerenciador de categorias para esta classe"""
        logger.info("🔍 === INICIALIZANDO CATEGORY MANAGER ===")

        try:
            from ..services.category_manager import CategoryManager

            categories_path = None
            possible_paths = [
                getattr(self.config, 'categories_db_path', None),
                getattr(self.config, 'categories_path', None),
                self.config.output_dir / "DB_CATEGORIAS.json",
                self.config.output_dir / "categories.json",
                Path("data/DB_CATEGORIAS.json"),
                Path("outputs/DB_CATEGORIAS.json")
            ]

            logger.info("🔍 Caminhos possíveis para DB_CATEGORIAS:")
            for i, path in enumerate(possible_paths):
                exists = path and Path(path).exists() if path else False
                logger.info(f"  {i + 1}. {path} - Existe: {exists}")

            for path in possible_paths:
                if path and Path(path).exists():
                    categories_path = Path(path)
                    logger.info(f"✅ Arquivo encontrado: {categories_path}")
                    break

            if categories_path:
                password = getattr(self.config, 'categories_password', 'admin123')
                logger.info("🔍 Tentando inicializar CategoryManager com senha...")

                self.category_manager = CategoryManager(categories_path, password)

                # ✅ TESTE: Verificar se carregou categorias
                if hasattr(self.category_manager, 'categories'):
                    total = len(self.category_manager.categories)
                    logger.success(f"✅ CategoryManager inicializado com {total} categorias")

                    if total > 0:
                        logger.info(
                            f"🔍 Primeira categoria: ID={self.category_manager.categories[0].id}, Nome='{self.category_manager.categories[0].name}'")
                else:
                    logger.error("❌ CategoryManager não tem atributo 'categories'")

            else:
                logger.error("❌ Nenhum arquivo de categorias encontrado")
                self.category_manager = None

        except Exception as e:
            logger.error(f"❌ Erro ao inicializar CategoryManager: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            self.category_manager = None

    def get_category_hierarchy(self, categoria_id: str) -> Optional[List[Dict]]:
        """Busca a hierarquia completa de uma categoria no banco (desta classe)"""
        try:
            if not self.category_manager:
                logger.warning("Gerenciador de categorias não disponível. Não é possível buscar hierarquia.")
                return None

            try:
                cat_id = int(categoria_id)
            except ValueError:
                logger.warning(f"ID de categoria inválido: {categoria_id}")
                return None

            # Usar o método existente do CategoryManager para obter o caminho
            category_path_str = self.category_manager.get_category_path(cat_id)
            if not category_path_str:
                logger.warning(f"Categoria ID {categoria_id} não encontrada no CategoryManager.")
                return None

            # Converter o caminho string para a estrutura de lista de dicionários esperada
            path_parts = [part.strip() for part in category_path_str.split('>')]
            hierarchy = []
            for i, name in enumerate(path_parts):
                # Para simplificar, estamos usando o nome como 'id' aqui,
                # mas em uma implementação completa, você buscaria o ID real de cada nível.
                hierarchy.append({'id': name, 'nome': name, 'nivel': i})

            return hierarchy

        except Exception as e:
            logger.error(f"Erro ao buscar hierarquia da categoria {categoria_id} no BusinessLogic: {e}")
            return None

    def _build_category_hierarchy(self, target_id: int) -> List[Dict]:
        """
        Constrói a hierarquia completa de uma categoria.
        Este método é interno e usado por get_category_hierarchy.
        Ele deve usar a estrutura interna do CategoryManager.
        """
        # Este método não é diretamente usado por get_category_hierarchy
        # que já usa self.category_manager.get_category_path.
        # Mantendo-o aqui caso alguma lógica interna ainda espere essa estrutura de 'children'.
        if not self.category_manager:
            return []

        def find_path_to_category(categories: List, current_path: List[Dict] = []) -> Optional[List[Dict]]:
            for cat in categories:
                current_cat = {
                    'id': str(cat.id),
                    'nome': cat.name,
                    'nivel': len(current_path),
                    'pai_id': current_path[-1]['id'] if current_path else None
                }
                new_path = current_path + [current_cat]

                if cat.id == target_id:
                    return new_path

                if hasattr(cat, 'children') and cat.children: # Verifica se 'children' existe
                    result = find_path_to_category(cat.children, new_path)
                    if result:
                        return result
            return None

        # O CategoryManager.get_category_path já retorna o caminho em string.
        # Se você precisa da lista de dicionários, o CategoryManager deveria ter um método para isso.
        # Por enquanto, o get_category_hierarchy acima já faz a conversão da string.
        # Este método `_build_category_hierarchy` parece ser mais detalhado que o necessário para o uso atual.
        # Vou deixar a implementação acima de `get_category_hierarchy` que se baseia em `get_category_path`.

        # Se for realmente necessário iterar sobre a estrutura de categorias,
        # o `CategoryManager` precisaria expor sua estrutura de `categories` (`self.category_manager.categories`)
        # e então este método poderia ser usado.
        # Por simplicidade e para evitar duplicação, o `get_category_hierarchy` acima já resolve usando a string.
        # Retornando vazio para evitar que seja chamado inadvertidamente.
        return []

    def get_category_by_id(self, categoria_id: str) -> Optional[Dict]:
        """Busca uma categoria específica por ID (desta classe)"""
        try:
            if not self.category_manager:
                logger.warning("Gerenciador de categorias não disponível. Não é possível buscar categoria por ID.")
                return None

            try:
                cat_id = int(categoria_id)
            except ValueError:
                logger.warning(f"ID de categoria inválido: {categoria_id}")
                return None

            categoria = self.category_manager._find_category_by_id(cat_id)

            if categoria:
                return {
                    'id': str(categoria.id),
                    'nome': categoria.name,
                    'status': categoria.status,
                    'pai_id': None # Preenchido pela hierarquia se necessário, não diretamente por este método
                }
            return None

        except Exception as e:
            logger.error(f"Erro ao buscar categoria {categoria_id} no BusinessLogic: {e}")
            return None

    def should_skip_empty_parent(self, product: ProductOrigin) -> bool:
        """Verifica se é um pai vazio (apenas EAN + tipo + complemento)"""
        try:
            # ✅ DEVE SER PRODUTO PAI
            if not product.tipo_produto or product.tipo_produto.lower().strip() != "pai":
                return False

            # ✅ DEVE TER EAN E COMPLEMENTO
            if not product.ean or not product.complemento_produto:
                return False

            logger.info(f"🔍 === VERIFICANDO PAI - EAN: {product.ean} ===")
            logger.info(f"  📝 Tipo: '{product.tipo_produto}'")
            logger.info(f"  🏷️ Complemento: '{product.complemento_produto}'")

            # ✅ VERIFICAR SE TEM APENAS OS 3 CAMPOS BÁSICOS
            campos_extras = [
                product.complemento_titulo,
                product.anuncio,
                product.titulo_compra,
                product.descricao_html,
                product.cor,
                product.cat,
                product.grupo
            ]

            # Contar campos extras preenchidos
            campos_extras_preenchidos = []
            for campo in campos_extras:
                if campo and str(campo).strip() and str(campo).strip().lower() not in ["nan", "none", ""]:
                    campos_extras_preenchidos.append(str(campo)[:30])

            logger.info(f"     Campos extras preenchidos: {len(campos_extras_preenchidos)}")
            logger.info(f"  📋 Dados extras: {campos_extras_preenchidos}")

            # ✅ SE TEM POUCOS OU NENHUM CAMPO EXTRA = PAI VAZIO
            if len(campos_extras_preenchidos) <= 1:  # Tolerância de 1 campo extra
                logger.warning(f"  ⚪ PAI VAZIO detectado - EAN: {product.ean}")
                logger.warning(f"    - Apenas {len(campos_extras_preenchidos)} campo(s) extra(s)")
                logger.warning("    - Vai APENAS para VARIACAO")
                return True

            # ✅ SE TEM MUITOS CAMPOS EXTRAS = PAI COMPLETO
            logger.success(f"  ✅ PAI COMPLETO - EAN: {product.ean}")
            logger.success(f"    - {len(campos_extras_preenchidos)} campos extras preenchidos")
            logger.success("    - Vai para TODAS as abas")
            return False

        except Exception as e:
            logger.error(f"Erro ao verificar pai vazio: {e}")
            return False

    def _is_empty_or_nan(self, value) -> bool:
        """Verifica se um valor está vazio ou é NaN"""
        try:
            if value is None:
                return True

            # Verificar se é NaN (para valores pandas)
            try:
                import pandas as pd
                if pd.isna(value):
                    return True
            except (ImportError, TypeError):
                pass

            # Verificar se é string vazia
            if isinstance(value, str):
                return not value.strip()

            # Verificar se é número zero (dependendo do contexto)
            if isinstance(value, (int, float)):
                return value == 0

            return False

        except Exception:
            return True

    def _get_prazo_especial_dmov(self, product: ProductOrigin, prazo_fornecedor: int) -> int:
        """Determina prazo especial para produtos DMOV baseado nas linhas de produto"""

        logger.info("🏭 === INICIANDO VERIFICAÇÃO PRAZO ESPECIAL DMOV ===")
        logger.info(f"     EAN: {product.ean}")
        logger.info(f"  🏷️ Marca configurada: '{self.config.default_brand}'")
        logger.info(f"  ⏱️ Prazo fornecedor recebido: {prazo_fornecedor}")

        # ✅ SÓ APLICAR PARA DMOV
        if not self.config.default_brand or "DMOV" not in self.config.default_brand.upper():  # <<< AQUI ESTÁ A CORREÇÃO
            logger.info(f"  ❌ Marca não contém 'DMOV' ou não configurada: '{self.config.default_brand}'")
            return prazo_fornecedor

        logger.info("✅ Marca DMOV confirmada, verificando linhas especiais...")

        # ✅ LINHAS COM PRAZO ESPECIAL DE 10 DIAS
        linhas_especiais = ["MORGAN", "LISBOA", "SHER", "JULIETTE", "JULIETE"]  # Mantenha a lista em maiúsculas

        # ✅ CAMPOS PARA VERIFICAR
        campos_para_verificar = [
            ("complemento_produto", product.complemento_produto),
            ("complemento_titulo", product.complemento_titulo),
            ("anuncio", product.anuncio),
            ("titulo_compra", product.titulo_compra),
            ("desc_site", getattr(product, 'desc_site', None)),
            ("descricao_html", product.descricao_html)
        ]

        logger.info(f"  🔍 Linhas especiais: {linhas_especiais}")
        logger.info(f"  📋 Campos a verificar: {len(campos_para_verificar)}")

        # ✅ VERIFICAR CADA CAMPO
        for nome_campo, valor_campo in campos_para_verificar:
            logger.info(f"     === VERIFICANDO CAMPO: {nome_campo} ===")

            if not valor_campo:
                logger.info("    ❌ Campo vazio ou None")
                continue

            valor_str = str(valor_campo)
            valor_upper = valor_str.upper()  # Converte para maiúsculas apenas uma vez
            logger.info(f"    ▶️ Valor original: '{valor_str}'")
            logger.info(f"    🔤 Valor em maiúsculo: '{valor_upper}'")

            # ✅ VERIFICAR CADA LINHA ESPECIAL
            for linha in linhas_especiais:
                logger.info(f"    🔍 Verificando palavra-chave: '{linha}'")

                if linha in valor_upper:  # Verifica se a palavra-chave (em maiúsculas) está no valor do campo (em maiúsculas)
                    logger.success("  🎯 === LINHA ESPECIAL ENCONTRADA! ===")
                    logger.success(f"    - Campo: {nome_campo}")
                    logger.success(f"    - Valor: '{valor_str}'")
                    logger.success(f"    - Palavra-chave detectada: {linha}")
                    logger.success("    - PRAZO ESPECIAL: 10 dias")
                    logger.success(f"    - Prazo anterior: {prazo_fornecedor} dias")
                    return 10
                else:
                    logger.info(f"    ❌ '{linha}' não encontrado em '{valor_upper}'")

        # ✅ SE NÃO ENCONTROU LINHA ESPECIAL, USAR PRAZO PADRÃO
        logger.info("  📅 === NENHUMA LINHA ESPECIAL ENCONTRADA ===")
        logger.info(f"  ⏱️ Mantendo prazo padrão do fornecedor: {prazo_fornecedor} dias")
        return prazo_fornecedor