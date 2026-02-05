import threading
import time
import serial
import subprocess
from flask import Flask, render_template_string, jsonify
from collections import deque

# --- 설정 ---
SERIAL_PORT = '/dev/cu.usbmodem1101'
BAUD_RATE = 115200
MAX_LINES = 500  

# --- 데이터 저장소 ---
log_buffer = deque(maxlen=MAX_LINES)
app = Flask(__name__)

# --- 시리얼 읽기 쓰레드 ---
def read_serial():
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        # 중요: 연결 시 DTR/RTS를 꺼서 ESP32가 리셋되거나 부트로더 모드로 빠지는 것을 방지
        ser.dtr = False
        ser.rts = False
        
        print(f"✅ Connected to {SERIAL_PORT}")
        while True:
            if ser.in_waiting:
                try:
                    line = ser.readline().decode('utf-8', errors='replace').rstrip()
                    if line:
                        print(f"[Serial] {line}")
                        log_buffer.append(line)
                except Exception:
                    pass
            time.sleep(0.005) 
    except Exception as e:
        print(f"❌ Serial Error: {e}")

# --- 웹 서버 라우트 ---
@app.route('/')
def index():
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ESP-Web-Monitor</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Source+Code+Pro:wght@400;500;600&family=Roboto+Mono:wght@400;500;600&display=swap" rel="stylesheet">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                background-color: #0a0e14;
                color: #00ff41;
                font-family: 'Fira Code', 'Source Code Pro', 'Roboto Mono', 'Courier New', monospace;
                margin: 0;
                padding: 20px;
                font-size: 15px;
                line-height: 1.5;
                font-variant-ligatures: none;
                font-feature-settings: normal;
                letter-spacing: 0;
            }
            
            #log-container {
                display: flex;
                flex-direction: column;
                background-color: #0d1117;
                border: 2px solid #1f6feb;
                border-radius: 8px;
                padding: 15px;
                box-shadow: 0 0 20px rgba(31, 111, 235, 0.3);
            }
            
            .log-entry {
                white-space: pre-wrap;
                word-wrap: break-word;
                overflow-wrap: break-word;
                word-break: break-all;
                padding: 3px 8px;
                border-left: 3px solid transparent;
                transition: all 0.2s ease;
                font-weight: 400;
                font-variant-ligatures: none;
                font-feature-settings: normal;
                letter-spacing: 0;
                max-width: 100%;
                overflow-x: auto;
                animation: fadeIn 0.3s ease-in;
            }
            
            @keyframes fadeIn {
                from {
                    opacity: 0;
                    transform: translateY(-5px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            .log-entry:hover {
                background-color: #161b22;
                border-left-color: #00ff41;
                box-shadow: 0 0 10px rgba(0, 255, 65, 0.2);
            }
            
            .top-buttons {
                position: fixed;
                top: 20px;
                right: 20px;
                display: flex;
                gap: 10px;
                z-index: 1000;
            }

            .retro-btn {
                padding: 10px 20px;
                background: transparent;
                color: #00ff41;
                border: 2px solid #00ff41;
                border-radius: 2px;
                cursor: pointer;
                font-family: 'Fira Code', monospace;
                font-size: 14px;
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 1px;
                box-shadow: 0 0 10px rgba(0, 255, 65, 0.4);
                transition: all 0.2s ease;
            }
            
            .retro-btn:hover {
                background: #00ff41;
                color: #0a0e14;
                box-shadow: 0 0 20px rgba(0, 255, 65, 0.8);
            }
            
            .retro-btn:active {
                transform: scale(0.98);
            }
            
            .retro-btn:disabled {
                border-color: #333;
                color: #333;
                box-shadow: none;
                cursor: not-allowed;
            }
        </style>
    </head>
    <body>
        <div class="top-buttons">
            <button id="scroll-btn" class="retro-btn" onclick="toggleScroll()">PAUSE SCROLL</button>
            <button id="reboot-btn" class="retro-btn" onclick="rebootESP32()">REBOOT ESP32</button>
        </div>
        <div id="log-container"></div>
        <script>
            let lastLogLength = 0;
            let isAutoScrollEnabled = true;
            const container = document.getElementById('log-container');
            
            function toggleScroll() {
                isAutoScrollEnabled = !isAutoScrollEnabled;
                const btn = document.getElementById('scroll-btn');
                btn.textContent = isAutoScrollEnabled ? 'PAUSE SCROLL' : 'RESUME SCROLL';
                if (isAutoScrollEnabled) {
                    container.scrollIntoView({ behavior: 'smooth', block: 'end' });
                }
            }
            
            async function rebootESP32() {
                const btn = document.getElementById('reboot-btn');
                if (confirm('ESP32를 리부팅하시겠습니까?')) {
                    btn.disabled = true;
                    btn.textContent = 'REBOOTING...';
                    
                    try {
                        const response = await fetch('/reboot', { method: 'POST' });
                        const result = await response.json();
                        
                        if (result.success) {
                            alert('ESP32가 리부팅되었습니다!');
                            // 로그 초기화
                            container.innerHTML = '';
                            lastLogLength = 0;
                        } else {
                            alert('리부팅 실패: ' + result.error);
                        }
                    } catch (error) {
                        alert('리부팅 요청 실패: ' + error);
                    } finally {
                        btn.disabled = false;
                        btn.textContent = 'REBOOT ESP32';
                    }
                }
            }

            function fetchLogs() {
                fetch('/logs')
                    .then(r => r.json())
                    .then(logs => {
                        if (logs.length === 0 && lastLogLength === 0) return; // 데이터 없음
                        
                        if (logs.length < lastLogLength) {
                             container.innerHTML = ''; 
                             lastLogLength = 0;
                        }

                        if (logs.length > lastLogLength) {
                            const newLogs = logs.slice(lastLogLength);
                            lastLogLength = logs.length;

                            const fragment = document.createDocumentFragment();
                            newLogs.forEach(text => {
                                const div = document.createElement('div');
                                div.className = 'log-entry';
                                div.textContent = text;
                                fragment.appendChild(div);
                            });
                             container.appendChild(fragment);
                             
                             // 부드러운 스크롤 (활성화된 경우에만)
                             if (isAutoScrollEnabled) {
                                 container.scrollIntoView({ behavior: 'smooth', block: 'end' });
                             }
                         }
                     })
                     .catch(e => console.error("Fetch error:", e));
             }
            setInterval(fetchLogs, 50);  // 50ms마다 업데이트 (더 부드러운 스트리밍) 
        </script>
    </body>
    </html>
    ''')

@app.route('/logs')
def get_logs():
    return jsonify(list(log_buffer))

@app.route('/reboot', methods=['POST'])
def reboot_esp32():
    try:
        # esptool을 사용하여 ESP32 리셋
        result = subprocess.run(
            ['python', '-m', 'esptool', '--port', SERIAL_PORT, 'run'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            # 로그 버퍼 초기화
            log_buffer.clear()
            return jsonify({'success': True, 'message': 'ESP32 rebooted successfully'})
        else:
            return jsonify({'success': False, 'error': result.stderr})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Reboot timeout'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    t = threading.Thread(target=read_serial)
    t.daemon = True
    t.start()
    app.run(host='0.0.0.0', port=8080, debug=False)
