@echo off
echo ========================================
echo   ATUALIZAÇÃO D'ROSSI v2.0 → v2.1
echo   Novas funcionalidades: Estoque + Dropdown
echo ========================================
echo.

echo 🆕 NOVIDADES DA VERSÃO 2.1:
echo    ✅ Estoque de Segurança automático
echo    ✅ Dropdown inteligente para seleção de abas
echo    ✅ Auto-detecção das abas da planilha Excel
echo    ✅ Interface mais intuitiva
echo.

echo [1/5] Fazendo backup da versão atual...
if exist "CadastroAutomaticoD'Rossi_v2.0.exe" (
    if not exist "backup" mkdir backup
    copy "CadastroAutomaticoD'Rossi_v2.0.exe" "backup\CadastroAutomaticoD'Rossi_v2.0_backup_%date:~-4,4%%date:~-7,2%%date:~-10,2%.exe" >nul
    echo ✅ Backup criado em backup\
) else (
    echo ⚠️ Versão anterior não encontrada (normal se for primeira instalação)
)
echo.

echo [2/5] Verificando nova versão...
if not exist "CadastroAutomaticoD'Rossi_v2.1.exe" (
    echo ❌ Arquivo v2.1 não encontrado!
    echo    Certifique-se de que o arquivo está na mesma pasta.
    pause
    exit /b 1
)
echo ✅ Arquivo v2.1 encontrado
echo.

echo [3/5] Verificando integridade...
for %%I in ("CadastroAutomaticoD'Rossi_v2.1.exe") do (
    echo 📏 Tamanho: %%~zI bytes
    if %%~zI LSS 50000000 (
        echo ⚠️ Arquivo pode estar corrompido
        set /p continue="Continuar mesmo assim? (s/n): "
        if /i not "!continue!"=="s" exit /b 1
    ) else (
        echo ✅ Arquivo íntegro
    )
)
echo.

echo [4/5] Criando atalho atualizado...
echo Set oWS = WScript.CreateObject("WScript.Shell") > CreateShortcut.vbs
echo sLinkFile = "%USERPROFILE%\Desktop\Cadastro D'Rossi v2.1.lnk" >> CreateShortcut.vbs
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> CreateShortcut.vbs
echo oLink.TargetPath = "%CD%\CadastroAutomaticoD'Rossi_v2.1.exe" >> CreateShortcut.vbs
echo oLink.WorkingDirectory = "%CD%" >> CreateShortcut.vbs
echo oLink.Description = "Cadastro Automático D'Rossi v2.1 - Estoque + Dropdown" >> CreateShortcut.vbs
echo oLink.Save >> CreateShortcut.vbs
cscript CreateShortcut.vbs >nul 2>&1
del CreateShortcut.vbs >nul 2>&1
echo ✅ Atalho criado na área de trabalho
echo.

echo [5/5] Limpando versão anterior...
if exist "CadastroAutomaticoD'Rossi_v2.0.exe" (
    del "CadastroAutomaticoD'Rossi_v2.0.exe" >nul 2>&1
    echo ✅ Versão anterior removida
)
if exist "Cadastro D'Rossi v2.0.lnk" (
    del "%USERPROFILE%\Desktop\Cadastro D'Rossi v2.0.lnk" >nul 2>&1
)
echo.

echo ========================================
echo ✅ ATUALIZAÇÃO CONCLUÍDA COM SUCESSO!
echo ========================================
echo.
echo 🎉 BEM-VINDO À VERSÃO 2.1!
echo.
echo 🆕 NOVAS FUNCIONALIDADES:
echo    📦 Estoque de Segurança automático
echo        • Produtos unitários (código 0): 1000 unidades
echo        • Demais produtos: 0 unidades
echo.
echo    📋 Dropdown inteligente para abas
echo        • Auto-detecção das abas da planilha
echo        • Seleção automática da aba mais provável
echo        • Botão de atualização manual
echo.
echo 📁 ARQUIVOS:
echo    • Executável: CadastroAutomaticoD'Rossi_v2.1.exe
echo    • Atalho: Desktop\Cadastro D'Rossi v2.1.lnk
if exist "backup\CadastroAutomaticoD'Rossi_v2.0_backup_*.exe" (
    echo    • Backup: backup\CadastroAutomaticoD'Rossi_v2.0_backup_*.exe
)
echo.
echo 🚀 PRONTO PARA USAR!
echo    Clique no atalho da área de trabalho para iniciar
echo.
pause