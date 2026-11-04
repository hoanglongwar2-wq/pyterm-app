import ctypes
import builtins
import os
import socket
import sys
import threading
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.textinput import TextInput

import pylibs

Window.softinput_mode = "below_target"

MONO = "RobotoMono-Regular"
MAX_OUT = 30000
NEW_LABEL = "[ Script moi ]"
WWW_LABEL = "[ Web tinh: thu muc www ]"
SAMPLES_MARK = ".samples_v3"

SAMPLES = {
    "hello.py": 'print("Xin chao tu app Python offline!")\n'
                'for i in range(3):\n    print("dong", i)\n',
    "nhap_ten.py": 'ten = input("Ban ten gi? ")\nprint("Chao", ten)\n',
    "may_tinh.py": 'a = float(input("So a: "))\nb = float(input("So b: "))\n'
                   'print("Tong =", a + b)\nprint("Tich =", a * b)\n',
    "thu_vien_mau.py": '# Neu chua cai, app se hoi cai "humanize" (can Internet 1 lan)\n'
                       'import humanize\n'
                       'print(humanize.intcomma(1234567))\n'
                       'print(humanize.naturalsize(5 * 1024 * 1024))\n',
    "server_mau.py": (
        '# Chon file nay o tab Server, bam START. Doc cong tu bien PORT.\n'
        'import os\n'
        'from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler\n\n'
        'PORT = int(os.environ.get("PORT", "8080"))\n\n'
        'class H(BaseHTTPRequestHandler):\n'
        '    def do_GET(self):\n'
        '        body = ("Xin chao tu server Python! Duong dan: %s" % self.path).encode()\n'
        '        self.send_response(200)\n'
        '        self.send_header("Content-Type", "text/plain; charset=utf-8")\n'
        '        self.send_header("Content-Length", str(len(body)))\n'
        '        self.end_headers()\n'
        '        self.wfile.write(body)\n\n'
        'print("Server chay cong", PORT)\n'
        'ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()\n'
    ),
}

INDEX_HTML = (
    "<!doctype html><meta charset=utf-8>"
    "<meta name=viewport content='width=device-width,initial-scale=1'>"
    "<title>PyTerm</title><h1>Server chay OK</h1>"
    "<p>Sua file <code>index.html</code> trong thu muc www cua app.</p>\n"
)

# ten import -> ten tren PyPI (khi hai ten khac nhau)
ALIASES = {
    "PIL": "pillow", "cv2": "opencv-python", "bs4": "beautifulsoup4",
    "yaml": "pyyaml", "sklearn": "scikit-learn", "dateutil": "python-dateutil",
    "Crypto": "pycryptodome", "serial": "pyserial", "jwt": "pyjwt",
    "dotenv": "python-dotenv", "attr": "attrs", "docx": "python-docx",
    "pptx": "python-pptx", "skimage": "scikit-image", "fitz": "pymupdf",
    "git": "gitpython", "socks": "pysocks", "zmq": "pyzmq",
    "telegram": "python-telegram-bot", "discord": "discord.py",
    "OpenSSL": "pyopenssl", "magic": "python-magic",
}


# =====================================================================
#  Ha tang chung: log, dinh tuyen stdout theo thread, popup, dung thread
# =====================================================================
class LogView(ScrollView):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.label = Label(
            text="", font_name=MONO, size_hint_y=None,
            halign="left", valign="top",
        )
        self.label.bind(
            width=lambda i, w: setattr(i, "text_size", (w, None)),
            texture_size=lambda i, s: setattr(i, "height", max(s[1], 10)),
        )
        self.add_widget(self.label)

    def write(self, s):
        Clock.schedule_once(lambda dt: self._append(s), 0)

    def _append(self, s):
        t = self.label.text + s
        if len(t) > MAX_OUT:
            t = t[-MAX_OUT:]
        self.label.text = t
        Clock.schedule_once(lambda dt: setattr(self, "scroll_y", 0), 0.05)

    def clear(self, *_):
        self.label.text = ""


class Router:
    """stdout/stderr: thread nao gan `_log` thi ghi vao log do."""

    def __init__(self, orig):
        self.orig = orig

    def write(self, s):
        log = getattr(threading.current_thread(), "_log", None)
        if log is not None:
            if s:
                log.write(s)
        elif self.orig is not None:
            try:
                self.orig.write(s)
            except Exception:
                pass
        return len(s)

    def flush(self):
        pass

    def isatty(self):
        return False


def new_thread(target, log, args=()):
    t = threading.Thread(target=target, args=args, daemon=True)
    t._log = log
    return t


ACTIVE = {}  # thread ident -> {"ev": Event, "pop": Popup}


def release_prompt(ident):
    slot = ACTIVE.get(ident)
    if not slot:
        return
    slot["ev"].set()
    pop = slot.get("pop")
    if pop is not None:
        Clock.schedule_once(lambda dt: pop.dismiss(), 0)


def kill_thread(t):
    if t is not None and t.is_alive():
        release_prompt(t.ident)
        ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_ulong(t.ident), ctypes.py_object(KeyboardInterrupt)
        )


def ask_text(title, message, default="", ok="OK", cancel=None):
    """Hoi chuoi bang popup. Goi tu thread phu; tra None neu huy."""
    ev = threading.Event()
    box = {"v": None}
    slot = {"ev": ev, "pop": None}
    ident = threading.get_ident()
    ACTIVE[ident] = slot

    def build(dt):
        content = BoxLayout(orientation="vertical", spacing=6, padding=6)
        lbl = Label(text=message, halign="left", valign="middle")
        lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
        ti = TextInput(text=default, multiline=False, size_hint_y=None,
                       height=90, write_tab=False)
        row = BoxLayout(size_hint_y=None, height=90, spacing=6)
        okb = Button(text=ok)
        row.add_widget(okb)
        cb = None
        if cancel:
            cb = Button(text=cancel)
            row.add_widget(cb)
        content.add_widget(lbl)
        content.add_widget(ti)
        content.add_widget(row)
        pop = Popup(title=title, content=content, size_hint=(0.92, 0.55),
                    auto_dismiss=False)
        slot["pop"] = pop

        def done(*_):
            if box["v"] is None and not ev.is_set():
                box["v"] = ti.text
            pop.dismiss()

        okb.bind(on_release=done)
        ti.bind(on_text_validate=done)
        if cb is not None:
            cb.bind(on_release=lambda *_: pop.dismiss())
        pop.bind(on_dismiss=lambda *_: ev.set())
        pop.open()
        Clock.schedule_once(lambda dt: setattr(ti, "focus", True), 0.3)

    Clock.schedule_once(build, 0)
    ev.wait()
    ACTIVE.pop(ident, None)
    return box["v"]


def ask_input(prompt=""):
    """Thay the input() cua Python."""
    p = str(prompt)
    if p:
        sys.stdout.write(p)
    v = ask_text("input()", p or "Nhap:", "", ok="OK")
    v = v if v is not None else ""
    sys.stdout.write(v + "\n")
    return v


def offer_install(core, mod):
    """Module bi thieu -> hoi ten PyPI roi cai. Chay trong thread phu."""
    root = mod.split(".")[0]
    guess = ALIASES.get(root, root)
    ans = ask_text(
        "Thieu thu vien",
        "Khong tim thay module '%s'.\nTen tren PyPI de cai (sua neu can,\n"
        "co the nhieu ten cach nhau dau phay):" % root,
        guess, ok="CAI", cancel="BO QUA",
    )
    if ans and ans.strip():
        if pylibs.install_many(core.libs_dir, ans, lambda s: sys.stdout.write(s)):
            print("Xong. Bam CHAY lai.")
        return True
    return False


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def open_url(url):
    try:
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        Activity = autoclass("org.kivy.android.PythonActivity")
        Activity.mActivity.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    except Exception:
        import webbrowser
        webbrowser.open(url)


class Core:
    def __init__(self, user_dir):
        self.script_dir = os.path.join(user_dir, "scripts")
        self.www_dir = os.path.join(user_dir, "www")
        self.libs_dir = os.path.join(user_dir, "site-packages")

    def setup(self):
        for d in (self.script_dir, self.www_dir, self.libs_dir):
            os.makedirs(d, exist_ok=True)
        if self.libs_dir not in sys.path:
            sys.path.append(self.libs_dir)
        mark = os.path.join(self.script_dir, SAMPLES_MARK)
        if not os.path.exists(mark):
            for fn, txt in SAMPLES.items():
                p = os.path.join(self.script_dir, fn)
                if not os.path.exists(p):
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(txt)
            open(mark, "w").close()
        idx = os.path.join(self.www_dir, "index.html")
        if not os.path.exists(idx):
            with open(idx, "w", encoding="utf-8") as f:
                f.write(INDEX_HTML)
        try:
            os.chdir(self.script_dir)
        except OSError:
            pass

    def list_scripts(self):
        try:
            return sorted(f for f in os.listdir(self.script_dir) if f.endswith(".py"))
        except OSError:
            return []


# =====================================================================
#  Tab 1: Code
# =====================================================================
class CodeTab(BoxLayout):
    def __init__(self, core, **kw):
        super().__init__(orientation="vertical", spacing=4, padding=4, **kw)
        self.core = core
        self.thread = None

        top = BoxLayout(size_hint_y=None, height=84, spacing=4)
        self.spin = Spinner(text=NEW_LABEL, values=[NEW_LABEL], size_hint_x=0.4)
        self.spin.bind(text=self.on_pick)
        self.name = TextInput(hint_text="ten file", multiline=False,
                              size_hint_x=0.3, write_tab=False)
        top.add_widget(self.spin)
        top.add_widget(self.name)
        top.add_widget(Button(text="LUU", size_hint_x=0.15, on_release=self.save))
        top.add_widget(Button(text="XOA", size_hint_x=0.15, on_release=self.delete))
        self.add_widget(top)

        self.code = TextInput(
            text="", font_name=MONO, size_hint_y=0.42, multiline=True,
            background_color=(0.1, 0.1, 0.1, 1),
            foreground_color=(0.9, 0.9, 0.9, 1),
            cursor_color=(1, 1, 1, 1), write_tab=False,
        )
        self.add_widget(self.code)

        bar = BoxLayout(size_hint_y=None, height=96, spacing=4)
        self.run_btn = Button(text="CHAY", on_release=self.run_code)
        self.stop_btn = Button(text="DUNG", on_release=self.stop_code, disabled=True)
        self.log = LogView(size_hint_y=0.4)
        bar.add_widget(self.run_btn)
        bar.add_widget(self.stop_btn)
        bar.add_widget(Button(text="XOA KQ", on_release=self.log.clear))
        self.add_widget(bar)
        self.add_widget(self.log)

        self.refresh_spinner()
        files = core.list_scripts()
        if files:
            self.spin.text = files[0]

    def refresh_spinner(self):
        self.spin.values = [NEW_LABEL] + self.core.list_scripts()

    def on_pick(self, _s, value):
        if value == NEW_LABEL:
            self.code.text = ""
            self.name.text = ""
            return
        try:
            with open(os.path.join(self.core.script_dir, value), encoding="utf-8") as f:
                self.code.text = f.read()
            self.name.text = value[:-3]
        except Exception as e:
            self.log.write("Loi mo file: %s\n" % e)

    def clean_name(self):
        n = self.name.text.strip().replace("/", "_").replace("\\", "_")
        return n[:-3] if n.endswith(".py") else n

    def save(self, *_):
        n = self.clean_name()
        if not n:
            self.log.write("Hay nhap ten file truoc khi luu.\n")
            return
        fn = n + ".py"
        try:
            with open(os.path.join(self.core.script_dir, fn), "w", encoding="utf-8") as f:
                f.write(self.code.text)
        except Exception as e:
            self.log.write("Loi luu: %s\n" % e)
            return
        self.refresh_spinner()
        self.spin.unbind(text=self.on_pick)
        self.spin.text = fn
        self.spin.bind(text=self.on_pick)
        self.log.write("Da luu %s\n" % fn)

    def delete(self, *_):
        fn = self.spin.text
        if fn == NEW_LABEL:
            return
        try:
            os.remove(os.path.join(self.core.script_dir, fn))
        except Exception as e:
            self.log.write("Loi xoa: %s\n" % e)
            return
        self.log.write("Da xoa %s\n" % fn)
        self.refresh_spinner()
        self.spin.text = NEW_LABEL
        self.on_pick(self.spin, NEW_LABEL)

    def run_code(self, *_):
        if self.thread and self.thread.is_alive():
            return
        self.run_btn.disabled = True
        self.stop_btn.disabled = False
        self.log.write("\n>>> chay\n")
        self.thread = new_thread(self._worker, self.log, (self.code.text,))
        self.thread.start()

    def _worker(self, src):
        env = {"__name__": "__main__"}
        missing = None
        try:
            exec(compile(src, "<script>", "exec"), env)
        except KeyboardInterrupt:
            print("\n[Da dung]")
        except SystemExit:
            pass
        except ModuleNotFoundError as e:
            traceback.print_exc()
            missing = e.name
        except BaseException:
            traceback.print_exc()
        try:
            if missing:
                offer_install(self.core, missing)
        except BaseException:
            pass
        print(">>> xong")
        Clock.schedule_once(self._finish, 0)

    def _finish(self, dt):
        self.run_btn.disabled = False
        self.stop_btn.disabled = True

    def stop_code(self, *_):
        kill_thread(self.thread)


# =====================================================================
#  Tab 2: Server
# =====================================================================
def make_handler(directory, log):
    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=directory, **k)

        def log_message(self, fmt, *args):
            log.write("%s %s\n" % (self.address_string(), fmt % args))

    return H


class ServerTab(BoxLayout):
    def __init__(self, core, **kw):
        super().__init__(orientation="vertical", spacing=4, padding=4, **kw)
        self.core = core
        self.thread = None
        self.httpd = None
        self.url = None
        self.static = False

        top = BoxLayout(size_hint_y=None, height=84, spacing=4)
        self.src = Spinner(text=WWW_LABEL, values=[WWW_LABEL], size_hint_x=0.65)
        self.src.bind(on_press=lambda *_: self.refresh())
        self.port = TextInput(text="8080", multiline=False, input_filter="int",
                              size_hint_x=0.35, write_tab=False)
        top.add_widget(self.src)
        top.add_widget(self.port)
        self.add_widget(top)

        bar = BoxLayout(size_hint_y=None, height=96, spacing=4)
        self.start_btn = Button(text="START", on_release=self.start)
        self.stop_btn = Button(text="STOP", on_release=self.stop, disabled=True)
        self.open_btn = Button(text="MO WEB", on_release=self.open_web, disabled=True)
        bar.add_widget(self.start_btn)
        bar.add_widget(self.stop_btn)
        bar.add_widget(self.open_btn)
        self.add_widget(bar)

        self.info = Label(
            text="Chua chay.\nWeb tinh: dat file vao thu muc www cua app.\n"
                 "Hoac chon 1 script .py lam server (doc cong tu bien PORT).",
            size_hint_y=None, height=130, halign="left", valign="middle",
        )
        self.info.bind(size=lambda i, s: setattr(i, "text_size", s))
        self.add_widget(self.info)

        self.log = LogView()
        self.add_widget(self.log)

    def refresh(self):
        self.src.values = [WWW_LABEL] + self.core.list_scripts()

    def alive(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, *_):
        if self.alive():
            return
        try:
            port = int(self.port.text or "8080")
            if not 1024 <= port <= 65535:
                raise ValueError
        except ValueError:
            self.log.write("Cong phai tu 1024 den 65535.\n")
            return
        sel = self.src.text
        self.static = sel == WWW_LABEL
        self.log.write("\n>>> start %s cong %d\n" % (sel, port))
        if sel == WWW_LABEL:
            try:
                self.httpd = ThreadingHTTPServer(
                    ("0.0.0.0", port), make_handler(self.core.www_dir, self.log))
            except OSError as e:
                self.log.write("Khong mo duoc cong %d: %s\n" % (port, e))
                return
            self.thread = new_thread(self._serve_static, self.log)
        else:
            try:
                with open(os.path.join(self.core.script_dir, sel), encoding="utf-8") as f:
                    src = f.read()
            except Exception as e:
                self.log.write("Loi doc script: %s\n" % e)
                return
            os.environ["PORT"] = str(port)
            self.thread = new_thread(self._serve_script, self.log, (src, port))
        self.thread.start()
        self.start_btn.disabled = True
        self.stop_btn.disabled = False
        self.open_btn.disabled = False
        self.url = "http://127.0.0.1:%d" % port
        ip = local_ip()
        txt = "Dang chay.\nTren may nay: %s" % self.url
        if ip:
            txt += "\nMay khac cung WiFi: http://%s:%d" % (ip, port)
        self.info.text = txt + "\n(Giu app mo, dung tat man hinh de server khong bi ngat)"

    def _serve_static(self):
        try:
            self.httpd.serve_forever()
        finally:
            try:
                self.httpd.server_close()
            except Exception:
                pass
            print(">>> da dung")
            Clock.schedule_once(self._stopped, 0)

    def _serve_script(self, src, port):
        env = {"__name__": "__main__", "PORT": port}
        try:
            exec(compile(src, "<server>", "exec"), env)
        except KeyboardInterrupt:
            print("[Da dung]")
        except SystemExit:
            pass
        except BaseException:
            traceback.print_exc()
        print(">>> da dung")
        Clock.schedule_once(self._stopped, 0)

    def _stopped(self, dt):
        self.start_btn.disabled = False
        self.stop_btn.disabled = True
        self.open_btn.disabled = True
        self.info.text = "Da dung."

    def stop(self, *_):
        if self.static and self.httpd is not None:
            h = self.httpd
            threading.Thread(target=h.shutdown, daemon=True).start()
        else:
            kill_thread(self.thread)

    def open_web(self, *_):
        if self.url:
            open_url(self.url)


# =====================================================================
#  Tab 3: Thu vien
# =====================================================================
class LibsTab(BoxLayout):
    def __init__(self, core, **kw):
        super().__init__(orientation="vertical", spacing=4, padding=4, **kw)
        self.core = core
        self.busy = False

        row = BoxLayout(size_hint_y=None, height=96, spacing=4)
        self.entry = TextInput(hint_text="vd: humanize, rich==13.7.1",
                               multiline=False, size_hint_x=0.55, write_tab=False)
        self.entry.bind(on_text_validate=self.do_install)
        row.add_widget(self.entry)
        row.add_widget(Button(text="CAI", size_hint_x=0.2, on_release=self.do_install))
        row.add_widget(Button(text="GO", size_hint_x=0.25, on_release=self.do_remove))
        self.add_widget(row)

        bar = BoxLayout(size_hint_y=None, height=84, spacing=4)
        bar.add_widget(Button(text="DANH SACH", on_release=self.do_list))
        bar.add_widget(Button(text="XOA KQ", on_release=lambda *_: self.log.clear()))
        self.add_widget(bar)

        self.log = LogView()
        self.log.write(
            "Cai thu vien Python thuan tu PyPI (can Internet luc cai).\n"
            "Cai xong dung offline binh thuong.\n"
            "Thu vien co ma C (numpy, pandas...) khong cai o day duoc:\n"
            "them vao `requirements` trong buildozer.spec roi build lai.\n")
        self.add_widget(self.log)

    def _run(self, fn):
        if self.busy:
            self.log.write("Dang ban, doi chut...\n")
            return
        self.busy = True

        def work():
            try:
                fn()
            except BaseException:
                traceback.print_exc()
            finally:
                self.busy = False

        new_thread(work, self.log).start()

    def do_install(self, *_):
        text = self.entry.text
        self._run(lambda: print(
            "Xong." if pylibs.install_many(
                self.core.libs_dir, text, lambda s: sys.stdout.write(s))
            else "Co loi, xem thong bao tren."))

    def do_remove(self, *_):
        names = [n for n, _v in pylibs.parse_user_input(self.entry.text)] \
            if self.entry.text.strip() else []

        def work():
            if not names:
                print("Nhap ten thu vien can go.")
            for n in names:
                pylibs.uninstall(self.core.libs_dir, n, lambda s: sys.stdout.write(s))

        self._run(work)

    def do_list(self, *_):
        def work():
            items = pylibs.list_installed(self.core.libs_dir)
            if not items:
                print("Chua cai thu vien nao them.")
            for n, v in items:
                print("%s %s" % (n, v))

        self._run(work)


# =====================================================================
class PyTermApp(App):
    title = "PyTerm"

    def build(self):
        core = Core(self.user_data_dir)
        core.setup()
        sys.stdout = Router(sys.stdout)
        sys.stderr = Router(sys.stderr)
        builtins.input = ask_input

        tp = TabbedPanel(do_default_tab=False, tab_height=72,
                         tab_width=Window.width / 3.0)
        first = None
        for title, widget in (
            ("Code", CodeTab(core)),
            ("Server", ServerTab(core)),
            ("Thu vien", LibsTab(core)),
        ):
            item = TabbedPanelItem(text=title)
            item.add_widget(widget)
            tp.add_widget(item)
            first = first or item
        Clock.schedule_once(lambda dt: tp.switch_to(first), 0)
        return tp


if __name__ == "__main__":
    PyTermApp().run()
