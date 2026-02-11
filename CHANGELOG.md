# Changelog - Cadastro Automático D'Rossi

## [2.1.0] - 2025-10-08
### ✅ Adicionado
- **Nova funcionalidade:** Estoque de Segurança automático
  - Produtos unitários com código "0": 1000 unidades
  - Demais produtos: 0 unidades
- **Nova funcionalidade:** Dropdown automático para seleção de abas
  - Auto-detecção das abas da planilha Excel
  - Seleção inteligente da aba mais provável
  - Botão de atualização manual das abas
- Logs detalhados para rastreamento da lógica de estoque
- Validação aprimorada de tipos de produto

### 🔧 Melhorado
- Interface mais intuitiva para seleção de abas
- Performance geral do processamento
- Validações de dados mais robustas
- Sistema de logs mais detalhado

### 📝 Técnico
- Implementação na classe ProductProcessor
- Campo estoque_seg adicionado ao ProductDestination
- Lógica baseada em tipo_produto e código gerado
- Dropdown automático com ExcelReader.get_sheet_names()

## [2.0.0] - 2024-11-XX
### ✅ Versão anterior
- Sistema base de cadastro automático
- Processamento de produtos, variações, kits
- Integração com fornecedores
- Sistema de precificação