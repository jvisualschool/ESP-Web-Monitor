# ESP-Web-Monitor (Retro Terminal & Serial Web Monitor)

이 프로젝트는 ESP32의 시리얼 출력을 캡처하여 웹 브라우저에서 레트로 터미널 스타일로 모니터링하고 제어할 수 있는 개발 환경입니다. ESP-IDF 인프라와 Python Flask 서버를 결합하여 실시간 로그 스트리밍, 원격 리부트, 자동 빌드 파이프라인을 제공합니다.

---

## 📦 Git 저장소 설정 (Setup)

개발 환경을 Git으로 관리하려면 다음 명령어를 터미널에서 실행하세요:

```bash
# Git 초기화
git init

# 원격 저장소 연결 (필요시)
# git remote add origin [YOUR_REPOSITORY_URL]

# 모든 파일 추가 및 첫 커밋
git add .
git commit -m "Initial commit: ESP-Web-Monitor"
```

---

## 🚀 주요 기능

### 1. ESP32 Firmware (ESP-IDF)

- **시스템 정보 출력**: 칩 사양, 코어 수, 메모리(Heap) 상태 실시간 모니터링.
- **애니메이션 ASCII 카운트다운**: 한 줄씩 0.1초 간격으로 출력되어 터미널 촤르륵 효과 구현.
- **포맷팅된 데이터 출력**: 박스 형태의 ASCII 레이아웃을 사용하여 현재 시간(KST) 및 위치 정보 표시.
- **고정 너비 정렬**: `printf` 포맷팅을 통해 시리얼 출력의 가로세로 정렬 유지.

### 2. Web Monitor (Python Flask)

- **레트로 UI/UX**: IBM Plex Mono 및 Fira Code 폰트를 사용한 고전 녹색 터미널 감성.
- **실시간 스트리밍**: 50ms 간격의 폴링을 통해 끊김 없는 로그 업데이트.
- **자동 스크롤 제어**: `PAUSE/RESUME SCROLL` 기능을 통해 특정 로그 분석 시 스크롤 고정 가능.
- **원격 리부트**: `esptool.py` 라이브러리를 통해 브라우저에서 ESP32 하드웨어 리셋 수행.

### 3. Automation Tooling

- **One-Step Pipeline**: `build_and_upload.sh` 스크립트 하나로 [서버 중지 -> 빌드 -> 플래싱 -> 서버 재시작] 전 과정 자동화.

---

## 🛠 기술 스택

- **Firmware**: ESP-IDF v5.5.2 (C Language)
- **Server**: Python 3.13+, Flask
- **Communication**: PySerial (115200 baud)
- **Frontend**: Vanilla JS, CSS3 (Retro Neon Style)
- **Tools**: esptool.py, Ninja Build System

---

## 📂 프로젝트 구조

```text
.
├── README.md               # 프로젝트 설명서
├── build_and_upload.sh     # 빌드/업로드/서버재시작 자동화 스크립트
├── serial_web_server.py    # Flask 기반 시리얼 웹 서버
├── .venv/                  # Python 가상 환경
└── hello_world/            # ESP32 ESP-IDF 프로젝트 폴더
    ├── main/
    │   └── hello_world_main.c # 메인 C 소스 코드
    └── CMakeLists.txt      # ESP-IDF 빌드 설정
```

---

## 🕹 시작하기

### 1. 환경 준비

**ESP-IDF 설정**:

```bash
# ESP-IDF가 설치된 경로에서 환경 변수 로드
source ~/esp/esp-idf/export.sh
```

**Python 의존성 설치**:

```bash
cd /Users/jinhojung/Desktop/ESP-IDF
source .venv/bin/activate
pip install flask pyserial esptool
```

### 2. 빌드 및 업로드 (자동화)

커넥터를 연결한 상태에서 다음 스크립트를 실행합니다. 포트(`/dev/cu.usbmodem1101`)는 사용자 환경에 따라 `build_and_upload.sh`에서 수정 가능합니다.

```bash
chmod +x build_and_upload.sh
./build_and_upload.sh
```

### 3. 웹 모니터링 접속

브라우저를 열고 다음 주소에 접속합니다:

- **URL**: `http://localhost:8080`

---

## 🖥 상세 인터페이스 가이드

### 🟩 콘솔 영역

- **Automatic Scrolling**: 새로운 로그가 들어오면 자동으로 화면 하단으로 이동합니다.
- **Fade-in Animation**: 텍스트가 나타날 때 부드럽게 올라와 실제 터미널 느낌을 줍니다.

### 🔘 상단 버튼

- **PAUSE/RESUME SCROLL**: 로그 흐름을 일시 정지하여 특정 버그나 데이터를 자세히 관찰할 때 사용합니다.
- **REBOOT ESP32**: 시리얼 포트의 DTR/RTS 핀을 제어하여 ESP32를 하드웨어적으로 다시 시작시킵니다.

---

## 📝 개발자 참고 사항

- **시리얼 포트 점유**: `esptool`(업로드)과 `serial_web_server`(모니터링)는 동시에 같은 시리얼 포트를 사용할 수 없습니다. `build_and_upload.sh`는 이 충돌을 방지하기 위해 서버를 먼저 종료한 후 빌드 프로세스를 진행합니다.
- **시간 설정**: 현재 SNTP를 통한 시간 동기화 대신 ESP32 내부 소프트웨어 타이머를 기반으로 동작하며, 출력 형식은 `strftime`을 통해 KST(UTC+9)로 포맷팅됩니다.
- **ASCII 아트 확장**: `hello_world_main.c`의 `print_big_number` 함수에 새로운 숫자를 추가하여 시각적 피드백을 확장할 수 있습니다.

---

## 📡 문제 해결 (Troubleshooting)

1. **Port Permission Error**: `ls -l /dev/cu.*` 명령어로 포트 이름을 확인하고 `serial_web_server.py`와 `build_and_upload.sh` 내의 `SERIAL_PORT` 경로를 일치시키세요.
2. **Python Module Missing**: `esptool`을 찾을 수 없는 경우 가상 환경(`source .venv/bin/activate`)을 로드했는지 확인하세요.
3. **Ghost Process**: 서버 중지 시 `pkill -f python` 명령어로 백그라운드 프로세스를 정리할 수 있습니다.
4. **Git Ignore**: `.venv`나 `build` 폴더가 Git에 올라가지 않도록 제공된 `.gitignore` 파일을 사용하세요.

---

## 📜 소스 코드 관리 가이드

이 프로젝트의 핵심 소스 코드는 다음과 같습니다:

- **실시간 데이터 처리**: `serial_web_server.py`
- **임베디드 로직**: `hello_world/main/hello_world_main.c`
- **워크플로우 자동화**: `build_and_upload.sh`

---

Created by **Antigravity AI Assistant** for **Jinho Jung**
