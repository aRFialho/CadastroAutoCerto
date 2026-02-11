#define MyAppName "Cadastro Automático D'Rossi"
#define MyAppVersion "2.1.0"
#define MyAppPublisher "D'Rossi"
#define MyAppExeName "CadastroAutomaticoD'Rossi_v2.1.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-123456789012}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=dist\installer
OutputBaseFilename=CadastroAutomaticoD'Rossi_v2.1_Setup
Compression=lzma
SolidCompression=yes

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Cadastro Automático D'Rossi"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Cadastro Automático D'Rossi"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Executar Cadastro Automático D'Rossi"; Flags: nowait postinstall skipifsilent