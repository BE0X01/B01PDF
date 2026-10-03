#define AppVersion "0.7.0"
[Setup]
AppId={{D9766A7B-123B-426D-8E04-108F11816A65}
AppName=B01PDF
UninstallDisplayName=B01PDF
SetupIconFile=..\assets\B01PDF.ico
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

[Code]
function GetCurrentProcessId: LongWord;
  external 'GetCurrentProcessId@kernel32.dll stdcall';

procedure DeinitializeSetup();
var
  Folder, Name, Script, Parameters: String;
  ResultCode: Integer;
begin
  Folder := ExtractFileDir(ExpandConstant('{srcexe}'));
  Name := ExtractFileName(Folder);
  { Delete only our installer in a dedicated update folder, never other files. }
  if (Pos('B01PDF-update-', Name) <> 1) or
     (CompareText(ExtractFileName(ExpandConstant('{srcexe}')), 'B01PDF-Setup.exe') <> 0) then
    Exit;
  StringChangeEx(Folder, '''', '''''', True);
  Script := '$p=Get-Process -Id ' + IntToStr(GetCurrentProcessId()) +
    ' -ErrorAction SilentlyContinue; if($p){$p.WaitForExit()}; ' +
    '$d=''' + Folder + '''; for($i=0;$i -lt 60;$i++){' +
    'try {Remove-Item -LiteralPath ($d+''\B01PDF-Setup.exe'') -Force -ErrorAction Stop; ' +
    '[System.IO.Directory]::Delete($d); break}' +
    'catch {Start-Sleep -Seconds 1}}';
  Parameters := '-NoProfile -NonInteractive -WindowStyle Hidden -Command "' + Script + '"';
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    Parameters, '', SW_HIDE, ewNoWait, ResultCode);
end;
