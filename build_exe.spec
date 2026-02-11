# build_exe.spec
# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

block_cipher = None

# Caminhos do projeto
project_root = Path.cwd()
src_path = project_root / "src"

# ✅ CORREÇÃO: Verifica quais pastas existem antes de incluir
datas_to_include = []

# Sempre inclui o src (obrigatório)
datas_to_include.append(('src', 'src'))

# ✅ NOVO: Incluir template embarcado
template_path = src_path / "resources" / "templates" / "Planilha Destino.xlsx"
if template_path.exists():
    datas_to_include.append((str(template_path), 'resources/templates/'))
    print(f"✅ Template encontrado e será embarcado: {template_path}")
else:
    print(f"⚠️ Template não encontrado em: {template_path}")
    print("   Certifique-se de copiar Planilha Destino.xlsx para src/resources/templates/")

# ✅ NOVO: Incluir toda a pasta resources se existir
resources_path = src_path / "resources"
if resources_path.exists():
    datas_to_include.append((str(resources_path), 'resources/'))
    print(f"✅ Pasta resources será embarcada: {resources_path}")

# ✅ ADICIONAR: Inclui assets (tem templates de email)
if (project_root / "assets").exists():
    datas_to_include.append(('assets', 'assets'))

# Inclui apenas se existir
if (project_root / "inputs").exists():
    datas_to_include.append(('inputs', 'inputs'))

if (project_root / "README.md").exists():
    datas_to_include.append(('README.md', '.'))

if (project_root / "requirements.txt").exists():
    datas_to_include.append(('requirements.txt', '.'))

# ✅ NOVO: Incluir CHANGELOG para rastreamento de versões
if (project_root / "CHANGELOG.md").exists():
    datas_to_include.append(('CHANGELOG.md', '.'))
    print(f"✅ Changelog incluído para rastreamento de versões")

# Verifica se tem logo
logo_paths = [
    project_root / "logo-CAD.ico",
    project_root / "logo.ico",
    project_root / "icon.ico"
]
logo_file = None
for logo_path in logo_paths:
    if logo_path.exists():
        logo_file = str(logo_path)
        datas_to_include.append((str(logo_path), '.'))
        break

print(f"📁 Arquivos que serão incluídos: {datas_to_include}")

# ✅ NOVO: Incluir bancos de dados pré-populados
print(f"🗄️ === VERIFICANDO BANCOS DE DADOS ===")
database_files = []

# Banco de fornecedores
db_suppliers = project_root / "outputs" / "suppliers.db"
if db_suppliers.exists():
    database_files.append((str(db_suppliers), 'databases/'))
    print(f"✅ Banco de fornecedores será incluído: {db_suppliers}")
    print(f"   Tamanho: {db_suppliers.stat().st_size} bytes")
else:
    print(f"⚠️ Banco de fornecedores não encontrado: {db_suppliers}")
    print(f"   Execute o sistema uma vez para criar o banco")

# Banco de categorias
db_categories = project_root / "outputs" / "DB_CATEGORIAS.json"
if db_categories.exists():
    database_files.append((str(db_categories), 'databases/'))
    print(f"✅ Banco de categorias será incluído: {db_categories}")
    print(f"   Tamanho: {db_categories.stat().st_size} bytes")
else:
    print(f"⚠️ Banco de categorias não encontrado: {db_categories}")
    print(f"   Execute o sistema uma vez para criar o banco")

# Catálogo de produtos
db_catalog = project_root / "outputs" / "product_catalog.db"
if db_catalog.exists():
    database_files.append((str(db_catalog), 'databases/'))
    print(f"✅ Catálogo de produtos será incluído: {db_catalog}")
    print(f"   Tamanho: {db_catalog.stat().st_size} bytes")
else:
    print(f"ℹ️ Catálogo de produtos não encontrado (normal se não foi criado ainda)")

# ✅ NOVO: Incluir arquivos de configuração importantes
config_files = []

# Arquivo de configuração principal (se existir)
config_file = project_root / "outputs" / "config.json"
if config_file.exists():
    config_files.append((str(config_file), 'config/'))
    print(f"✅ Configuração principal será incluída: {config_file}")

# Incluir bancos e configurações na lista de dados
datas_to_include.extend(database_files)
datas_to_include.extend(config_files)

if database_files:
    print(f"✅ Total de {len(database_files)} bancos de dados serão incluídos")
else:
    print(f"⚠️ ATENÇÃO: Nenhum banco de dados encontrado para incluir!")
    print(f"   Execute o sistema uma vez para criar os bancos antes do build")
    print(f"   Ou use o script prepare_databases.bat")

print(f"📦 Total de arquivos/pastas para incluir: {len(datas_to_include)}")
print(f"🗄️ === FIM VERIFICAÇÃO BANCOS ===")

a = Analysis(
    ['main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas_to_include,  # ✅ USA LISTA DINÂMICA COM BANCOS
    hiddenimports=[
        # Seus módulos específicos
        'src',
        'src.ui',
        'src.ui.main_window',
        'src.ui.components',
        'src.ui.components.log_viewer',
        'src.ui.components.progress_dialog',
        'src.ui.components.costs_manager_window',
        'src.ui.styles',
        'src.core',
        'src.core.models',
        'src.core.config',
        'src.core.exceptions',
        'src.core.supplier_database',  # ✅ ADICIONADO
        'src.processors',
        'src.processors.business_logic',
        'src.processors.data_mapper',
        'src.processors.excel_reader',
        'src.processors.excel_writer',
        'src.services',
        'src.services.category_service',
        'src.services.category_manager',  # ✅ ADICIONADO
        'src.services.cost_service',
        'src.services.costing_pricing_engine',  # ✅ ADICIONADO
        'src.services.email_sender',
        'src.services.email_service',
        'src.utils',
        'src.utils.file_utils',
        'src.utils.logger',
        'src.utils.validators',
        'src.utils.resource_manager',  # ✅ NOVO: Resource manager

        # ✅ PANDAS E DEPENDÊNCIAS (ADICIONADO)
        'pandas',
        'pandas.core',
        'pandas.core.arrays',
        'pandas.core.arrays.categorical',
        'pandas.core.arrays.datetimes',
        'pandas.core.arrays.integer',
        'pandas.core.arrays.period',
        'pandas.core.arrays.string_',
        'pandas.core.arrays.timedeltas',
        'pandas.core.computation',
        'pandas.core.dtypes',
        'pandas.core.dtypes.common',
        'pandas.core.dtypes.dtypes',
        'pandas.core.dtypes.generic',
        'pandas.core.dtypes.inference',
        'pandas.core.groupby',
        'pandas.core.indexes',
        'pandas.core.internals',
        'pandas.core.ops',
        'pandas.core.reshape',
        'pandas.core.sparse',
        'pandas.core.tools',
        'pandas.core.util',
        'pandas.io',
        'pandas.io.common',
        'pandas.io.excel',
        'pandas.io.formats',
        'pandas.io.json',
        'pandas.io.parsers',
        'pandas.plotting',
        'pandas.tseries',
        'pandas.util',
        'pandas._libs',
        'pandas._libs.tslib',
        'pandas._libs.tslibs',
        'pandas._libs.tslibs.base',
        'pandas._libs.tslibs.ccalendar',
        'pandas._libs.tslibs.conversion',
        'pandas._libs.tslibs.fields',
        'pandas._libs.tslibs.nattype',
        'pandas._libs.tslibs.np_datetime',
        'pandas._libs.tslibs.offsets',
        'pandas._libs.tslibs.parsing',
        'pandas._libs.tslibs.period',
        'pandas._libs.tslibs.resolution',
        'pandas._libs.tslibs.strptime',
        'pandas._libs.tslibs.timedeltas',
        'pandas._libs.tslibs.timestamps',
        'pandas._libs.tslibs.timezones',
        'pandas._libs.tslibs.tzconversion',
        'pandas._libs.tslibs.vectorized',

        # ✅ NUMPY (NECESSÁRIO PARA PANDAS)
        'numpy',
        'numpy.core',
        'numpy.core.multiarray',
        'numpy.core.umath',
        'numpy.core._multiarray_umath',
        'numpy.linalg',
        'numpy.random',
        'numpy.lib',
        'numpy.lib.format',

        # ✅ DEPENDÊNCIAS DO PANDAS
        'pytz',
        'dateutil',
        'dateutil.parser',
        'dateutil.tz',
        'dateutil.relativedelta',
        'six',

        # Dependências críticas existentes
        'customtkinter',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'polars',
        'polars.io',
        'polars.io.excel',
        'openpyxl',
        'openpyxl.workbook',
        'openpyxl.worksheet',
        'openpyxl.styles',
        'openpyxl.utils',
        'openpyxl.reader',
        'openpyxl.writer',
        'pydantic',
        'pydantic.fields',
        'pydantic.main',
        'loguru',

        # ✅ SQLITE (para banco de fornecedores)
        'sqlite3',

        # ✅ RECURSOS EMBARCADOS
        'tempfile',
        'shutil',

        # Email
        'smtplib',
        'ssl',
        'email',
        'email.mime',
        'email.mime.multipart',
        'email.mime.text',
        'email.mime.base',
        'email.encoders',

        # Sistema
        'pathlib',
        'asyncio',
        'threading',
        'datetime',
        'typing',
        'dataclasses',
        're',
        'json',
        'os',
        'platform',
        'subprocess',
        'time',
        'traceback',
        'sys',
        'io',
        'base64',
        'uuid',
        'hashlib',
        'collections',
        'itertools',
        'functools',
        'weakref',
        'gc',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ✅ CORRIGIDO: Removido pandas e numpy da lista de exclusões
        'matplotlib',
        # 'numpy',  # ← REMOVIDO (necessário para pandas)
        'scipy',
        # 'pandas',  # ← REMOVIDO (necessário para o app)
        'jupyter',
        'IPython',
        'pytest',
        'sphinx',
        'PIL',
        'cv2',
        'tensorflow',
        'torch',
        'sklearn',
        'seaborn',
        'plotly',
        'bokeh',
        'dash',
        'streamlit',
        'flask',
        'django',
        'fastapi',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CadastroAutomaticoD\'Rossi_v2.1',  # ✅ VERSÃO ATUALIZADA
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Interface gráfica
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=logo_file,  # ✅ USA LOGO DINÂMICO
)