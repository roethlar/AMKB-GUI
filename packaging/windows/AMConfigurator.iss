#ifndef MyAppVersion
  #error MyAppVersion must be supplied with /DMyAppVersion=...
#endif
#ifndef MySourceDir
  #error MySourceDir must be supplied with /DMySourceDir=...
#endif
#ifndef MyOutputDir
  #error MyOutputDir must be supplied with /DMyOutputDir=...
#endif
#ifndef MyOutputBaseFilename
  #error MyOutputBaseFilename must be supplied with /DMyOutputBaseFilename=...
#endif

[Setup]
AppId={{CA237A4C-E91A-4D31-9225-0438A8102ED6}
AppName=OpenKeeb
AppVersion={#MyAppVersion}
AppPublisher=AMKB-GUI contributors
AppPublisherURL=https://github.com/roethlar/AMKB-GUI
AppSupportURL=https://github.com/roethlar/AMKB-GUI/issues
DefaultDirName={localappdata}\Programs\OpenKeeb
DefaultGroupName=OpenKeeb
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
UsedUserAreasWarning=no
OutputDir={#MyOutputDir}
OutputBaseFilename={#MyOutputBaseFilename}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\OpenKeeb.exe
SetupIconFile=..\..\assets\openkeeb.ico
LicenseFile=..\..\LICENSE
CloseApplications=yes

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\OpenKeeb"; Filename: "{app}\OpenKeeb.exe"
Name: "{autodesktop}\OpenKeeb"; Filename: "{app}\OpenKeeb.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\OpenKeeb.exe"; Description: "Launch OpenKeeb"; Flags: nowait postinstall skipifsilent
