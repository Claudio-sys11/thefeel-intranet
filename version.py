# -*- coding: utf-8 -*-
"""버전 및 배포 정보 (릴리스마다 __version__ 만 올리면 됨)"""
__version__ = "1.3.9"
GITHUB_OWNER = "Claudio-sys11"
GITHUB_REPO = "thefeel-intranet"
# 릴리스 자산(설치파일) 이름 패턴 (실제 파일명에는 버전이 붙음: ...-1.0.2.exe)
ASSET_NAME = "ThefeelIntranet-Setup.exe"
# 기본 서버 PC 주소 — 이 IP의 PC는 '항상 서버', 그 외 PC는 이 주소로 '자동 클라이언트' 접속.
# 서버 PC IP가 바뀌면 이 값만 수정해 재배포하면 됨(서버 PC는 고정 IP 권장).
DEFAULT_SERVER_HOST = "192.168.0.74"
DEFAULT_SERVER_PORT = 5000
DEFAULT_SERVER_URL = f"http://{DEFAULT_SERVER_HOST}:{DEFAULT_SERVER_PORT}"
