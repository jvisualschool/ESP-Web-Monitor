import threading
import time
import serial
import serial.tools.list_ports
import subprocess
import sys
from flask import Flask, render_template_string, jsonify, request
from collections import deque

# --- 설정 ---
SERIAL_PORT = '/dev/cu.usbmodem101'
BAUD_RATE = 115200
MAX_BUFFER_LINES = 1000  

# --- 글로벌 상태 관리 ---
app = Flask(__name__)
log_queue = deque(maxlen=MAX_BUFFER_LINES)
log_sequence = 0
serial_inst = None
serial_lock = threading.Lock()
is_connected = False

def _find_serial_port():
    """우선 기본 포트 시도, 실패 시 사용 가능한 USB 시리얼 포트 검색 (리셋 후 포트 번호 변경 대응)"""
    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1) as probe:
            pass
        return SERIAL_PORT
    except Exception:
        pass
    for port in serial.tools.list_ports.comports():
        path = port.device
        if 'usbmodem' in path or 'usbserial' in path or (sys.platform == 'win32' and path.startswith('COM')):
            try:
                with serial.Serial(path, BAUD_RATE, timeout=0.1) as probe:
                    pass
                return path
            except Exception:
                continue
    return None

# --- 시리얼 리스너 쓰레드 ---
def serial_listener():
    global serial_inst, log_sequence, is_connected
    buffer = b""
    
    while True:
        # 1. 연결 시도 (기본 포트 → 포트 스캔으로 재연결)
        # 1. 연결 시도 (기본 포트 → 포트 스캔으로 재연결)
        if serial_inst is None:
            port = _find_serial_port()
            if port is None:
                if time.time() % 5 < 0.2:
                    print(f"⌛ No serial port found (trying {SERIAL_PORT} and USB serial)", flush=True)
                time.sleep(1)
                continue
            try:
                new_inst = serial.Serial(port, BAUD_RATE, timeout=0.1)
                new_inst.dtr = False
                new_inst.rts = False
                with serial_lock:
                    serial_inst = new_inst
                    is_connected = True
                print(f"📡 Serial Connected: {port}")
                
                # 연결 직후 ESP32 안정화 대기
                time.sleep(1.0)
                print("📡 [AUTO] Serial connection established")
            except Exception as e:
                if time.time() % 5 < 0.2:
                    print(f"⌛ Serial port {port} error: {e}", flush=True)
                with serial_lock:
                    is_connected = False
                    serial_inst = None
                time.sleep(1)
                continue
        
        # 2. 데이터 읽기 및 명령 전송
        try:
            chunk = None
            with serial_lock:
                if serial_inst and serial_inst.in_waiting:
                    chunk = serial_inst.read(serial_inst.in_waiting)
            
            if chunk:
                buffer += chunk
            
            if b"\n" in buffer:
                lines = buffer.split(b"\n")
                buffer = lines.pop()
                for l in lines:
                    text = l.decode('utf-8', errors='replace').rstrip('\r\n')
                    log_sequence += 1
                    log_queue.append({"id": log_sequence, "text": text, "time": time.strftime("%H:%M:%S")})
                    
                    # 자동 재부팅 감지 비활성화 - HARD RESET 버튼으로만 리셋

        except Exception as e:
            print(f"❌ Serial Error: {e}", flush=True)
            with serial_lock:
                is_connected = False
                if serial_inst:
                    try: serial_inst.close()
                    except: pass
                serial_inst = None
            # 리셋 후 USB 재연결 대기 (포트 번호 바뀜 대응)
            time.sleep(2)
        
        time.sleep(0.01)

# --- 웹 대시보드 템플릿 (Premium UI) ---
INDEX_HTML = '''
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>ESP32 Web Console</title>
    <link rel="icon" type="image/svg+xml" href="/favicon.ico">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {
            /* 기본 다크 테마 */
            --bg-color: #0d1117;
            --card-bg: #161b22;
            --accent-color: #58a6ff;
            --text-color: #c9d1d9;
            --terminal-green: #3fb950;
            --error-red: #f85149;
            --font-family: 'JetBrains Mono', monospace;
            --log-hover: rgba(255,255,255,0.03);
            --crt-scanline: none;
            --text-shadow: none;
        }

        /* 라이트 테마 */
        [data-theme="light"] {
            --bg-color: #ffffff;
            --card-bg: #f6f8fa;
            --accent-color: #0969da;
            --text-color: #24292f;
            --terminal-green: #1a7f37;
            --error-red: #cf222e;
            --log-hover: rgba(0,0,0,0.05);
        }

        /* 레트로 아스키 테마 (CRT 효과) */
        [data-theme="retro"] {
            --bg-color: #000000;
            --card-bg: #111111;
            --accent-color: #00ff00;
            --text-color: #00ff00;
            --terminal-green: #00ff00;
            --error-red: #ff3333;
            --font-family: 'Courier New', Courier, monospace;
            --log-hover: rgba(0, 255, 0, 0.1);
            --text-shadow: 0 0 5px rgba(0, 255, 0, 0.8);
        }

        /* CRT 화면 효과 (레트로 테마 전용) */
        [data-theme="retro"]::after {
            content: " ";
            display: block;
            position: absolute;
            top: 0;
            left: 0;
            bottom: 0;
            right: 0;
            background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.06), rgba(0, 255, 0, 0.02), rgba(0, 0, 255, 0.06));
            z-index: 2;
            background-size: 100% 2px, 3px 100%;
            pointer-events: none;
        }

        body {
            margin: 0;
            padding: 0;
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: var(--font-family);
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
            line-height: 1.1;
            transition: background-color 0.3s, color 0.3s;
            text-shadow: var(--text-shadow);
        }

        #navbar {
            padding: 10px 25px;
            background: var(--card-bg);
            border-bottom: 1px solid #30363d;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
            z-index: 10;
            transition: background 0.3s;
        }
        
        [data-theme="light"] #navbar { border-bottom: 1px solid #d0d7de; }
        [data-theme="retro"] #navbar { border-bottom: 1px solid #00ff00; }

        .status-badge {
            padding: 2px 10px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: bold;
            text-transform: uppercase;
        }
        .online { background: rgba(63, 185, 80, 0.15); color: var(--terminal-green); border: 1px solid var(--terminal-green); }
        .offline { background: rgba(248, 81, 73, 0.15); color: var(--error-red); border: 1px solid var(--error-red); }

        #console {
            flex: 1;
            overflow-y: auto;
            padding: 15px 20px;
            display: flex;
            flex-direction: column;
            gap: 1px;
            scroll-behavior: auto;
            position: relative;
            z-index: 1;
        }

        .log-line {
            display: flex;
            gap: 15px;
            padding: 1px 8px;
            border-radius: 4px;
            transition: background 0.2s;
            animation: fadeIn 0.2s ease-out;
        }
        .log-line:hover { background: var(--log-hover); }
        .log-time { color: var(--text-color); opacity: 0.6; min-width: 80px; font-size: 12px; }
        .log-text { word-break: break-all; white-space: pre-wrap; color: var(--text-color); }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-2px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .controls { display: flex; gap: 10px; }
        .btn {
            background: var(--card-bg);
            border: 1px solid #30363d;
            color: var(--text-color);
            padding: 6px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-family: inherit;
            font-size: 13px;
            transition: all 0.2s;
        }
        [data-theme="light"] .btn { border: 1px solid #d0d7de; }
        [data-theme="retro"] .btn { border: 1px solid #00ff00; background: #000; }
        
        .btn:hover { opacity: 0.8; }
        .btn-primary { background: var(--accent-color); color: white; border: none; }
        [data-theme="retro"] .btn-primary { color: black; background: #00ff00; }
        .btn-primary:hover { opacity: 0.9; }
    </style>
</head>
<body>
    <div id="navbar">
        <div style="display:flex; align-items:center; gap:15px;">
            <h3 style="margin:0; color:var(--accent-color);">ESP32 CONSOLE</h3>
            <div id="status-badge" class="status-badge offline">CONNECTING...</div>
        </div>
        <div class="controls">
            <button class="btn" id="theme-btn" onclick="toggleTheme()">THEME: DARK</button>
            <button class="btn" id="scroll-toggle" onclick="toggleAutoScroll()">AUTO-SCROLL: ON</button>
            <button class="btn" onclick="clearConsole()">CLEAR</button>
            <button class="btn btn-primary" id="reboot-btn" onclick="rebootESP()">HARD RESET</button>
        </div>
    </div>
    <div id="console"></div>

    <script>
        let lastId = 0;
        let autoScroll = true;
        let rebootInProgress = false;
        const consoleEl = document.getElementById('console');
        
        // 테마 설정
        const themes = ['dark', 'retro', 'light'];
        let currentThemeIndex = 0;
        
        function initTheme() {
            const savedTheme = localStorage.getItem('esp_theme') || 'dark';
            currentThemeIndex = themes.indexOf(savedTheme);
            if (currentThemeIndex === -1) currentThemeIndex = 0;
            applyTheme();
        }

        function toggleTheme() {
            currentThemeIndex = (currentThemeIndex + 1) % themes.length;
            applyTheme();
        }

        function applyTheme() {
            const theme = themes[currentThemeIndex];
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('esp_theme', theme);
            
            const btn = document.getElementById('theme-btn');
            if(btn) btn.textContent = `THEME: ${theme.toUpperCase()}`;
        }
        
        // 초기화 시 실행
        initTheme();

        function toggleAutoScroll() {
            autoScroll = !autoScroll;
            document.getElementById('scroll-toggle').textContent = `AUTO-SCROLL: ${autoScroll ? 'ON' : 'OFF'}`;
        }

        function clearConsole() { consoleEl.innerHTML = ''; }

        async function rebootESP() {
            if(rebootInProgress || !confirm('ESP32를 강제 리셋하시겠습니까?')) return;
            rebootInProgress = true;
            const btn = document.getElementById('reboot-btn');
            if(btn) { btn.disabled = true; btn.textContent = 'RESETTING...'; }
            try {
                const ctrl = new AbortController();
                const t = setTimeout(() => ctrl.abort(), 1000);
                const res = await fetch('/reboot', { method: 'POST', signal: ctrl.signal });
                clearTimeout(t);
                const data = await res.json();
                const div = document.createElement('div');
                div.className = 'log-line';
                if(data.success) {
                    div.innerHTML = `<span class="log-time">SYSTEM</span><span class="log-text" style="color:#3fb950;">>>> Reboot command sent. Device restarting...</span>`;
                } else {
                    div.innerHTML = `<span class="log-time">SYSTEM</span><span class="log-text" style="color:#f85149;">>>> Reboot failed: ${escapeHtml(data.error || data.message || '')}</span>`;
                }
                consoleEl.appendChild(div);
            } finally {
                rebootInProgress = false;
                if(btn) { btn.disabled = false; btn.textContent = 'HARD RESET'; }
            }
        }

        async function sync() {
            try {
                const res = await fetch(`/api/sync?last_id=${lastId}`);
                const data = await res.json();
                
                // 상태 업데이트
                const badge = document.getElementById('status-badge');
                if (badge) {
                    badge.textContent = data.connected ? 'ONLINE' : 'OFFLINE';
                    badge.className = `status-badge ${data.connected ? 'online' : 'offline'}`;
                }

                // 서버가 재시작되어 sequence가 초기화된 경우 처리
                if (data.last_id < lastId) {
                    console.log("Server restarted, resetting lastId");
                    lastId = 0;
                    return; // 다음 주기부터 다시 가져옴
                }

                if (data.logs && data.logs.length > 0) {
                    // 로그를 순차적으로 추가하여 부드러운 애니메이션 효과 연출
                    data.logs.forEach((msg, index) => {
                        setTimeout(() => {
                            const div = document.createElement('div');
                            div.className = 'log-line';
                            div.innerHTML = `<span class="log-time">${msg.time}</span><span class="log-text">${escapeHtml(msg.text)}</span>`;

                            // 초기 상태: 투명하고 아래에서 오는 효과
                            div.style.opacity = '0';
                            div.style.transform = 'translateY(8px)';
                            div.style.transition = 'opacity 0.35s ease-out, transform 0.35s ease-out';

                            consoleEl.appendChild(div);

                            // 애니메이션 트리거 (다음 프레임에)
                            requestAnimationFrame(() => {
                                div.style.opacity = '1';
                                div.style.transform = 'translateY(0)';
                            });

                            // 줄 수 관리 (메모리 최적화)
                            while(consoleEl.children.length > 1000) {
                                const firstChild = consoleEl.firstChild;
                                if(firstChild) consoleEl.removeChild(firstChild);
                            }

                            // 부드러운 스크롤 (마지막 로그에만 적용)
                            if(autoScroll && index === data.logs.length - 1) {
                                setTimeout(() => {
                                    consoleEl.scrollTo({
                                        top: consoleEl.scrollHeight,
                                        behavior: 'smooth'
                                    });
                                }, 50);
                            }
                        }, index * 20); // 20ms 간격으로 빠르게 순차 출력 (섞임 방지 최적화)
                    });
                }
                
                // 로그 유무와 상관없이 항상 최신 ID로 갱신
                lastId = data.last_id;

            } catch (e) {
                console.error("Sync error", e);
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        setInterval(sync, 120);
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

@app.route('/api/sync')
@app.route('/sync') # 하위 호환성 유지
def api_sync():
    try:
        current_last_id = int(request.args.get('last_id', 0))
        # 새 로그만 필터링
        new_logs = [log for log in log_queue if log['id'] > current_last_id]
        return jsonify({
            "connected": is_connected,
            "last_id": log_sequence,
            "logs": new_logs,
            "status": "Connected" if is_connected else "Disconnected",
            "count": len(log_queue)
        })
    except Exception as e:
        return jsonify({"connected": False, "last_id": 0, "logs": [], "error": str(e)})

@app.route('/status') # 하위 호환성 유지
def api_status():
    return jsonify({
        "status": "Connected" if is_connected else "Disconnected",
        "count": len(log_queue),
        "last_id": log_sequence,
        "connected": is_connected
    })

def _do_reboot_sequence():
    """백그라운드에서 REBOOT 1회 전송 (확실히 flush)"""
    global serial_inst, log_queue
    print("🔄 _do_reboot_sequence() called")
    with serial_lock:
        if not serial_inst:
            print("❌ No serial connection for reboot")
            return
        try:
            serial_inst.write(b"REBOOT\n")
            serial_inst.flush()
            log_queue.clear()
            print("✅ REBOOT sent (once).")
        except Exception as e:
            print(f"❌ Reboot send failed: {e}")
            return

        # DTR/RTS 핀 제어로 ESP32 하드웨어 리셋
        try:
            print("🔌 Performing hardware reset via DTR/RTS")
            # ESP32 리셋 시퀀스: DTR=Low, RTS=High -> DTR=High, RTS=Low
            serial_inst.setDTR(False)
            serial_inst.setRTS(True)
            time.sleep(0.1)
            serial_inst.setDTR(True)
            serial_inst.setRTS(False)
            time.sleep(0.1)
            serial_inst.setDTR(False)
            serial_inst.setRTS(False)
            print("✅ Hardware reset sequence completed")
        except Exception as e:
            print(f"❌ Hardware reset failed: {e}")

@app.route('/reboot', methods=['POST'])
def reboot():
    global serial_inst
    if not serial_inst:
        return jsonify({"success": False, "message": "No serial connection"}), 400
    # 즉시 200 반환 후, 실제 전송은 백그라운드에서 수행 (버튼이 RESETTING...에서 멈추지 않음)
    threading.Thread(target=_do_reboot_sequence, daemon=True).start()
    return jsonify({"success": True})

@app.route('/favicon.ico')
def favicon():
    return open('terminal-icon.svg', 'rb').read(), 200, {'Content-Type': 'image/svg+xml'}

if __name__ == '__main__':
    threading.Thread(target=serial_listener, daemon=True).start()
    app.run(host='0.0.0.0', port=8080, debug=False)
