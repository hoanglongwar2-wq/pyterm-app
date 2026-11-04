[app]
title = PyTerm
package.name = pyterm
package.domain = org.riengtoi
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.3

# Muon them thu vien (chay offline), them vao day, vi du:
# requirements = python3,kivy,numpy
requirements = python3,kivy,pyjnius,openssl,certifi,sqlite3

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,WAKE_LOCK
android.archs = arm64-v8a
android.api = 33
android.minapi = 21
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
