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
OutputBaseFilename=ThefeelIntranet-Setup-{#MyAppVersion}
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

; 구버전(한글 제품명) 바로가기/그룹 잔재 정리
[InstallDelete]
Type: files;          Name: "{autodesktop}\더필코리아 인트라넷.lnk"
Type: filesandordirs; Name: "{autoprograms}\더필코리아 인트라넷"

[Files]
Source: "dist\{#MyAppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; 바탕화면 바로가기
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
; 시작 메뉴
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\{#MyAppName} 제거"; Filename: "{uninstallexe}"

[Run]
; 설치 완료 후 자동 실행 (사일런트 업데이트 포함)
Filename: "{app}\{#MyAppExe}"; Description: "{#MyAppName} 실행"; Flags: nowait postinstall
