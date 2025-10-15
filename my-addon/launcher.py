# launcher.py
import subprocess, signal, sys, os, time

PROCS = []

def start(cmd):
    print(f"[launcher] starting: {cmd}", flush=True)
    p = subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)
    PROCS.append(p)
    return p

def stop_all():
    for p in PROCS:
        if p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
    # 給一點時間讓它們優雅關閉
    t0 = time.time()
    while any(p.poll() is None for p in PROCS) and time.time() - t0 < 8:
        time.sleep(0.2)
    # 還有沒關掉的就殺掉
    for p in PROCS:
        if p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass

def handler(sig, frame):
    print(f"[launcher] got signal {sig}, terminating children...", flush=True)
    stop_all()
    sys.exit(0)

if __name__ == "__main__":
    # 訊號處理（HA/Supervisor 會送 SIGTERM）
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)

    # 同時啟動兩支
    p1 = start(["python3", "/run.py"])          # MQTT 發佈/Discovery
    p2 = start(["python3", "/3drp_show.py"])    # Flask HTTP API/Status

    # 任何一支先退出，就把另一支也關掉並跟著退出
    exit_code = 0
    try:
        while True:
            if p1.poll() is not None:
                exit_code = p1.returncode
                print(f"[launcher] /run.py exited with {exit_code}", flush=True)
                break
            if p2.poll() is not None:
                exit_code = p2.returncode
                print(f"[launcher] /3drp_show.py exited with {exit_code}", flush=True)
                break
            time.sleep(0.5)
    finally:
        stop_all()
    sys.exit(exit_code)
