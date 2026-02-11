@echo off
echo ========================================
echo    CADASTRO AUTOMÁTICO D'ROSSI v2.1
echo    BUILD E INSTALADOR COMPLETO
echo    Novas funcionalidades: Estoque + Dropdown
echo ========================================
echo.

echo [1/4] Limpando builds anteriores...
if exist "dist" rmdir /s /q "dist" >nul 2>&1
if exist "build" rmdir /s /q "build" >nul 2>&1
echo ✅ Limpeza concluída
echo.

echo [2/4] Executando build do executável v2.1...
pyinstaller build_exe.spec

if %ERRORLEVEL% NEQ 0 (
    echo ❌ Erro no build do executável!
    echo Verifique os erros acima e tente novamente.
    pause
    exit /b 1
)
echo ✅ Build do executável concluído
echo.

echo [3/4] Verificando se o build foi bem-sucedido...
if not exist "dist\CadastroAutomaticoD'Rossi_v2.1.exe" (
    echo ❌ Executável v2.1 não encontrado! Build falhou.
    echo Verifique os erros acima e tente novamente.
    pause
    exit /b 1
)

REM Verificar tamanho mínimo do executável
for %%I in ("dist\CadastroAutomaticoD'Rossi_v2.1.exe") do (
    if %%~zI LSS 50000000 (
        echo ⚠️ Executável muito pequeno (%%~zI bytes) - pode ter problemas
        set /p continue="Continuar mesmo assim? (s/n): "
        if /i not "!continue!"=="s" exit /b 1
    ) else (
        echo ✅ Executável v2.1 criado com sucesso (%%~zI bytes)
    )
)
echo.

echo [4/4] Criando instalador com Inno Setup...

REM Criar pasta do instalador se não existir
if not exist "dist\installer" mkdir "dist\installer"

REM Verificar se existe arquivo installer.iss
if not exist "installer.iss" (
    echo ❌ Arquivo installer.iss não encontrado!
    echo    Crie o arquivo installer.iss primeiro
    echo.
    echo 📁 Executável disponível em: dist\CadastroAutomaticoD'Rossi_v2.1.exe
    pause
    exit /b 0
)

REM Tentar encontrar o Inno Setup
set INNO_PATH=""
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set INNO_PATH="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set INNO_PATH="C:\Program Files\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" (
    set INNO_PATH="C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 5\ISCC.exe" (
    set INNO_PATH="C:\Program Files\Inno Setup 5\ISCC.exe"
)

if %INNO_PATH%=="" (
    echo ❌ Inno Setup não encontrado!
    echo.
    echo 📥 PARA INSTALAR O INNO SETUP:
    echo    1. Acesse: https://jrsoftware.org/isinfo.php
    echo    2. Baixe e instale o Inno Setup 6
    echo    3. Execute este script novamente
    echo.
    echo �� Executável disponível em: dist\CadastroAutomaticoD'Rossi_v2.1.exe
    echo 💡 Você pode distribuir apenas o executável se preferir
    pause
    exit /b 0
)

echo 🔧 Inno Setup encontrado: %INNO_PATH%
echo 📝 Compilando instalador...

%INNO_PATH% installer.iss

if %ERRORLEVEL% NEQ 0 (
    echo ❌ Erro ao criar instalador
    echo    Verifique o arquivo installer.iss
    echo.
    echo 📁 Executável disponível em: dist\CadastroAutomaticoD'Rossi_v2.1.exe
    pause
    exit /b 1
)

REM Verificar se instalador foi criado
if exist "dist\installer\CadastroAutomaticoD'Rossi_v2.1_Setup.exe" (
    echo ✅ Instalador criado com sucesso!
) else (
    echo ⚠️ Instalador não encontrado no local esperado
    echo    Verifique a configuração OutputDir no installer.iss
)

echo.
echo ========================================
echo ✅ BUILD E INSTALADOR v2.1 CONCLUÍDOS!
echo ========================================
echo.
echo 🆕 NOVAS FUNCIONALIDADES v2.1:
echo    ✅ Estoque de Segurança automático
echo       • Produtos unitários (código 0): 1000 unidades
echo       • Demais produtos: 0 unidades
echo    ✅ Dropdown inteligente para abas Excel
echo       • Auto-detecção das abas da planilha
echo       • Seleção automática da aba mais provável
echo       • Não precisa mais digitar nome da aba!
echo    ✅ Interface mais intuitiva e amigável
echo.
echo 📁 ARQUIVOS GERADOS:
echo    Executável: dist\CadastroAutomaticoD'Rossi_v2.1.exe
if exist "dist\installer\CadastroAutomaticoD'Rossi_v2.1_Setup.exe" (
    echo    Instalador: dist\installer\CadastroAutomaticoD'Rossi_v2.1_Setup.exe
)
echo.
echo 🎯 TAMANHOS DOS ARQUIVOS:
for %%I in ("dist\CadastroAutomaticoD'Rossi_v2.1.exe") do (
    set /a size_mb=%%~zI/1048576
    echo    Executável: %%~zI bytes (~!size_mb! MB)
)
if exist "dist\installer\CadastroAutomaticoD'Rossi_v2.1_Setup.exe" (
    for %%I in ("dist\installer\CadastroAutomaticoD'Rossi_v2.1_Setup.exe") do (
        set /a size_mb=%%~zI/1048576
        echo    Instalador: %%~zI bytes (~!size_mb! MB)
    )
)
echo.
echo 🚀 PRONTO PARA DISTRIBUIÇÃO!
echo.
echo 📱 PARA DISTRIBUIR VIA CHAT:
echo    1. Faça upload do instalador para Google Drive/OneDrive
echo    2. Gere link compartilhável
echo    3. Envie nos grupos de WhatsApp/Telegram
echo    4. Inclua as instruções de instalação
echo.
echo 💡 DICA: Use o instalador para distribuição mais fácil
echo    Os usuários só precisam baixar e executar!
echo.
pause