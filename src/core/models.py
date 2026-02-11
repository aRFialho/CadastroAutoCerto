from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
from pathlib import Path
from enum import Enum


class TipoProduto(str, Enum):
    KIT = "kit"
    UNITARIO = "unitário"
    FABRICA = "fábrica"


class TipoAnuncio(str, Enum):
    PAI = "pai"
    FILHO = "filho"


# ✅ NOVO ENUM PARA MODO DE PRECIFICAÇÃO
class PricingMode(str, Enum):
    FABRICA = "Fábrica"
    FORNECEDOR = "Fornecedor"


class ProductOrigin(BaseModel):
    """Modelo para dados da planilha de origem"""
    ean: str = Field(..., description="Código de barras principal")
    ean_variacao: Optional[str] = Field(None, description="EAN da variação")
    cod_fornecedor: str = Field(..., description="Código do fornecedor")
    complemento_titulo: Optional[str] = Field(None, description="Título interno")
    anuncio: Optional[str] = Field(None, description="Título do anúncio")
    titulo_compra: Optional[str] = Field(None, description="Título para compra")  # ✅ NOVA COLUNA

    # ✅ ALTERAÇÃO: Produto agora é opcional (não será mais usado para preenchimento)
    produto: Optional[str] = Field(None, description="Nome do produto (não usado para preenchimento)")

    # ✅ NOVO CAMPO: Cat. da origem (para aba PRODUTO)
    cat: Optional[str] = Field(None, description="Cat. da origem (para aba PRODUTO)")

    # ✅ MANTER: Grupo
    grupo: Optional[str] = Field(None, description="Grupo do produto")

    cor: Optional[str] = Field(None, description="Cor do produto")  # ✅ ATUALIZADO: Cor do produto
    tipo_anuncio: Optional[str] = Field(None, description="Tipo: pai/filho")
    tipo_produto: Optional[str] = Field(None, description="KIT/UNITÁRIO/fábrica")
    volumes: Optional[int] = Field(1, description="Quantidade de volumes")
    qtde_volume: Optional[int] = Field(None, description="Quantidade de volume")
    peso_bruto: Optional[float] = Field(0.0, description="Peso bruto em kg")
    peso_liquido: Optional[float] = Field(0.0, description="Peso líquido em kg")
    largura: Optional[float] = Field(0.0, description="Largura em cm")
    altura: Optional[float] = Field(0.0, description="Altura em cm")
    comprimento: Optional[float] = Field(0.0, description="Comprimento em cm")
    prazo: Optional[int] = Field(0, description="Prazo de entrega")
    descricao_html: Optional[str] = Field(None, description="Descrição HTML")

    # ✅ CATEGORIA CONTINUA (para LOJA WEB)
    categoria: Optional[str] = Field(None, description="Categoria do produto (para LOJA WEB)")

    ncm: Optional[str] = Field(None, description="NCM do produto")
    complemento_produto: Optional[str] = Field(None, description="Complemento do produto (sem cod e marca)")

    @validator('ean', 'cod_fornecedor')
    def validate_required_fields(cls, v):
        if not v or not str(v).strip():
            raise ValueError("Campo obrigatório não pode estar vazio")
        return str(v).strip()

    @validator('ean_variacao', 'complemento_titulo', 'anuncio', 'titulo_compra', 'cor', 'descricao_html', 'categoria',
               'grupo', 'ncm', 'complemento_produto', 'produto', 'cat')
    def clean_optional_strings(cls, v):
        if v is None:
            return None
        return str(v).strip() if str(v).strip() else None


class CategoryMapping(BaseModel):
    """Modelo para mapeamento de categorias"""
    categoria_origem: str
    categoria_principal: str
    nivel_1: Optional[str] = None
    nivel_2: Optional[str] = None


class ProductDestination(BaseModel):
    """Modelo para produto na planilha de destino"""
    # Dados básicos
    ean: str
    cod_fabricante: str
    fornecedor: str = "D'Rossi"
    desc_nfe: str
    desc_compra: str
    desc_etiqueta: str
    obs_produto: str
    complemento_produto: str

    # ✅ ALTERAÇÃO: Categoria agora vem de "cat" (Cat. da origem)
    categoria: str  # Cat. da origem vai para Categoria da aba PRODUTO

    grupo: str
    cor: str
    desc_site: str
    marca: str = "D'Rossi"
    ncm: str = "94016100"

    # ✅ NOVOS CAMPOS PARA PRECIFICAÇÃO AUTOMÁTICA
    vr_custo_total: float = Field(0.0, description="Valor do custo total")
    custo_ipi: float = Field(0.0, description="Custo do IPI")
    custo_frete: float = Field(0.0, description="Custo do frete")
    preco_de_venda: float = Field(0.0, description="Preço de venda")
    preco_promocao: float = Field(0.0, description="Preço de promoção")

    # Configurações
    fabricacao_propria: str = "F"  # T/F
    tipo_produto: str = "0"  # 0=unitário, 2=kit
    imprime_ped: str = "T"
    imprime_comp: str = "T"
    imprime_nf: str = "F"
    site_marca: str = "D Rossi"
    unidade_venda: str = "UN"
    unidade_compra: str = "UN"
    produto_inativo: str = "F"

    # Garantia e promoção
    dias_garantia: int = 90
    site_garantia: str = "90 dias após o recebimento do produto"
    inicio_promocao: str = "01/01/2025"
    fim_promocao: str = "31/12/2040"

    # Dimensões e estoque
    qtde_emb_venda: int = 1
    qtde_volume: int = 0.0
    peso_bruto: float = 0.0
    peso_liquido: float = 0.0
    largura: float = 0.0
    altura: float = 0.0
    comprimento: float = 0.0
    diametro: float = 0.0
    estoque_min: int = 0
    estoque_seg: int = 0
    dias_entrega: int
    site_disponibilidade: int

    # Descrição (sem preços)
    desc_html: str = ""

    class Config:
        arbitrary_types_allowed = True


class VariationData(BaseModel):
    """Modelo para dados de variação"""
    ean_filho: str
    ean_pai: str
    cor: str


class LojaWebData(BaseModel):
    """Modelo para dados da loja web"""
    ean: str
    cod_loja: str = "1"
    enviar_site: str = "T"
    disponibilizar_site: str = "T"
    site_lancamento: str = "F"
    site_destaque: str = "F"
    categoria_principal: str = ""
    nivel_1: str = ""
    nivel_2: str = ""


class KitData(BaseModel):
    """Modelo para dados de kit"""
    ean_kit: str
    ean_componente: str
    custo_kit: float = 0.0
    desc_venda: float = 0.0
    quantidade: int = 1


class ProcessingResult(BaseModel):
    """Resultado do processamento"""
    success: bool
    total_products: int = 0
    total_variations: int = 0
    total_kits: int = 0
    total_errors: int = 0
    processing_time: float = 0.0
    output_file: Optional[Path] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_products == 0:
            return 1.0
        return (self.total_products - self.total_errors) / self.total_products

    class Config:
        arbitrary_types_allowed = True


class EmailConfig(BaseModel):
    """Configuração de e-mail"""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_use_ssl: bool = True
    username: str
    password: str
    from_addr: str
    to_addrs: List[str]


class AppConfig(BaseModel):
    """Configuração da aplicação"""
    # Caminhos
    template_path: Optional[Path] = Field(None, description="Caminho da planilha modelo (auto-detectado)")
    categories_path: Path = Path("C:/Users/USER/Desktop/Planilhas/Não tirar daqui/Relação de Categorias.xlsx")
    output_dir: Path = Path("~/Documents/cadastro_produtos_python/outputs").expanduser()
    logo_path: Path = Path("C:/Users/USER/Documents/cadastro_produtos_python/logo-CAD.ico")

    # ✅ NOVO: Caminho para o banco de dados de categorias
    categories_db_path: Path = Path("C:/Users/USER/Documents/cadastro_produtos_python/data/DB_CATEGORIAS.json")
    categories_password: str = Field("172839", description="Senha para gerenciar categorias")

    # ✅ NOVOS CAMPOS PARA PRECIFICAÇÃO AUTOMÁTICA
    cost_file_path: Optional[Path] = Field(None, description="Caminho da planilha de custos")
    enable_auto_pricing: bool = Field(False, description="Habilitar precificação automática")
    pricing_mode: PricingMode = Field(PricingMode.FABRICA, description="Modo de precificação: Fábrica ou Fornecedor")
    apply_90_cents_rule: bool = Field(False, description="Aplicar regra dos 90 centavos nos preços")

    # E-mail
    email: Optional[EmailConfig] = None

    # Processamento
    default_brand: str = "D'Rossi"

    # ✅ NOVO CAMPO PARA CÓDIGO DO FORNECEDOR
    supplier_code: int = Field(0, description="Código do fornecedor resolvido do banco de dados")
    # ✅ NOVOS CAMPOS PARA EXCEÇÃO DE PRAZO
    enable_exception_prazo: bool = Field(False, description="Habilitar exceção de prazo para entrega")
    exception_prazo_days: int = Field(0, description="Dias de prazo de exceção")
    batch_size: int = 1000
    max_workers: int = 4

    # Abas padrão
    sheet_origem: str = "Produtos"
    sheet_produto_dest: str = "PRODUTO"
    sheet_variacao_dest: str = "VARIACAO"
    sheet_lojaweb_dest: str = "LOJA WEB"
    sheet_kit_dest: str = "KIT"

    def __init__(self, **data):
        super().__init__(**data)

        # ✅ AUTO-DETECTAR TEMPLATE EMBARCADO
        self._setup_template_path()

        # Criar diretórios se não existirem
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _setup_template_path(self):
        """Configura o caminho do template automaticamente"""
        try:
            # ✅ TENTAR USAR TEMPLATE EMBARCADO
            from ..utils.resource_manager import get_template_path
            self.template_path = get_template_path()
            print(f"✅ Template embarcado carregado: {self.template_path}")

        except ImportError:
            # ✅ FALLBACK: resource_manager ainda não existe
            print("⚠️ Resource manager não encontrado, usando caminho padrão")
            self.template_path = Path("C:/Users/USER/Documents/cadastro_produtos_python/inputs/Planilha Destino.xlsx")

        except Exception as e:
            # ✅ FALLBACK: erro ao carregar template embarcado
            print(f"⚠️ Erro ao carregar template embarcado: {e}")
            print("📁 Usando caminho padrão como fallback")
            self.template_path = Path("C:/Users/USER/Documents/cadastro_produtos_python/inputs/Planilha Destino.xlsx")

    class Config:
        env_file = ".env"
        env_prefix = "CADASTRO_"
        arbitrary_types_allowed = True


class CategoryItem(BaseModel):
    name: str
    id: int
    status: str = "Ativo"
    children: List['CategoryItem'] = Field(default_factory=list)  # Recursivo!

    @validator('status')
    def validate_status(cls, v):
        if v not in ["Ativo", "Inativo"]:
            raise ValueError("Status da categoria deve ser 'Ativo' ou 'Inativo'")
        return v

    class Config:
        arbitrary_types_allowed = True  # Necessário para o campo children recursivo