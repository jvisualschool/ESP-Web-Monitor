#!/bin/bash

# ESP32 빌드 및 업로드 자동화 스크립트
# Flask 서버 중지 -> 빌드 -> 업로드 -> Flask 서버 재시작

set -e  # 에러 발생 시 스크립트 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 설정
PROJECT_DIR="/Users/jinhojung/Desktop/ESP-IDF/hello_world"
SERIAL_PORT="/dev/cu.usbmodem1101"
FLASK_SERVER_SCRIPT="/Users/jinhojung/Desktop/ESP-IDF/serial_web_server.py"
VENV_PATH="/Users/jinhojung/Desktop/ESP-IDF/.venv"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  ESP-Web-Monitor 빌드 및 업로드${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 1. Flask 서버 중지
echo -e "${YELLOW}[1/4] Flask 서버 중지 중...${NC}"
FLASK_PID=$(ps aux | grep "python.*serial_web_server.py" | grep -v grep | awk '{print $2}')
if [ -n "$FLASK_PID" ]; then
    kill $FLASK_PID
    echo -e "${GREEN}✓ Flask 서버 중지됨 (PID: $FLASK_PID)${NC}"
    sleep 1
else
    echo -e "${YELLOW}⚠ Flask 서버가 실행 중이 아닙니다${NC}"
fi

# 2. ESP-IDF 환경 설정
echo -e "${YELLOW}[2/4] ESP-IDF 환경 설정 중...${NC}"
export PATH="/Users/jinhojung/.espressif/python_env/idf5.5_py3.14_env/bin:$PATH"
export IDF_PATH="$HOME/esp/esp-idf"
source "$IDF_PATH/export.sh" > /dev/null 2>&1
echo -e "${GREEN}✓ ESP-IDF 환경 설정 완료${NC}"

# 3. 빌드 및 업로드
echo -e "${YELLOW}[3/4] ESP32 빌드 및 업로드 중...${NC}"
cd "$PROJECT_DIR"

# 빌드
echo -e "${BLUE}  → 빌드 중...${NC}"
idf.py build

# 업로드
echo -e "${BLUE}  → 업로드 중...${NC}"
idf.py -p "$SERIAL_PORT" flash

echo -e "${GREEN}✓ 빌드 및 업로드 완료${NC}"

# 잠시 대기 (ESP32 재시작 시간)
sleep 2

# 4. Flask 서버 재시작
echo -e "${YELLOW}[4/4] Flask 서버 재시작 중...${NC}"
cd /Users/jinhojung/Desktop/ESP-IDF
source "$VENV_PATH/bin/activate"
nohup python "$FLASK_SERVER_SCRIPT" > /tmp/flask_server.log 2>&1 &
FLASK_NEW_PID=$!
echo -e "${GREEN}✓ Flask 서버 재시작됨 (PID: $FLASK_NEW_PID)${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  모든 작업이 완료되었습니다!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "${BLUE}웹 대시보드: http://localhost:8080${NC}"
echo -e "${BLUE}Flask 로그: tail -f /tmp/flask_server.log${NC}"
echo ""
