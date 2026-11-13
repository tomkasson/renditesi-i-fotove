"""Renditësi i Fotove si program: serveri në sfond + dritare më vete (Edge/Chrome në modalitetin aplikacion).

Hapet me pythonw (pa dritaren e zezë): ikona në Desktop e thërret këtë skedar.
Kur mbyllet dritarja, ndalet edhe serveri. Nëse Renditësi është tashmë i hapur, hapet vetëm një dritare e re.
Ditari i serverit: %LOCALAPPDATA%\\RenditesiFotove\\ditari.txt
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
APP_HOME = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "RenditesiFotove")
STATE = os.path.join(APP_HOME, "serveri.json")
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


def python_exe():
    """python.exe pranë pythonw.exe (serveri nuk ka nevojë për dritare)."""
    d = os.path.dirname(sys.executable)
    p = os.path.join(d, "python.exe")
    return p if os.path.exists(p) else sys.executable


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def alive(url):
    try:
        with urllib.request.urlopen(url + "/_stcore/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def find_browser():
    pf = [os.environ.get(k, "") for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    cands = [os.path.join(b, "Microsoft", "Edge", "Application", "msedge.exe") for b in pf if b]
    cands += [os.path.join(b, "Google", "Chrome", "Application", "chrome.exe") for b in pf if b]
    return next((c for c in cands if os.path.exists(c)), None)


def open_window(url):
    """Dritare më vete pa shiritin e adresës. Kthen procesin (që të dimë kur mbyllet) ose None."""
    b = find_browser()
    if not b:
        webbrowser.open(url)
        return None
    prof = os.path.join(APP_HOME, "dritarja")  # profil i veçantë: dritarja jeton sa jeton procesi
    return subprocess.Popen([b, f"--app={url}", f"--user-data-dir={prof}", "--window-size=1440,920",
                             "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"])


def splash(stop_event):
    """Dritare e vogël 'Po hapet...' derisa serveri të jetë gati."""
    try:
        import tkinter as tk
    except Exception:
        stop_event.wait()
        return
    root = tk.Tk()
    root.overrideredirect(True)
    root.configure(bg="#0F172A")
    w, h = 380, 130
    root.geometry(f"{w}x{h}+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 2}")
    tk.Label(root, text="Renditësi i Fotove", fg="#E2E8F0", bg="#0F172A", font=("Segoe UI", 15, "bold")).pack(pady=(26, 4))
    msg = tk.Label(root, text="Po hapet...", fg="#A5B4FC", bg="#0F172A", font=("Segoe UI", 10))
    msg.pack()
    dots = [0]

    def tick():
        if stop_event.is_set():
            root.destroy()
            return
        dots[0] = (dots[0] + 1) % 4
        msg.config(text="Po hapet" + "." * dots[0] + " " * (3 - dots[0]))
        root.after(350, tick)

    root.after(350, tick)
    root.mainloop()


def main():
    os.makedirs(APP_HOME, exist_ok=True)
    # tashmë i hapur? vetëm një dritare e re
    try:
        with open(STATE, encoding="utf-8") as f:
            url = json.load(f)["url"]
        if alive(url):
            p = open_window(url)
            if p:
                p.wait()
            return
    except Exception:
        pass

    port = free_port()
    url = f"http://localhost:{port}"
    log = open(os.path.join(APP_HOME, "ditari.txt"), "a", encoding="utf-8", errors="replace")
    log.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} nisja në portin {port}\n")
    log.flush()
    srv = subprocess.Popen(
        [python_exe(), "-m", "streamlit", "run", os.path.join(HERE, "app.py"), "--server.headless", "true",
         "--server.port", str(port), "--server.address", "localhost", "--browser.gatherUsageStats", "false"],
        cwd=HERE, stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
    stop = threading.Event()
    th = threading.Thread(target=splash, args=(stop,), daemon=True)
    th.start()
    t0 = time.time()
    while not alive(url):
        if srv.poll() is not None or time.time() - t0 > 180:  # serveri ra ose s'u hap
            stop.set()
            th.join(timeout=2)
            os.startfile(os.path.join(APP_HOME, "ditari.txt"))
            return
        time.sleep(0.4)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({"url": url, "pid": srv.pid}, f)
    stop.set()
    th.join(timeout=2)
    try:
        p = open_window(url)
        if p:
            p.wait()  # mbyllet dritarja → mbyllet programi
        else:  # pa Edge/Chrome: serveri rri derisa të mbyllet kjo dritare e vogël
            import tkinter as tk
            r = tk.Tk()
            r.title("Renditësi i Fotove")
            tk.Label(r, text="Renditësi është hapur në shfletues.\nMbyll këtë dritare për ta ndalur.",
                     font=("Segoe UI", 10), padx=20, pady=16).pack()
            r.mainloop()
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except Exception:
            srv.kill()
        try:
            os.remove(STATE)
        except OSError:
            pass


if __name__ == "__main__":
    main()
