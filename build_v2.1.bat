@echo off
echo ========================================
echo    CADASTRO AUTOMÁTICO D'ROSSI v2.1
echo    BUILD E INSTALADOR COMPLETO
echo    Novas funcionalidades: Estoque + Dropdown
echo ========================================
echo.

echo [1/4] Limpando builds anteriores...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
echo ✅ Limpeza concluída
echo.

echo [2/4] Executando build do executável v2.1...
pyinstaller build_exe.spec
echo.

echo [3/4] Verificando se o build foi bem-sucedido...
if not exist "dist\CadastroAutomaticoD'Rossi_v2.1.exe" (
    echo ❌ Executável v2.1 não encontrado! Build falhou.
    echo Verifique os erros acima e tente novamente.
    pause
    exit /b 1
)
echo ✅ Executável v2.1 criado com sucesso!

echo.
echo [4/4] Verificando tamanho e integridade...
for %%I in ("dist\CadastroAutomaticoD'Rossi_v2.1.exe") do (
    echo 📏 Tamanho: %%~zI bytes
    if %%~zI LSS 50000000 (
        echo ⚠️ Arquivo muito pequeno, pode ter problemas
    ) else (
        echo ✅ Tamanho adequado
    )
)

echo.
echo ========================================
echo ✅ BUILD v2.1 CONCLUÍDO COM SUCESSO!
echo ========================================
echo.
echo 🆕 NOVAS FUNCIONALIDADES v2.1:
echo    ✅ Estoque de Segurança automático
echo    ✅ Dropdown inteligente para abas Excel
echo    ✅ Auto-seleção da aba mais provável
echo    ✅ Interface melhorada
echo.
echo 📁 Arquivo gerado:
echo    dist\CadastroAutomaticoD'Rossi_v2.1.exe
echo.
echo 🚀 Pronto para distribuição!
echo.
pause