; Inno Setup script — wraps the PyInstaller build of GPU Check into a
; downloadable Windows installer (GPU-Check-Setup.exe), Anaconda-style wizard.
;
; Prerequisite: build the app first so dist\GPU Check\ exists:
;     powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -WithTorch
; Then compile this script with Inno Setup (https://jrsoftware.org/isdl.php):
;     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer_windows.iss
; Output: installer_out\GPU-Check-Setup.exe

#define MyAppName "GPU Check"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "GPU-Perf"
#define MyAppExeName "GPU Check.exe"

[Setup]
; A stable, unique app id (keep constant across versions for clean upgrades).
AppId={{7F3A9C21-4D8E-4B6A-9E12-GPUPERFCHECK01}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\installer_out
OutputBaseFilename=GPU-Check-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
; Big builds (with torch) — allow the installer to exceed 2GB internally.
DiskSpanning=no

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 아이콘 만들기"; GroupDescription: "추가 아이콘:"; Flags: checkedonce

[Files]
; The whole PyInstaller output folder (built at repo root: dist\GPU Check\).
Source: "..\dist\GPU Check\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "지금 실행"; Flags: nowait postinstall skipifsilent
