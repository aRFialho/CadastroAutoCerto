"""Componentes da interface gráfica"""

# Imports opcionais para evitar erros se algum componente não existir
try:
    from .supplier_manager import SupplierManagerWindow
except ImportError:
    SupplierManagerWindow = None

try:
    from .progress_dialog import ProgressDialog
except ImportError:
    ProgressDialog = None

try:
    from .log_viewer import LogViewer
except ImportError:
    LogViewer = None

__all__ = ['SupplierManagerWindow', 'ProgressDialog', 'LogViewer']