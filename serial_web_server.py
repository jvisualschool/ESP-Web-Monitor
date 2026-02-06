import threading
import time
import serial
import subprocess
import sys
from flask import Flask, render_template_string, jsonify, request
from collections import deque

# --- 설정 ---
SERIAL_PORT = '/dev/cu.usbmodem2101'
BAUD_RATE = 115200
MAX_BUFFER_LINES = 1000  

# --- 글로벌 상태 관리 ---
app = Flask(__name__)
log_queue = deque(maxlen=MAX_BUFFER_LINES)
log_sequence = 0
serial_inst = None
serial_lock = threading.Lock()
is_connected = False

# --- 시리얼 리스너 쓰레드 ---
def serial_listener():
    global serial_inst, log_sequence, is_connected
    buffer = b""
    
    while True:
        with serial_lock:
            if serial_inst is None:
                try:
                    serial_inst = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
                    serial_inst.dtr = False
                    serial_inst.rts = False
                    is_connected = True
                    print(f"📡 Serial Connected: {SERIAL_PORT}")
                except Exception as e:
                    if time.time() % 5 < 0.1: # 5초마다 한 번만 출력
                        print(f"⌛ Serial port {SERIAL_PORT} busy or not found: {e}")
                    is_connected = False
                    serial_inst = None
                    time.sleep(1)
                    continue
            
            try:
                if serial_inst.in_waiting:
                    # 바이너리로 읽어서 줄바꿈 단위로 정확히 파싱
                    chunk = serial_inst.read(serial_inst.in_waiting)
                    buffer += chunk
                    if b"\n" in buffer:
                        lines = buffer.split(b"\n")
                        # 마지막 미완성 줄은 다시 버퍼에 저장
                        buffer = lines.pop()
                        for l in lines:
                            text = l.decode('utf-8', errors='replace').rstrip()
                            if text:
                                log_sequence += 1
                                log_queue.append({"id": log_sequence, "text": text, "time": time.strftime("%H:%M:%S")})
            except Exception as e:
                print(f"❌ Serial Error: {e}")
                is_connected = False
                if serial_inst:
                    try: serial_inst.close()
                    except: pass
                serial_inst = None
        
        time.sleep(0.01)

# --- 웹 대시보드 템플릿 (Premium UI) ---
INDEX_HTML = '''
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>ESP32 Web Console</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0d1117;
            --card-bg: #161b22;
            --accent-color: #58a6ff;
            --text-color: #c9d1d9;
            --terminal-green: #3fb950;
            --error-red: #f85149;
        }
        
        body {
            margin: 0;
            padding: 0;
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: 'JetBrains Mono', monospace;
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
            line-height: 1.1; /* 행간 축소 */
        }

        #navbar {
            padding: 10px 25px; /* 헤더 높이도 살짝 축소 */
            background: var(--card-bg);
            border-bottom: 1px solid #30363d;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
            z-index: 10;
        }

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
            gap: 1px; /* 로그 간 간격 축소 */
            scroll-behavior: auto;
        }

        .log-line {
            display: flex;
            gap: 15px;
            padding: 1px 8px; /* 위아래 패딩 50% 이상 축소 */
            border-radius: 4px;
            transition: background 0.2s;
            animation: fadeIn 0.2s ease-out;
        }
        .log-line:hover { background: rgba(255,255,255,0.03); }
        .log-time { color: #8b949e; min-width: 80px; font-size: 12px; }
        .log-text { word-break: break-all; white-space: pre-wrap; color: #d1d5da; }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateX(-5px); }
            to { opacity: 1; transform: translateX(0); }
        }

        .controls { display: flex; gap: 10px; }
        .btn {
            background: #21262d;
            border: 1px solid #30363d;
            color: #c9d1d9;
            padding: 6px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-family: inherit;
            font-size: 13px;
            transition: all 0.2s;
        }
        .btn:hover { background: #30363d; border-color: #8b949e; }
        .btn-primary { background: var(--accent-color); color: white; border: none; }
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
            <button class="btn" id="scroll-toggle" onclick="toggleAutoScroll()">AUTO-SCROLL: ON</button>
            <button class="btn" onclick="clearConsole()">CLEAR</button>
            <button class="btn btn-primary" onclick="rebootESP()">HARD RESET</button>
        </div>
    </div>
    <div id="console"></div>

    <script>
        let lastId = 0;
        let autoScroll = true;
        const consoleEl = document.getElementById('console');

        function toggleAutoScroll() {
            autoScroll = !autoScroll;
            document.getElementById('scroll-toggle').textContent = `AUTO-SCROLL: ${autoScroll ? 'ON' : 'OFF'}`;
        }

        function clearConsole() { consoleEl.innerHTML = ''; }

        async function rebootESP() {
            if(!confirm('ESP32를 강제 리셋하시겠습니까?')) return;
            const res = await fetch('/reboot', { method: 'POST' });
            if(res.ok) {
                 const div = document.createElement('div');
                 div.className = 'log-line';
                 div.innerHTML = `<span class="log-time">SYSTEM</span><span class="log-text" style="color:orange;">>>> Reboot command sent</span>`;
                 consoleEl.appendChild(div);
            }
        }

        async function sync() {
            try {
                const res = await fetch(`/api/sync?last_id=${lastId}`);
                const data = await res.json();
                
                // 상태 업데이트
                const badge = document.getElementById('status-badge');
                badge.textContent = data.connected ? 'ONLINE' : 'OFFLINE';
                badge.className = `status-badge ${data.connected ? 'online' : 'offline'}`;

                if (data.logs.length > 0) {
                    const fragment = document.createDocumentFragment();
                    data.logs.forEach(msg => {
                        const div = document.createElement('div');
                        div.className = 'log-line';
                        div.innerHTML = `<span class="log-time">${msg.time}</span><span class="log-text">${escapeHtml(msg.text)}</span>`;
                        fragment.appendChild(div);
                    });
                    consoleEl.appendChild(fragment);
                    lastId = data.last_id;

                    // 줄 수 관리 (메모리 최적화)
                    while(consoleEl.children.length > 1000) consoleEl.removeChild(consoleEl.firstChild);
                    
                    if(autoScroll) consoleEl.scrollTop = consoleEl.scrollHeight;
                }
            } catch (e) {
                console.error("Sync error", e);
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        setInterval(sync, 100);
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

@app.route('/reboot', methods=['POST'])
def reboot():
    global serial_inst
    with serial_lock:
        if serial_inst:
            serial_inst.dtr = False
            serial_inst.rts = True
            time.sleep(0.1)
            serial_inst.rts = False
            time.sleep(0.1)
            log_queue.clear() # 리부팅 시 버퍼 초기화
            return jsonify({"success": True})
    return jsonify({"success": False}), 400

if __name__ == '__main__':
    threading.Thread(target=serial_listener, daemon=True).start()
    app.run(host='0.0.0.0', port=8080, debug=False)
