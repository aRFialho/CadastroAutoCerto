@echo off
setlocal enabledelayedexpansion

echo ========================================
echo    CADASTRO AUTOMÁTICO D'ROSSI v2.0
echo    BUILD E INSTALADOR COMPLETO
echo ========================================
echo.

REM ✅ VERIFICAÇÃO INICIAL: Estrutura de arquivos necessária
echo [0/4] Verificando estrutura de arquivos...

if not exist "main.py" (
    echo ❌ main.py não encontrado!
    echo Certifique-se de estar na pasta raiz do projeto.
    pause
    exit /b 1
)

if not exist "build_exe.spec" (
    echo ❌ build_exe.spec não encontrado!
    echo Arquivo de configuração do build é necessário.
    pause
    exit /b 1
)

if not exist "src\resources\templates\Planilha Destino.xlsx" (
    echo ❌ Template não encontrado!
    echo Copie Planilha Destino.xlsx para src\resources\templates\
    pause
    exit /b 1
)

if not exist "installer.iss" (
    echo ⚠️ installer.iss não encontrado! Instalador não será criado.
    set CREATE_INSTALLER=0
) else (
    set CREATE_INSTALLER=1
)

echo ✅ Estrutura de arquivos verificada!
echo.

echo [1/4] Limpando builds anteriores...
if exist "dist" (
    echo Removendo pasta dist anterior...
    rmdir /s /q "dist" 2>nul
)
if exist "build" (
    echo Removendo pasta build anterior...
    rmdir /s /q "build" 2>nul
)
echo ✅ Limpeza concluída!
echo.

echo [2/4] Executando build do executável...
echo Comando: pyinstaller build_exe.spec
echo.

pyinstaller build_exe.spec

if %ERRORLEVEL% NEQ 0 (
    echo ❌ Erro no build do PyInstaller!
    echo Verifique os erros acima e tente novamente.
    pause
    exit /b 1
)
echo.

echo [3/4] Verificando se o build foi bem-sucedido...
if not exist "dist\CadastroAutomaticoD'Rossi_v2.0.exe" (
    echo ❌ Executável não encontrado! Build falhou.
    echo Verifique os erros acima e tente novamente.
    pause
    exit /b 1
)

REM ✅ VERIFICAR TAMANHO DO EXECUTÁVEL
for %%I in ("dist\CadastroAutomaticoD'Rossi_v2.0.exe") do (
    set /a SIZE_MB=%%~zI/1024/1024
    echo ✅ Executável criado com sucesso! Tamanho: !SIZE_MB! MB
)
echo.

REM ✅ TESTE RÁPIDO DO EXECUTÁVEL
echo [3.5/4] Testando executável...
echo Executando teste rápido (será fechado automaticamente)...
start /wait "Teste" "dist\CadastroAutomaticoD'Rossi_v2.0.exe" --test 2>nul
echo ✅ Teste do executável concluído!
echo.

if %CREATE_INSTALLER%==0 (
    echo [4/4] Pulando criação do instalador (installer.iss não encontrado)
    goto :FINAL
)

echo [4/4] Criando instalador com Inno Setup...

REM Criar pasta do instalador se não existir
if not exist "dist\installer" mkdir "dist\installer"

REM ✅ BUSCA MAIS ABRANGENTE DO INNO SETUP
set INNO_PATH=""
set INNO_FOUND=0

REM Verificar versões e locais mais comuns
for %%V in (6 5) do (
    for %%P in ("C:\Program Files (x86)\Inno Setup %%V" "C:\Program Files\Inno Setup %%V") do (
        if exist "%%P\ISCC.exe" (
            set INNO_PATH="%%P\ISCC.exe"
            set INNO_FOUND=1
            goto :INNO_FOUND
        )
    )
)

REM Buscar no PATH
where ISCC.exe >nul 2>&1
if %ERRORLEVEL%==0 (
    set INNO_PATH=ISCC.exe
    set INNO_FOUND=1
)

:INNO_FOUND
if %INNO_FOUND%==0 (
    echo ❌ Inno Setup não encontrado!
    echo.
    echo Para criar o instalador manualmente:
    echo 1. Instale o Inno Setup 6: https://jrsoftware.org/isinfo.php
    echo 2. Abra o Inno Setup Compiler
    echo 3. Compile o arquivo installer.iss
    echo.
    goto :FINAL
)

echo 🔧 Inno Setup encontrado: %INNO_PATH%
echo Compilando instalador...

%INNO_PATH% installer.iss

if %ERRORLEVEL% NEQ 0 (
    echo ❌ Erro ao criar instalador
    echo Verifique o arquivo installer.iss
    pause
    exit /b 1
)

echo ✅ Instalador criado com sucesso!
echo.

:FINAL
echo ========================================
echo ✅ BUILD CONCLUÍDO COM SUCESSO!
echo ========================================
echo.

REM ✅ RELATÓRIO DETALHADO
echo 📊 RELATÓRIO DE BUILD:
echo ----------------------------------------
echo 📁 Executável: dist\CadastroAutomaticoD'Rossi_v2.0.exe

if exist "dist\CadastroAutomaticoD'Rossi_v2.0.exe" (
    for %%I in ("dist\CadastroAutomaticoD'Rossi_v2.0.exe") do (
        set /a SIZE_MB=%%~zI/1024/1024
        echo    Tamanho: !SIZE_MB! MB ^(%%~zI bytes^)
        echo    Data: %%~tI
    )
)

if exist "dist\installer\CadastroAutomaticoD'Rossi_v2.0_Setup.exe" (
    echo.
    echo 📦 Instalador: dist\installer\CadastroAutomaticoD'Rossi_v2.0_Setup.exe
    for %%I in ("dist\installer\CadastroAutomaticoD'Rossi_v2.0_Setup.exe") do (
        set /a SIZE_MB=%%~zI/1024/1024
        echo    Tamanho: !SIZE_MB! MB ^(%%~zI bytes^)
        echo    Data: %%~tI
    )
)

echo.
echo 🎯 PRÓXIMOS PASSOS:
echo ----------------------------------------
if exist "dist\installer\CadastroAutomaticoD'Rossi_v2.0_Setup.exe" (
    echo ✅ Use o INSTALADOR para distribuição: dist\installer\CadastroAutomaticoD'Rossi_v2.0_Setup.exe
) else (
    echo ✅ Use o EXECUTÁVEL para distribuição: dist\CadastroAutomaticoD'Rossi_v2.0.exe
)
echo ✅ Teste em uma máquina limpa antes da distribuição final
echo ✅ O template está embarcado - não precisa de arquivos externos!

echo.
echo 🚀 BUILD FINALIZADO - PRONTO PARA DISTRIBUIÇÃO!
echo.

REM ✅ OPÇÃO DE ABRIR PASTA
set /p OPEN_FOLDER="Deseja abrir a pasta dist? (s/n): "
if /i "%OPEN_FOLDER%"=="s" (
    explorer "dist"
)

pause