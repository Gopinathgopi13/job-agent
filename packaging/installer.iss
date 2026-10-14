; Inno Setup script -> JobSprint-Setup.exe
; Compile with: ISCC.exe packaging\installer.iss
; Requires the PyInstaller onedir build to already exist at dist\JobSprint\
; (see packaging\jobsprint.spec).
;
; Installs per-user, no admin rights required, to %LOCALAPPDATA%\Programs\JobSprint
; — deliberately NOT the same folder as the app's own data
; (%LOCALAPPDATA%\JobSprint, see jobsprint\paths.py), so uninstalling the program
; never touches the user's profile/knowledge base/Excel tracker.

#define MyAppName "JobSprint"
#define MyAppVersion "1.0.0"
#define MyAppExeName "JobSprint.exe"
#define MyAppPublisher "JobSprint"

[Setup]
AppId={{2F3B7C9E-4B7E-4F6B-9C8E-3A1D6E7C5B10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist_installer
OutputBaseFilename=JobSprint-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\JobSprint\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
