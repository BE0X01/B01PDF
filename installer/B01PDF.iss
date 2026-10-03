#define AppVersion "0.3.0"
[Setup]
AppId={{D9766A7B-123B-426D-8E04-108F11816A65}
AppName=B01PDF
AppVersion={#AppVersion}
AppPublisher=B01
DefaultDirName={autopf}\B01PDF
DefaultGroupName=B01PDF
PrivilegesRequired=admin
UsePreviousAppDir=no
OutputDir=..\dist\installer
OutputBaseFilename=B01PDF-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\B01PDF.exe
[Files]
Source: "..\dist\B01PDF\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\B01PDF"; Filename: "{app}\B01PDF.exe"
Name: "{autodesktop}\B01PDF"; Filename: "{app}\B01PDF.exe"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Run]
Filename: "{app}\B01PDF.exe"; Description: "Launch B01PDF"; Flags: nowait postinstall skipifsilent
