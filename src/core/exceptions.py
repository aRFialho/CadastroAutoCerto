"""Exceções customizadas do sistema"""

class CadastroError(Exception):
    """Exceção base do sistema"""
    pass

class ExcelProcessingError(CadastroError):
    """Erro no processamento de planilhas Excel"""
    pass

class ValidationError(CadastroError):
    """Erro de validação de dados"""
    pass

class EmailError(CadastroError):
    """Erro no envio de e-mail"""
    pass

class ConfigurationError(CadastroError):
    """Erro de configuração"""
    pass

# Adicionar esta exceção ao arquivo existente:

class EmailSendError(CadastroError):
    """Erro no envio de e-mail"""
    pass