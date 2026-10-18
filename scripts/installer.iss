; PrintScale Studio - Inno Setup Installer Script
; Produces a standard Windows desktop installer with Start Menu shortcuts and safe uninstallation.

#define MyAppName "PrintScale Studio"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.6"
#endif
#define MyAppPublisher "VitalRove"
#define MyAppURL "https://github.com/baki2222/printscale-studio"
#define MyAppExeName "PrintScaleStudio.exe"
; Brand icon as bundled by PyInstaller. Shortcuts point at this file (a path that did not exist before
; 1.0.5), so upgraded shortcuts cannot reuse a shell-cached icon of the 1.0.4 EXE path.
#define MyAppIconRel "_internal\printscale\assets\brand\PrintScaleStudio_Windows.ico"

[Setup]
AppId={{D37E6B20-5A38-4C23-9F9B-1B4422A5C7F0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
OutputBaseFilename=PrintScaleStudio_Setup_v{#MyAppVersion}
OutputDir=..\dist
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
SetupIconFile=..\printscale\assets\brand\PrintScaleStudio_Windows.ico
UninstallDisplayIcon={app}\{#MyAppIconRel}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Remove application files left by v1.0.1 (duplicate model copies incl. PyTorch .pth files, dev launcher,
; and the previous runtime folder) so an upgrade does not keep stale binaries. User data lives in
; %APPDATA%\PrintScaleStudio and exports live wherever the user saved them; neither is touched.
Type: filesandordirs; Name: "{app}\models"
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\licenses"
Type: files; Name: "{app}\PrintScaleStudio.bat"

[Files]
; Copy all files from the standalone portable build directory
Source: "..\dist\PrintScaleStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIconRel}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIconRel}"; Tasks: desktopicon

[Run]
Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Filename: "{app}\{#MyAppExeName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only clean up temporary logs, never delete user exports
Type: files; Name: "{app}\*.log"

[Code]
// The Start menu keeps its own tile for an existing shortcut, so after an upgrade from 1.0.4 it kept
// showing the old icon although the .lnk now points at the brand ICO. Notify the shell about this
// app's own shortcuts only; global icon caches and other applications are not touched.
procedure SHChangeNotify(wEventId: Integer; uFlags: Cardinal; dwItem1: String; dwItem2: Cardinal);
  external 'SHChangeNotify@shell32.dll stdcall';

procedure RefreshShortcut(const Path: String);
begin
  if FileExists(Path) then
    SHChangeNotify($00002000 {SHCNE_UPDATEITEM}, $00001005 {SHCNF_PATHW or SHCNF_FLUSH}, Path, 0);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    RefreshShortcut(ExpandConstant('{autoprograms}\{#MyAppName}.lnk'));
    RefreshShortcut(ExpandConstant('{autodesktop}\{#MyAppName}.lnk'));
  end;
end;
