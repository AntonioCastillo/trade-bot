@echo off
REM ============================================================
REM  ARRANQUE UNICO DEL SISTEMA  --  doble clic aqui
REM  Lanza el bot (y el sniper dentro del mismo proceso, si esta
REM  activado en config.yaml). Una sola ventana. Se reinicia solo
REM  si el proceso cae de forma dura.
REM  Para detener: cierra la ventana o pulsa Ctrl+C.
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"
title TradeBot

:loop
echo [%date% %time%] Iniciando TradeBot...
python scripts\run.py
if %errorlevel%==0 goto end
echo [%date% %time%] Caida inesperada (codigo %errorlevel%). Reiniciando en 10s...
timeout /t 10 /nobreak >nul
goto loop

:end
echo [%date% %time%] TradeBot detenido limpiamente.
pause
