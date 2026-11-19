TOS_RigTools 설치 안내 (작업자 PC용, 2026-11-18, TOS_RigTools 1.0 = MTOS_RigTools 1.0 을 TOS 용으로. docs\TOS_1.0_변경사항.md)
==================================================

[부품]  설치할 때 고를 수 있어요 (MTOS_RigTools 설치기와 같음)
  A. Max Bridge + VirusGuard  (항상 설치, MTOS 와 같은 파일)
  B. TOS_RigTools (Max + 블렌더)
     - Max: TOS_RigTools, TOS_RigToolsStd  +  scripts\TOS_RigTools\ (데이터·보조 스크립트)
            BipFit, BipConvert, WeightToolPos 는 MTOS 와 같은 파일 (같이 씀)
     - 블렌더: MTOS 와 같은 애드온
  C. Claude Max 환경 (MTOS 와 같음)

[필요한 것]
  - 3ds Max 2016 을 한 번 켰다 끈 상태
  - TOS 레퍼런스 폴더: <루트>\ani\Character\PC (예: E:\TOS\ani\Character\PC), 그 아래 직업별 폴더 Ver5_Archer_f · Ver5_Archer_m ...
    PC 마다 자동으로 찾아요. 못 찾으면 창 아래 [경로 변경] 으로 골라요 (이 PC 의 plugcfg\TOS_RigTools.ini 에 저장)

[가장 쉬운 방법]
  3ds Max·블렌더를 끄고 INSTALL_ALL.bat 더블클릭. 끝에 점검까지 해요.
  다른 PC: MAKE_ZIP.bat -> 바탕화면에 TOS_RigTools_v1.0.zip -> 그 PC 에서 풀고 INSTALL_ALL.bat

[나눠서 할 때]
  1_INSTALL.bat (설치) -> Max 켜고 2_CHECK.bat (점검, 마지막 줄 "결과: OK") / 되돌리기 3_RESTORE.bat
  바꾸는 파일은 모두 먼저 백업: C:\Users\<내 이름>\tos_rig_backup\<날짜_시각>\

[MTOS_RigTools·GE 리그 툴과 같이 쓰기]
  TOS_RigTools 는 함수 이름이 따로라 MTOS_RigTools·GE 리그 툴과 한 Max 에 같이 켜도 돼요. (메뉴도 TOS / MTOS 따로)
  TOS 설치기는 MTOS·GE 파일을 건드리지 않아요.
  주의: MTOS 설치기(MTOS 의 1_INSTALL·INSTALL_ALL)를 다시 돌리면 TOS_RigTools.ms·TOS_RigToolsStd.ms 를 "이름이 비슷함" 으로 보고
        치울지 물어요 -> N (그대로 둠). Y 를 누르면 TOS 메뉴가 사라져요 (TOS 의 INSTALL_ALL.bat 을 다시 돌리면 돌아옴).

[실행]
  Max 상단 메뉴 TOS > TOS_RigTools
  0 작업 시간 · 1 모델링 체크 · 2 Biped 자동 생성 · 3 헬퍼·보조 본(Twist) · 4 세컨더리 본(Cloak·Skirt·Clavicle)
  5 스킨 · 6 리그 체크 · 7 리깅 완료
  2. Biped = 직업_성별 레퍼런스 Biped 그대로 (archer·cleric·mage·warrior × 남·여)
     직업·성별은 캐릭터 이름(파일 이름) 앞부분(archer_f_..., mage_m_...)이나 파일 위치(Ver5_Archer_f)로 자동으로 정해요.
     못 정하면 창의 [직업]·[성별] 칸에서 골라요 (고른 값은 그 Max 파일에 저장).
  3. 헬퍼·보조 본 = MTOS 와 같음. 여자는 가슴 더미 Dummy_Chast 도 만들어요.
