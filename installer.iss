; 더필코리아 인트라넷 설치 스크립트 (Inno Setup 6)
; 버전은 build 단계에서 생성되는 version.iss(#define MyAppVersion) 에서 가져온다.
#include "version.iss"

#define MyAppName "The Feel Intranet"
#define MyAppExe "ThefeelIntranet.exe"
#define MyAppPublisher "THE FEEL KOREA"

[Setup]
; 동일 AppId → 새 버전 설치 시 이전 버전을 자동 제거하고 같은 위치에 업그레이드
AppId={{B4E7B6A2-1F2C-4D9A-9C3E-2A0A5E000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\ThefeelIntranet
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=installer_out
OutputBaseFilename=The Feel Intranet-Setup-v{#MyAppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName} v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 실행 중인 이전 버전을 닫고 진행 (자동 업데이트 시)
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

; 구버전(한글 제품명) 바로가기/그룹 잔재 정리 + 이전 onedir 자원 정리
[InstallDelete]
Type: files;          Name: "{autodesktop}\더필코리아 인트라넷.lnk"
Type: filesandordirs; Name: "{autoprograms}\더필코리아 인트라넷"
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; onedir 빌드: 실행파일 + _internal(템플릿/정적/런타임)을 통째로 설치 → 자원이 항상 폴더에 존재
Source: "dist\ThefeelIntranet\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 바탕화면 바로가기
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
; 시작 메뉴
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\{#MyAppName} 제거"; Filename: "{uninstallexe}"

[Run]
; 아이콘 캐시 새로고침 (바탕화면 바로가기 아이콘 즉시 반영)
Filename: "{sys}\ie4uinit.exe"; Parameters: "-ClearIconCache"; Flags: runhidden skipifdoesntexist
Filename: "{sys}\ie4uinit.exe"; Parameters: "-show"; Flags: runhidden skipifdoesntexist
; 설치 완료 후 자동 실행 (사일런트 업데이트 포함)
Filename: "{app}\{#MyAppExe}"; Description: "{#MyAppName} 실행"; Flags: nowait postinstall

[Code]
procedure SHChangeNotify(EventId: Integer; Flags: Cardinal; Item1, Item2: Cardinal);
  external 'SHChangeNotify@shell32.dll stdcall';

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SHChangeNotify($08000000, $0000, 0, 0);  // SHCNE_ASSOCCHANGED → 쉘 아이콘 갱신
end;
