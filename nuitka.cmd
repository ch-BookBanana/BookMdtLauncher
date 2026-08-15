@echo off
REM ============================================================
REM  Nuitka build script (onefile mode) - counterpart of pyinstaller.cmd
REM  Usage: run from cmd, or double-click.
REM  NOTE: keep this file ASCII-only. cmd parses it with the ANSI
REM  code page (GBK on zh-CN systems); UTF-8 comments get mangled
REM  and may be executed as commands.
REM ============================================================
REM  Prerequisites:
REM   1. A CPython that Nuitka accepts (python.org recommended;
REM      MS Store Python is flagged but seems accepted by Nuitka 4.x)
REM   2. pip install nuitka
REM   3. C compiler: MSVC (VS2022 Build Tools, recommended) or
REM      zig (--zig). MinGW64 does NOT work with Python 3.13+
REM ============================================================

REM Point PYTHON at your python.org install; or use "python" if in PATH
set PYTHON=C:\Users\Book\Desktop\BookMDTLauncher\python\python.exe

%PYTHON% -m nuitka ^
  --onefile ^
  --enable-plugin=pyqt5 ^
  --include-data-dir=src=src ^
  --windows-console-mode=disable ^
  --output-filename="Book Mindustry Launcher.exe" ^
  main.py

REM Notes:
REM   --onefile                  single-file mode (bootstrap unpacks to temp dir)
REM   NO --lto with zig:         --lto=yes + zig dies at link with
REM                              "lld-link: error: undefined symbol:
REM                              frexpf/mempcpy/strtok_r/__DENORM/__QNAN..."
REM                              referenced by zigc.lib(zigc_zcu.obj). zigc.lib is
REM                              zig's compiler-rt; it references glibc-only symbols
REM                              (mempcpy, strtok_r, long-double math...) that the
REM                              MSVC CRT does not export. Without LTO those code
REM                              paths stay dead and are never pulled in; with LTO
REM                              the whole library is loaded and every symbol must
REM                              resolve -> link fails. So: zig = no LTO (default).
REM                              Want LTO? Install VS2022 Build Tools (C++ workload)
REM                              and let Nuitka pick MSVC (--msvc=latest); MSVC LTCG
REM                              works. For this Qt launcher (I/O bound) LTO's gain
REM                              is marginal anyway.
REM   --enable-plugin=pyqt5      collect PyQt5 Qt plugins/DLLs automatically
REM   --include-data-dir=src=src pack non-code files under src (json/qss/images);
REM                              .py files are treated as code and compiled, not copied
REM   --windows-console-mode=disable  same as PyInstaller -w (GUI, no console)
REM   --onefile-tempdir-spec={PROGRAM_DIR}/BML/dlls
REM                              reuse unpacked files in "BML/dlls" next to the
REM                              exe instead of unpacking to a fresh temp dir on
REM                              EVERY run (biggest onefile startup cost). Nuitka
REM                              re-unpacks when the exe changes. Safe here: app
REM                              is single-instance (QLocalServer), no same-dir
REM                              double-lock issue.
REM                              WATCH OUT: fixed dir name -> leftover files from
REM                              older builds are NOT auto-cleaned (only
REM                              overwritten); and the exe location must be
REM                              writable (Desktop is fine; Program Files is not).
REM   --output-filename          output exe name
REM
REM   BML/ is intentionally NOT packed: it is runtime user data next to the
REM   exe (settings.json, logs, .tmp download cache), resolved by getPath()'s
REM   "other paths -> exe directory" branch.
REM
REM   First compile is slow (downloads/compiles C deps); later builds use cache.
REM
REM   KNOWN RISK: Nuitka's pyqt5 plugin has known bugs with callbacks and
REM   threading (see https://nuitka.net/info/pyqt5.html). This project relies
REM   heavily on QThread + signals (QDownloader/QThTimer). Build succeeds but
REM   runtime behavior must be verified; PySide6 migration is the official fix.
REM
REM   SPEED TUNING:
REM     - LTO above trades build time for runtime speed (already enabled).
REM     - PGO (--pgo) profiles a real run and re-compiles optimized; needs an
REM       automated GUI smoke run to collect data first. Optional, bigger win,
REM       much longer build. Not enabled.
REM     - Install zstandard ("pip install zstandard") to compress the onefile
REM       payload -> smaller exe, faster first unpack. Auto-detected.
REM     - --static-libpython=yes NOT usable here: this python install has no
REM       static libpython. Skip.
pause