; ========================================
; INSTALADOR CADASTRO AUTOMÁTICO D'ROSSI v2.1
; Atualização com Estoque de Segurança + Dropdown
; ========================================

[Setup]
AppName=Cadastro Automático D'Rossi
AppVersion=2.1.0
AppPublisher=D'Rossi Interiores
AppPublisherURL=https://drossiinteriores.com.br
AppSupportURL=https://drossiinteriores.com.br/suporte
AppUpdatesURL=https://drossiinteriores.com.br/downloads
DefaultDirName={autopf}\DRossi\CadastroAutomatico
DefaultGroupName=D'Rossi Cadastro Automático
AllowNoIcons=yes
LicenseFile=
InfoBeforeFile=
InfoAfterFile=
OutputDir=dist\installer
OutputBaseFilename=CadastroAutomaticoD'Rossi_v2.1_Setup
SetupIconFile=logo-CAD.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

; ✅ CONFIGURAÇÕES DE ATUALIZAÇÃO
AppId={{B8F8F8F8-1234-5678-9ABC-DEF012345678}
UninstallDisplayName=Cadastro Automático D'Rossi v2.1
UninstallDisplayIcon={app}\CadastroAutomaticoD'Rossi_v2.1.exe
VersionInfoVersion=2.1.0.0
VersionInfoCompany=D'Rossi Interiores
VersionInfoDescription=Sistema de Cadastro Automático v2.1
VersionInfoCopyright=© 2025 D'Rossi Interiores

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos adicionais:"; Flags: unchecked
Name: "quicklaunchicon"; Description: "Criar atalho na barra de tarefas"; GroupDescription: "Atalhos adicionais:"; Flags: unchecked

[Files]
; ✅ EXECUTÁVEL PRINCIPAL
Source: "dist\CadastroAutomaticoD'Rossi_v2.1.exe"; DestDir: "{app}"; Flags: ignoreversion
; ✅ DOCUMENTAÇÃO
Source: "CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
; ✅ ÍCONE
Source: "logo-CAD.ico"; DestDir: "{app}"; Flags: ignoreversion
; ✅ TEMPLATES (SE EXISTIREM)
Source: "src\resources\templates\*"; DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: DirExists('src\resources\templates')

[Icons]
Name: "{group}\Cadastro Automático D'Rossi v2.1"; Filename: "{app}\CadastroAutomaticoD'Rossi_v2.1.exe"; IconFilename: "{app}\logo-CAD.ico"
Name: "{group}{cm:UninstallProgram,Cadastro Automático D'Rossi}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Cadastro D'Rossi v2.1"; Filename: "{app}\CadastroAutomaticoD'Rossi_v2.1.exe"; IconFilename: "{app}\logo-CAD.ico"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\Cadastro D'Rossi v2.1"; Filename: "{app}\CadastroAutomaticoD'Rossi_v2.1.exe"; IconFilename: "{app}\logo-CAD.ico"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\CadastroAutomaticoD'Rossi_v2.1.exe"; Description: "Executar Cadastro Automático D'Rossi v2.1"; Flags: nowait postinstall skipifsilent

; ✅ CÓDIGO PASCAL PARA DETECÇÃO DE VERSÃO ANTERIOR
[Code]
var
  PreviousVersionFound: Boolean;
  PreviousVersionPath: String;

function InitializeSetup(): Boolean;
var
  OldPath: String;
begin
  Result := True;
  PreviousVersionFound := False;

  // Verificar se existe versão anterior
  if RegQueryStringValue(HKEY_LOCAL_MACHINE, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall{B8F8F8F8-1234-5678-9ABC-DEF012345678}_is1', 'InstallLocation', OldPath) then
  begin
    PreviousVersionFound := True;
    PreviousVersionPath := OldPath;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  BackupDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Criar pasta de backup se versão anterior foi encontrada
    if PreviousVersionFound then
    begin
      BackupDir := ExpandConstant('{app}\backup');
      CreateDir(BackupDir);

      // Fazer backup da versão anterior (se existir)
      if FileExists(PreviousVersionPath + '\CadastroAutomaticoD''Rossi_v2.0.exe') then
      begin
        FileCopy(PreviousVersionPath + '\CadastroAutomaticoD''Rossi_v2.0.exe',
                BackupDir + '\CadastroAutomaticoD''Rossi_v2.0_backup.exe', False);
      end;
    end;

    // Criar pastas necessárias
    CreateDir(ExpandConstant('{app}\outputs'));
    CreateDir(ExpandConstant('{app}\logs'));
    CreateDir(ExpandConstant('{app}\temp'));
  end;
end;

[Messages]
; ✅ MENSAGENS CUSTOMIZADAS EM PORTUGUÊS
WelcomeLabel1=Bem-vindo ao Assistente de Instalação do Cadastro Automático D'Rossi v2.1
WelcomeLabel2=Este assistente irá instalar a versão 2.1 do Sistema de Cadastro Automático D'Rossi em seu computador.%n%n🆕 NOVIDADES DA VERSÃO 2.1:%n• Estoque de Segurança automático%n• Dropdown inteligente para seleção de abas%n• Interface mais intuitiva%n• Melhor experiência do usuário%n%nRecomenda-se fechar todos os outros aplicativos antes de continuar.
ClickNext=Clique em Avançar para continuar.
ClickInstall=Clique em Instalar para iniciar a instalação.
ClickFinish=Clique em Concluir para finalizar a instalação.

[CustomMessages]
brazilianportuguese.NewFeatures=🆕 NOVIDADES DA VERSÃO 2.1:%n%n✅ ESTOQUE DE SEGURANÇA AUTOMÁTICO%n   • Produtos unitários: 1000 unidades%n   • Demais produtos: 0 unidades%n%n✅ DROPDOWN INTELIGENTE%n   • Auto-detecção das abas Excel%n   • Seleção automática da aba mais provável%n   • Não precisa mais digitar o nome da aba!%n%n✅ MELHORIAS GERAIS%n   • Interface mais intuitiva%n   • Validações aprimoradas%n   • Logs mais detalhados