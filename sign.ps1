# The Feel Intranet 코드서명 헬퍼
# 사용법: powershell -ExecutionPolicy Bypass -File sign.ps1 "대상파일.exe"
param([Parameter(Mandatory=$true)][string]$File)

$cert = $null
# 1) thumbprint 파일로 저장소에서 조회
$thumbFile = Join-Path $PSScriptRoot ".cert_thumbprint"
if (Test-Path $thumbFile) {
  $tp = (Get-Content $thumbFile -Raw).Trim()
  $cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Thumbprint -eq $tp -and $_.HasPrivateKey } | Select-Object -First 1
}
# 2) 주체명으로 조회
if (-not $cert) {
  $cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -like '*THE FEEL KOREA*' -and $_.HasPrivateKey } | Select-Object -First 1
}
# 3) PFX 백업에서 로드
if (-not $cert) {
  $pfx = Join-Path $PSScriptRoot "thefeel-codesign.pfx"
  if (Test-Path $pfx) {
    $pw = ConvertTo-SecureString "thefeel-sign-2026" -AsPlainText -Force
    $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($pfx, $pw, 'Exportable,PersistKeySet')
  }
}
if (-not $cert) { Write-Error "코드서명 인증서를 찾을 수 없습니다."; exit 1 }

Set-AuthenticodeSignature -FilePath $File -Certificate $cert -HashAlgorithm SHA256 -TimestampServer "http://timestamp.digicert.com" | Out-Null
# 자체서명 인증서는 인증서를 신뢰 등록하지 않은 PC에서 Status=UnknownError(미신뢰 루트)로 나오지만
# 서명 자체는 적용된다. SignerCertificate 존재 여부로 성공 판정.
$sig = Get-AuthenticodeSignature -FilePath $File
if ($sig.SignerCertificate) {
  "Signed OK ($($sig.Status))  $File"
} else {
  Write-Error "서명 실패: $File"; exit 1
}
