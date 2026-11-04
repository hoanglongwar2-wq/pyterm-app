"""Cai / go thu vien Python thuan (pure-Python) tu PyPI luc app dang chay.

Khong dung pip. Chi cai duoc goi co wheel "py3-none-any" (khong co ma C).
Thu vien native (numpy, pandas, ...) phai them vao `requirements` luc build APK.
"""
import csv
import hashlib
import importlib
import io
import json
import operator
import os
import re
import shutil
import ssl
import sys
import urllib.error
import urllib.request
import zipfile

UA = "PyTerm/0.3"
NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._\-]*)(?:==([A-Za-z0-9._!+\-]+))?$")

OPS = {
    "<": operator.lt, "<=": operator.le, ">": operator.gt,
    ">=": operator.ge, "==": operator.eq, "!=": operator.ne,
}
ENV = {
    "sys_platform": "linux",
    "platform_system": "Linux",
    "os_name": "posix",
    "implementation_name": "cpython",
    "platform_python_implementation": "CPython",
}


def norm(name):
    return re.sub(r"[-_.]+", "_", name).lower()


def parse_user_input(text):
    """'rich, humanize==4.9.0' -> [('rich', None), ('humanize', '4.9.0')]"""
    out = []
    for tok in re.split(r"[\s,;]+", text.strip()):
        if not tok:
            continue
        m = NAME_RE.match(tok)
        if not m:
            raise ValueError("Khong hop le: %s (dung dang ten hoac ten==phienban)" % tok)
        out.append((m.group(1), m.group(2)))
    return out


# ---------------- mang ----------------
def _ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
        return r.read()


# ---------------- marker phu thuoc (khong dung eval) ----------------
def _atom(a):
    a = a.strip().strip("()").strip()
    m = re.match(r"""^(\w+)\s*(<=|>=|==|!=|<|>|~=)\s*['"]([^'"]*)['"]$""", a)
    if not m:
        return True
    var, op, val = m.groups()
    if op == "~=":
        return True
    if var in ("python_version", "python_full_version"):
        n = 3 if var == "python_full_version" else 2
        try:
            want = tuple(int(x) for x in val.split(".") if x.isdigit())
        except ValueError:
            return True
        cur = tuple(sys.version_info[:n])[:max(len(want), 1)]
        return OPS[op](cur, want)
    cur = ENV.get(var)
    if cur is None or op not in ("==", "!="):
        return True
    return OPS[op](cur, val)


def marker_ok(marker):
    if re.search(r"\bextra\b", marker):
        return False
    for grp in re.split(r"\s+or\s+", marker):
        if all(_atom(x) for x in re.split(r"\s+and\s+", grp)):
            return True
    return False


def parse_req(req):
    base, _, marker = req.partition(";")
    m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)", base)
    if not m:
        return None
    if marker.strip() and not marker_ok(marker):
        return None
    return m.group(1)


# ---------------- quan ly goi da cai ----------------
def find_dist(libs_dir, name):
    key = norm(name)
    try:
        entries = os.listdir(libs_dir)
    except OSError:
        return []
    out = []
    for e in entries:
        if e.endswith(".dist-info"):
            n, _, v = e[:-len(".dist-info")].rpartition("-")
            if norm(n) == key:
                out.append((e, n, v))
    return out


def installed_version(libs_dir, name):
    d = find_dist(libs_dir, name)
    if d:
        return d[0][2]
    try:
        import importlib.metadata as md
        return md.version(name)
    except Exception:
        return None


def list_installed(libs_dir):
    try:
        entries = os.listdir(libs_dir)
    except OSError:
        return []
    out = []
    for e in entries:
        if e.endswith(".dist-info"):
            n, _, v = e[:-len(".dist-info")].rpartition("-")
            out.append((n, v))
    return sorted(out, key=lambda x: x[0].lower())


def pick_wheel(data):
    for f in data.get("urls", []):
        fn = f.get("filename", "")
        if f.get("packagetype") == "bdist_wheel" and fn.endswith(".whl"):
            parts = fn[:-4].split("-")
            if len(parts) >= 5 and parts[-1] == "any" and parts[-2] == "none" \
                    and "py3" in parts[-3]:
                return f
    return None


def _inside(base, path):
    base = os.path.realpath(base)
    path = os.path.realpath(path)
    return path == base or path.startswith(base + os.sep)


def install(libs_dir, name, say, ver=None, seen=None, depth=0):
    """Tra ve True neu cai xong (hoac da co). say(str) de in thong bao."""
    seen = seen if seen is not None else set()
    key = norm(name)
    if key in seen:
        return True
    seen.add(key)
    if depth > 8:
        say("Qua nhieu tang phu thuoc o %s\n" % name)
        return False

    cur = installed_version(libs_dir, name)
    if cur and (ver is None or ver == cur):
        say("Da co %s %s\n" % (name, cur))
        return True

    url = "https://pypi.org/pypi/%s/%sjson" % (name, ("%s/" % ver) if ver else "")
    say("Tim %s tren PyPI...\n" % name)
    try:
        data = json.loads(http_get(url))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            say("Khong tim thay '%s' tren PyPI (kiem tra lai ten/phien ban).\n" % name)
        else:
            say("PyPI tra loi loi %s.\n" % e.code)
        return False
    except Exception as e:
        say("Loi mang: %s\nCan co Internet de cai thu vien (chi luc cai).\n" % e)
        return False

    info = data.get("info", {})
    wheel = pick_wheel(data)
    if wheel is None:
        say("'%s' khong co ban thuan Python (co ma C/native hoac chi co ban nguon).\n"
            "Cach xu ly: them ten vao dong `requirements` trong buildozer.spec roi build lai APK.\n"
            % name)
        return False

    rp = info.get("requires_python") or ""
    m = re.search(r">=\s*(\d+)\.(\d+)", rp)
    if m and (int(m.group(1)), int(m.group(2))) > tuple(sys.version_info[:2]):
        say("Canh bao: %s can Python %s, app dang dung %d.%d - co the loi khi import.\n"
            % (name, rp, sys.version_info[0], sys.version_info[1]))

    say("Tai %s (%d KB)...\n" % (wheel["filename"], wheel.get("size", 0) // 1024))
    try:
        blob = http_get(wheel["url"], timeout=120)
    except Exception as e:
        say("Loi tai file: %s\n" % e)
        return False

    want = (wheel.get("digests") or {}).get("sha256")
    if want and hashlib.sha256(blob).hexdigest() != want:
        say("Sai ma kiem tra sha256, huy cai.\n")
        return False

    if ver and cur and ver != cur:
        uninstall(libs_dir, name, lambda s: None)

    try:
        os.makedirs(libs_dir, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for mem in z.infolist():
                if not _inside(libs_dir, os.path.join(libs_dir, mem.filename)):
                    raise ValueError("file zip khong an toan: %s" % mem.filename)
            z.extractall(libs_dir)
    except Exception as e:
        say("Loi giai nen: %s\n" % e)
        return False

    importlib.invalidate_caches()
    say("Da cai %s %s\n" % (info.get("name", name), info.get("version", "")))

    ok = True
    for r in info.get("requires_dist") or []:
        dep = parse_req(r)
        if dep and not install(libs_dir, dep, say, None, seen, depth + 1):
            say("Khong cai duoc phu thuoc: %s\n" % dep)
            ok = False
    return ok


def install_many(libs_dir, text, say):
    try:
        items = parse_user_input(text)
    except ValueError as e:
        say(str(e) + "\n")
        return False
    if not items:
        say("Chua nhap ten thu vien.\n")
        return False
    seen = set()
    ok = True
    for name, ver in items:
        ok = install(libs_dir, name, say, ver, seen) and ok
    return ok


def uninstall(libs_dir, name, say):
    found = find_dist(libs_dir, name)
    if not found:
        say("Khong co '%s' trong thu vien da cai.\n" % name)
        return False
    for e, n, v in found:
        di = os.path.join(libs_dir, e)
        dirs = set()
        try:
            with open(os.path.join(di, "RECORD"), newline="", encoding="utf-8") as f:
                for row in csv.reader(f):
                    if not row:
                        continue
                    p = os.path.join(libs_dir, row[0])
                    if _inside(libs_dir, p) and os.path.isfile(p):
                        os.remove(p)
                        dirs.add(os.path.dirname(p))
        except OSError:
            pass
        for d in sorted(dirs, key=len, reverse=True):
            cur = d
            while _inside(libs_dir, cur) and os.path.realpath(cur) != os.path.realpath(libs_dir):
                try:
                    os.rmdir(cur)
                except OSError:
                    break
                cur = os.path.dirname(cur)
        shutil.rmtree(di, ignore_errors=True)
        say("Da go %s %s\n" % (n, v))
    importlib.invalidate_caches()
    return True
