@echo off
echo ========================================
echo   CRIANDO INSTALADOR D'ROSSI v2.1
echo   Atualização: Estoque + Dropdown
echo ========================================
echo.

echo [1/6] Verificando pré-requisitos...

REM Verificar se executável existe
if not exist "dist\CadastroAutomaticoD'Rossi_v2.1.exe" (
    echo ❌ Executável v2.1 não encontrado!
    echo    Execute primeiro: build_v2.1.bat
    pause
    exit /b 1
)
echo ✅ Executável v2.1 encontrado

REM Verificar Inno Setup
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
    echo 📥 INSTALE O INNO SETUP:
    echo    1. Acesse: https://jrsoftware.org/isinfo.php
    echo    2. Baixe e instale o Inno Setup 6
    echo    3. Execute este script novamente
    pause
    exit /b 1
)
echo ✅ Inno Setup encontrado: %INNO_PATH%
echo.

echo [2/6] Criando estrutura de diretórios...
if not exist "dist\installer" mkdir "dist\installer"
echo ✅ Diretórios criados
echo.

echo [3/6] Verificando arquivos necessários...
if not exist "CHANGELOG.md" (
    echo ⚠️ CHANGELOG.md não encontrado, criando...
    echo # Changelog v2.1 > CHANGELOG.md
    echo Estoque de Segurança + Dropdown inteligente >> CHANGELOG.md
)

if not exist "README.md" (
    echo ⚠️ README.md não encontrado, criando...
    echo # Cadastro Automático D'Rossi v2.1 > README.md
)

if not exist "logo-CAD.ico" (
    echo ⚠️ Ícone não encontrado, instalador será criado sem ícone
)
echo ✅ Arquivos verificados
echo.

echo [4/6] Compilando instalador...
%INNO_PATH% installer_v2.1.iss

if %ERRORLEVEL% NEQ 0 (
    echo ❌ Erro ao compilar instalador!
    echo    Verifique o arquivo installer_v2.1.iss
    pause
    exit /b 1
)
echo ✅ Instalador compilado com sucesso!
echo.

echo [5/6] Verificando instalador gerado...
if exist "dist\installer\CadastroAutomaticoD'Rossi_v2.1_Setup.exe" (
    for %%I in ("dist\installer\CadastroAutomaticoD'Rossi_v2.1_Setup.exe") do (
        echo ✅ Instalador criado: %%~nxI
        echo 📏 Tamanho: %%~zI bytes

        REM Verificar se o tamanho é razoável (maior que 50MB)
        if %%~zI LSS 52428800 (
            echo ⚠️ Instalador pode estar incompleto (menor que 50MB)
        ) else (
            echo ✅ Tamanho adequado
        )
    )
) else (
    echo ❌ Instalador não foi gerado!
    pause
    exit /b 1
)
echo.

echo [6/6] Criando arquivo de informações...
echo INSTALADOR CADASTRO AUTOMÁTICO D'ROSSI v2.1 > "dist\installer\INFORMACOES.txt"
echo ============================================== >> "dist\installer\INFORMACOES.txt"
echo. >> "dist\installer\INFORMACOES.txt"
echo 📦 ARQUIVO: CadastroAutomaticoD'Rossi_v2.1_Setup.exe >> "dist\installer\INFORMACOES.txt"
echo 📅 DATA: %date% %time% >> "dist\installer\INFORMACOES.txt"
echo 💻 SISTEMA: Windows 10/11 (64-bit) >> "dist\installer\INFORMACOES.txt"
echo. >> "dist\installer\INFORMACOES.txt"
echo 🆕 NOVIDADES v2.1: >> "dist\installer\INFORMACOES.txt"
echo • Estoque de Segurança automático >> "dist\installer\INFORMACOES.txt"
echo • Dropdown inteligente para abas Excel >> "dist\installer\INFORMACOES.txt"
echo • Interface mais intuitiva >> "dist\installer\INFORMACOES.txt"
echo. >> "dist\installer\INFORMACOES.txt"
echo 📋 INSTALAÇÃO: >> "dist\installer\INFORMACOES.txt"
echo 1. Execute o arquivo .exe como administrador >> "dist\installer\INFORMACOES.txt"
echo 2. Siga as instruções na tela >> "dist\installer\INFORMACOES.txt"
echo 3. A versão anterior será preservada como backup >> "dist\installer\INFORMACOES.txt"
echo. >> "dist\installer\INFORMACOES.txt"
echo ✅ Pronto para distribuição! >> "dist\installer\INFORMACOES.txt"

echo ========================================
echo ✅ INSTALADOR v2.1 CRIADO COM SUCESSO!
echo ========================================
echo.
echo 📁 LOCALIZAÇÃO:
echo    dist\installer\CadastroAutomaticoD'Rossi_v2.1_Setup.exe
echo.
echo 📊 INFORMAÇÕES:
for %%I in ("dist\installer\CadastroAutomaticoD'Rossi_v2.1_Setup.exe") do (
    echo    Tamanho: %%~zI bytes (%.1f MB)
    set /a size_mb=%%~zI/1048576
    echo    Tamanho: !size_mb! MB aproximadamente
)
echo.
echo 🚀 PRONTO PARA DISTRIBUIÇÃO:
echo    ✅ Envie por WhatsApp/Telegram/Email
echo    ✅ Upload para Google Drive/OneDrive
echo    ✅ Compartilhe o link de download
echo.
echo 📋 INSTRUÇÕES PARA USUÁRIOS:
echo    1. Baixar o arquivo
echo    2. Executar como administrador
echo    3. Seguir o assistente de instalação
echo    4. Usar o novo atalho criado
echo.
pause