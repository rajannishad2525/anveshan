; ANVESHAN offline installer. Everything it needs is inside the setup file;
; it never touches the network.

#define AppName    "ANVESHAN"
#define AppVersion "0.9.7"
#define AppExe     "runtime\ANVESHAN.exe"

[Setup]
AppId={{477A2EDA-2931-47C9-B501-9CF1BD4D140B}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Team ANVESHAN
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=anveshan.ico
OutputDir=.
OutputBaseFilename=ANVESHAN-Setup-{#AppVersion}-x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/fast
SolidCompression=yes
PrivilegesRequired=admin
; Sites that will not hand out admin rights can install per-user instead.
PrivilegesRequiredOverridesAllowed=dialog commandline
WizardStyle=modern
DisableProgramGroupPage=yes

[Files]
Source: "ANVESHAN\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Only unpacked when the runtime is actually missing.
Source: "prereq\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; DestDir: "{tmp}"; \
    Flags: deleteafterinstall; Check: WebView2Missing

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; \
    Parameters: """{app}\desktop.py"""; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; \
    Parameters: """{app}\desktop.py"""; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; Parameters: "/silent /install"; \
    StatusMsg: "Installing Microsoft Edge WebView2 Runtime (offline)..."; \
    Check: WebView2Missing; Flags: waituntilterminated
Filename: "{app}\{#AppExe}"; Parameters: """{app}\desktop.py"""; \
    Description: "Start {#AppName}"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; Python writes __pycache__ into every package directory at runtime, and the
; uninstaller only tracks files it installed, so sweep the whole folder. The
; operator's archive lives under LOCALAPPDATA and is never touched.
Type: filesandordirs; Name: "{app}"

[Code]
const
  WV2 = 'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function WebView2Missing: Boolean;
var
  version: String;
begin
  Result := not (
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\' + WV2, 'pv', version) or
    RegQueryStringValue(HKLM, 'SOFTWARE\' + WV2, 'pv', version) or
    RegQueryStringValue(HKCU, 'SOFTWARE\' + WV2, 'pv', version));
end;
