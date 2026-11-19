# TOS_RigTools 1.0 (3ds Max 2016, 2026-11-18)

TOS 프로젝트용 리깅 툴. MTOS_RigTools 1.0 을 바탕으로 기준을 각 PC 의 `ani\Character\PC` 직업별 레퍼런스(Ver5_<직업>_<성별>, 자동으로 찾음)로 바꿨습니다.
MTOS_RigTools·GE 리그 툴과 한 Max 에 같이 켤 수 있습니다 (함수 이름·메뉴·데이터 폴더가 따로).
변경 내용: `docs\TOS_1.0_변경사항.md`. 작업자 설치 안내: `README_KO.txt`.

## 설치
1. 3ds Max 와 블렌더를 모두 끕니다.
2. `INSTALL_ALL.bat` → 묶음 검사(manifest) → 설치 → 점검.
3. Max 상단 메뉴 **TOS > TOS_RigTools**.
4. 되돌리기: `3_RESTORE.bat`

## 관리
- Biped 레퍼런스 데이터 다시 만들기: TOS_RigTools 창 아래 [레퍼런스 다시 읽기] (직업·성별 8개)
- payload 를 고친 뒤: `powershell -File _setup\make_manifest.ps1`
- 다른 PC 용 zip: `MAKE_ZIP.bat`
