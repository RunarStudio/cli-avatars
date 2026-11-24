; Per-user CLI Avatars installer.
; Requires Inno Setup 6.6 or newer (CreateCustomForm takes a client size).
; Compile from the repo root with ISCC, or via tools/build_installer.py.
; App files go to {localappdata}\Programs\CLI Avatars.
; App data stays in {localappdata}\cli-avatars and is deleted only when
; the uninstall checkbox is ticked. A silent uninstall keeps app data.

#if Ver < 0x06060000
  #error CLI Avatars requires Inno Setup 6.6 or newer.
#endif

#ifndef AppVersion
  #define AppVersion "0.4.0"
#endif
#ifndef AppCommit
  #define AppCommit ""
#endif

#define AppName "CLI Avatars"
#define AppExe "cli-avatars.exe"

[Setup]
AppId={{B7E2A1C4-5D38-4F90-8A16-3C9E0D2B7F41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Runar Studio
DefaultDirName={localappdata}\Programs\CLI Avatars
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=CLI-Avatars-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\Caine_Icon.ico
UninstallDisplayIcon={app}\{#AppExe}
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#AppVersion}
VersionInfoProductTextVersion={#AppVersion} {#AppCommit}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\CLI Avatars\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "CLI Avatars"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon; Comment: "CLI Avatars"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start CLI Avatars"; Flags: nowait postinstall skipifsilent

[Code]
var
  DeleteAppData: Boolean;

function InitializeUninstall(): Boolean;
var
  Form: TSetupForm;
  Info: TNewStaticText;
  CheckBox: TNewCheckBox;
  UninstallButton: TNewButton;
  CancelButton: TNewButton;
begin
  DeleteAppData := False;
  Result := True;
  if UninstallSilent then
    Exit;
  Form := CreateCustomForm(ScaleX(440), ScaleY(170), False, False);
  try
    Form.BorderStyle := bsDialog;
    Form.Caption := 'Uninstall CLI Avatars';
    Form.Position := poScreenCenter;

    Info := TNewStaticText.Create(Form);
    Info.Parent := Form;
    Info.Left := ScaleX(16);
    Info.Top := ScaleY(16);
    Info.Width := Form.ClientWidth - ScaleX(32);
    Info.Height := ScaleY(48);
    Info.AutoSize := False;
    Info.WordWrap := True;
    Info.Caption :=
      'The program is removed from your user Programs folder. ' +
      'Chat, settings, and the update clone stay unless you tick the box.';

    CheckBox := TNewCheckBox.Create(Form);
    CheckBox.Parent := Form;
    CheckBox.Left := ScaleX(16);
    CheckBox.Top := ScaleY(72);
    CheckBox.Width := Form.ClientWidth - ScaleX(32);
    CheckBox.Height := ScaleY(24);
    CheckBox.Caption := 'Also delete app data (chat, settings, and the update clone)';
    CheckBox.Checked := False;

    UninstallButton := TNewButton.Create(Form);
    UninstallButton.Parent := Form;
    UninstallButton.Caption := 'Uninstall';
    UninstallButton.ModalResult := mrOk;
    UninstallButton.Default := True;
    UninstallButton.Width := ScaleX(90);
    UninstallButton.Height := ScaleY(24);
    UninstallButton.Left := Form.ClientWidth - ScaleX(196);
    UninstallButton.Top := Form.ClientHeight - ScaleY(40);

    CancelButton := TNewButton.Create(Form);
    CancelButton.Parent := Form;
    CancelButton.Caption := 'Cancel';
    CancelButton.ModalResult := mrCancel;
    CancelButton.Cancel := True;
    CancelButton.Width := ScaleX(90);
    CancelButton.Height := ScaleY(24);
    CancelButton.Left := Form.ClientWidth - ScaleX(100);
    CancelButton.Top := UninstallButton.Top;

    Form.ActiveControl := CancelButton;
    Result := Form.ShowModal() = mrOk;
    if Result then
      DeleteAppData := CheckBox.Checked;
  finally
    Form.Free();
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if (CurUninstallStep <> usPostUninstall) or (not DeleteAppData) then
    Exit;
  DataDir := ExpandConstant('{localappdata}\cli-avatars');
  if DirExists(DataDir) then
    DelTree(DataDir, True, True, True);
end;
