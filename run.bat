@echo off
:: 自动切换到这个run.bat文件所在的文件夹
cd /d "%~dp0"
:: 运行当前文件夹里的app.py（这里的app.py要和你的真实文件名完全一致）
python app.py
pause