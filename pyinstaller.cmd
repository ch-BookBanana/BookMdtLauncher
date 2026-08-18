@echo off
python\Scripts\pyinstaller.exe ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "BookMdtLauncher" ^
    --add-data "src;src" ^
    main.py

pause