chcp 65001
@echo off
REM 运行桌面上的Python程序
echo 正在运行桌面上的Python程序...
python "C:\Users\35975\Desktop\fund\app.py"

REM 如果上面的命令失败，尝试使用python3
if errorlevel 1 (
    echo 尝试使用python3...
    python3 "C:\Users\35975\Desktop\test.py"
)

REM 如果还是失败，提示用户
if errorlevel 1 (
    echo 无法运行Python程序，请检查：
    echo 1. Python是否正确安装
    echo 2. Python是否已添加到系统PATH
    echo 3. test.py文件是否存在
)

REM 暂停窗口，查看输出结果
pause