# PyTerm - app Python offline cho Android

Chay Python hoan toan offline. Co: soan code, CHAY / DUNG, input() bang popup,
luu - mo - xoa script (luu trong bo nho rieng cua app).

## Build APK mien phi bang GitHub (chi can dien thoai)

1. Vao github.com, dang ky / dang nhap, tao repo moi (vd: `pyterm`).
2. Trong repo, bam **Add file > Create new file**:
   - Ten `main.py` -> dan noi dung file main.py -> Commit.
   - Ten `buildozer.spec` -> dan noi dung -> Commit.
   - Ten `.github/workflows/build.yml` (go dau `/` de tu tao thu muc) -> dan noi dung build.yml -> Commit.
3. Vao tab **Actions**. Neu chua tu chay, chon **Build APK > Run workflow**.
4. Doi 15-30 phut (lan dau lau). Xong, bam vao lan chay, keo xuong **Artifacts**, tai `apk` (file zip), giai nen ra file `.apk`.
5. Cai APK (cho phep "cai tu nguon khong ro").

## 3 tab

- **Code**: soan, luu, chay script. Neu script thieu module, app hoi ten tren PyPI va cai luon (can Internet 1 lan), roi bam CHAY lai.
- **Server**: chon "Web tinh" (thu muc www) hoac 1 script .py lam server (doc cong tu bien PORT). May khac cung WiFi vao duoc bang IP hien tren man hinh.
- **Thu vien**: go ten (vd `humanize, rich==13.7.1`) bam CAI / GO / DANH SACH.

Thu vien chi cai duoc loai Python thuan. Loai co ma C (numpy, pandas, pillow...) phai them vao `requirements` trong buildozer.spec roi build lai.

## Dung app

- Chon `[ Script moi ]`, go code, nhap ten file, bam LUU.
- CHAY de chay, DUNG de ngat script dang chay (vd vong lap vo han).
- Script mo / ghi file se ghi vao thu muc scripts cua app.

## Them thu vien

Sua dong `requirements` trong `buildozer.spec`, vd `python3,kivy,numpy`.
Chi thu vien co recipe cua python-for-android moi dung duoc (numpy, sqlite3, pillow...).
`pip install` luc dang chay khong dung duoc (khong co mang va khong co pip).

## Luu y

- Day khong phai terminal Linux day du nhu Termux (khong co lenh shell).
- Build lan dau co the loi; mo log trong Actions va gui cho toi de sua.
