@echo off
chcp 65001 >nul
echo ========================================
echo    CADASTRO AUTOMATICO D'ROSSI v2.1
echo    BUILD E INSTALADOR COMPLETO
echo    Novas funcionalidades: Estoque + Dropdown
echo ========================================
echo.

echo [1/4] Limpando builds anteriores...
if exist "dist" rmdir /s /q "dist" >nul 2>&1
if exist "build" rmdir /s /q "build" >nul 2>&1
echo OK Limpeza concluida
echo.

echo [2/4] Executando build do executavel v2.1...
pyinstaller build_exe.spec

if %ERRORLEVEL% NEQ 0 (
    echo ERRO no build do executavel!
    echo Verifique os erros acima e tente novamente.
    pause
    exit /b 1
)
echo OK Build do executavel concluido
echo.

echo [3/4] Verificando se o build foi bem-sucedido...
if not exist "dist\CadastroAutomaticoD'Rossi_v2.1.exe" (
    echo ERRO Executavel v2.1 nao encontrado! Build falhou.
    echo Verifique os erros acima e tente novamente.
    pause
    exit /b 1
)

echo Verificando tamanho do arquivo...
for %%I in ("dist\CadastroAutomaticoD'Rossi_v2.1.exe") do (
    echo Tamanho do executavel: %%~zI bytes
    if %%~zI LSS 50000000 (
        echo AVISO: Executavel muito pequeno - pode ter problemas
        set /p continue="Continuar mesmo assim? (s/n): "
        if /i not "!continue!"=="s" exit /b 1
    ) else (
        echo OK Executavel v2.1 criado com sucesso
    )
)
echo.

echo [4/4] Criando instalador com Inno Setup...

if not exist "dist\installer" mkdir "dist\installer"

if not exist "installer.iss" (
    echo ERRO: Arquivo installer.iss nao encontrado!
    echo Crie o arquivo installer.iss primeiro
    echo.
    echo Executavel disponivel em: dist\CadastroAutomaticoD'Rossi_v2.1.exe
    pause
    exit /b 0
)

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
    echo ERRO: Inno Setup nao encontrado!
    echo.
    echo PARA INSTALAR O INNO SETUP:
    echo 1. Acesse: https://jrsoftware.org/isinfo.php
    echo 2. Baixe e instale o Inno Setup 6
    echo 3. Execute este script novamente
    echo.
    echo Executavel disponivel em: dist\CadastroAutomaticoD'Rossi_v2.1.exe
    pause
    exit /b 0
)

echo Inno Setup encontrado: %INNO_PATH%
echo Compilando instalador...

%INNO_PATH% installer.iss

if %ERRORLEVEL% NEQ 0 (
    echo ERRO ao criar instalador
    echo Verifique o arquivo installer.iss
    echo.
    echo Executavel disponivel em: dist\CadastroAutomaticoD'Rossi_v2.1.exe
    pause
    exit /b 1
)

if exist "dist\installer\CadastroAutomaticoD'Rossi_v2.1_Setup.exe" (
    echo OK Instalador criado com sucesso!
) else (
    echo AVISO: Instalador nao encontrado no local esperado
)

echo.
echo ========================================
echo OK BUILD E INSTALADOR v2.1 CONCLUIDOS!
echo ========================================
echo.
echo NOVAS FUNCIONALIDADES v2.1:
echo - Estoque de Seguranca automatico
echo - Dropdown inteligente para abas Excel
echo - Interface mais intuitiva
echo.
echo ARQUIVOS GERADOS:
echo Executavel: dist\CadastroAutomaticoD'Rossi_v2.1.exe
if exist "dist\installer\CadastroAutomaticoD'Rossi_v2.1_Setup.exe" (
    echo Instalador: dist\installer\CadastroAutomaticoD'Rossi_v2.1_Setup.exe
)
echo.
echo TAMANHOS DOS ARQUIVOS:
for %%I in ("dist\CadastroAutomaticoD'Rossi_v2.1.exe") do (
    set /a size_mb=%%~zI/1048576
    echo Executavel: %%~zI bytes
)
if exist "dist\installer\CadastroAutomaticoD'Rossi_v2.1_Setup.exe" (
    for %%I in ("dist\installer\CadastroAutomaticoD'Rossi_v2.1_Setup.exe") do (
        echo Instalador: %%~zI bytes
    )
)
echo.
echo PRONTO PARA DISTRIBUICAO!
echo.
pause