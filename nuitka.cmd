@echo off
REM ============================================================
REM  Nuitka build script (standalone mode) - counterpart of pyinstaller.cmd
REM  Usage: run from cmd, or double-click.
REM  NOTE: keep this file ASCII-only. cmd parses it with the ANSI
REM  code page (GBK on zh-CN); UTF-8 comments get mangled and may be
REM  executed as commands.
REM ============================================================
REM  Prerequisites:
REM   1. A CPython that Nuitka accepts (python.org recommended;
REM      MS Store Python is flagged but seems accepted by Nuitka 4.x)
REM   2. pip install nuitka
REM   3. C compiler: MSVC (Visual Studio Build Tools, C++ workload)
REM ============================================================
REM
REM  ############################################################
REM  ##  NEVER LET NUITKA USE zig.  --msvc=latest IS MANDATORY.  ##
REM  ############################################################
REM
REM  What this prevents: the exe pops "X has stopped working" (or never
REM  shows a window at all) on SOME machines - typically a friend's or a
REM  new PC - while the very same file (identical SHA256) runs fine on the
REM  build machine AND inside Windows Sandbox on that build machine.
REM
REM  Cause: zig targets the BUILD MACHINE'S CPU by default (Nuitka passes
REM  neither -target nor -mcpu). Measured on this dev machine
REM  (AMD A10-9600P, Excavator), counting AVX/AVX2/FMA/BMI instructions:
REM        zig build   -> 5089   in the exe
REM        MSVC build  ->    0   (baseline x86-64)
REM        official python313.dll / qt6core.dll -> 0 / 179 (vendor-chosen)
REM  A zig-built exe therefore REQUIRES AVX/AVX2/BMI at runtime. On a CPU
REM  without them it takes an illegal instruction (0xC000001D) during
REM  interpreter startup, before any window is created -> Windows shows
REM  "stopped working". CPUs without AVX2 include Windows-on-ARM's x64
REM  emulation and pre-2011 Intel. Same bytes + different CPU = different
REM  result, which is why this looks machine-specific but is not.
REM
REM  Also: Nuitka does NOT reliably auto-detect VS Build Tools. On this
REM  machine it silently fell back to zig even though VS 2026 Build Tools
REM  (MSVC 14.5) was installed. So always pass --msvc=latest explicitly.
REM  To see which compiler a build actually used, open
REM      <name>.build\scons-report.txt
REM  and look at CC= / CCCOM= : it must be cl.exe, never ziglang\zig.exe.
REM
REM  VERIFY BEFORE SHIPPING (this is the acceptance test):
REM      python nuitka_bisect\scan_isa.py <path-to-exe>
REM  It must print "AVX/AVX2/FMA  : 0". Anything else = do not ship.
REM  ============================================================
REM
REM  ============================================================
REM  CONSOLE MODE (measured on this machine, not guessed)
REM  ============================================================
REM  --windows-console-mode=attach (used below) does exactly what we want:
REM
REM    mode      launched from cmd               double-clicked
REM    attach    console=YES -> the log lines     console=NO -> nobody
REM              appear in that cmd window                   opens a window
REM    force     console=YES                      console=YES -> a console
REM    (default)                                             window pops up
REM    hide      console=YES                      console hidden (but a
REM                                                          console is
REM                                                          still spawned)
REM    disable   no console at all; all output is discarded
REM
REM  Measured two ways: GetConsoleWindow() called inside the exe, and the PE
REM  subsystem byte:
REM      attach -> Subsystem = 2 (GUI)      => cmd does NOT wait for it
REM      force  -> Subsystem = 3 (Console)  => cmd waits for it
REM  So with attach, running from cmd shows the log but the prompt comes back
REM  immediately. If you need to wait:   start /wait "Book Mindustry Launcher.exe"
REM
REM  IMPORTANT consequence: on a double-click there is NO console, so every
REM  print() and every traceback is silently thrown away. When a build dies on
REM  someone else's machine, either
REM     a) have them run it FROM CMD  (cd /d <folder>  then the exe name), or
REM     b) hand them a temporary DIAGNOSTIC copy built with =force, or
REM     c) rely on the app's own file log (BML\logs) plus faulthandler.
REM  ============================================================

REM Point PYTHON at your python.org install; or use "python" if in PATH
set PYTHON=C:\Users\Book\Desktop\BookMDTLauncher\python\python.exe

%PYTHON% -m nuitka ^
  --onefile ^
  --enable-plugin=pyside6 ^
  --include-qt-plugins=sensible ^
  --include-data-dir=src=src ^
  --windows-console-mode=attach ^
  --msvc=latest ^
  --output-filename="Book Mindustry Launcher.exe" ^
  main.py

REM Notes:
REM   --msvc=latest              FORCE MSVC. Never use --zig (see above).
REM   --onefile                  single-file mode: the bootstrap unpacks to a
REM                              temp dir on EVERY run. Not used here - folder
REM                              mode starts faster and is far easier to debug.
REM                              If you do switch: --onefile-tempdir-spec=
REM                              {PROGRAM_DIR}/BML/dlls reuses one unpack dir,
REM                              but that dir must be writable and leftover
REM                              files are never cleaned automatically.
REM   --enable-plugin=pyside6    collect PySide6 Qt plugins/DLLs automatically
REM   --include-data-dir=src=src pack non-code files under src (json/qss/images);
REM                              .py files are treated as code and compiled,
REM                              not copied
REM   --windows-console-mode=attach  no console window on double-click.
REM                              For DEBUGGING use =force so you can actually
REM                              read tracebacks and fatal errors. A windowed
REM                              exe hides every startup error, which is what
REM                              makes "stopped working" so hard to diagnose.
REM   --output-filename          output exe name
REM
REM   BML/ is intentionally NOT packed: it is runtime user data next to the
REM   exe (settings.json, logs, .tmp download cache), resolved by getPath()'s
REM   "other paths -> exe directory" branch.
REM
REM   First compile is slow; later builds reuse caches.
REM
REM   KNOWN RISK: this project relies heavily on QThread + signals
REM   (QDownloader/QThTimer), and QThTimer's teardown of dedicated timers is
REM   timing sensitive. Under PyInstaller onefile that teardown produced
REM   0xC0000374 heap corruption in 2 of 10 runs, and it runs on aboutToQuit,
REM   i.e. on every exit. See nuitka_bisect\test_5_qthtimer_real.py, which
REM   exercises the real QThTimer code.
REM
REM   SPEED TUNING:
REM     - LTO (--lto=yes) works with MSVC via LTCG. It did NOT work with zig:
REM       zig + LTO dies at link with undefined frexpf/mempcpy/strtok_r from
REM       zigc.lib - another reason not to use zig.
REM     - PGO (--pgo) profiles a real run and needs an automated GUI smoke
REM       run to collect data. Optional, bigger win, much longer build.
REM       Not enabled.
REM     - --static-libpython=yes NOT usable here: this python install has no
REM       static libpython. Skip.
pause
