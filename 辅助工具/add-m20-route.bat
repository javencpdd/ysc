@echo off
REM ============================================================
REM  add-m20-route.bat
REM  Run as Administrator: add a PERSISTENT static route from this
REM  PC to the M20 Pro internal subnet 10.21.31.0/24 via the AOS
REM  gateway 192.168.0.196.
REM  Result: PC can reach 10.21.31.103(AOS)/.104(GOS)/.106(NOS)
REM ============================================================
setlocal
set ROUTE_NET=10.21.31.0
set ROUTE_MASK=255.255.255.0
set GATEWAY=192.168.0.196

echo [0/3] Checking gateway AOS (192.168.0.196) reachability...
ping -n 1 -w 1500 %GATEWAY% >nul 2>&1
if errorlevel 1 (
    echo [!] WARNING: gateway %GATEWAY% not reachable. Make sure AOS is
    echo     connected to the Tenda WiFi. The route will still be written,
    echo     but traffic only works when AOS is online.
) else (
    echo [ok] Gateway reachable.
)

echo [1/3] Removing any stale route (ignore if none)...
route delete %ROUTE_NET% >nul 2>&1

echo [2/3] Adding PERSISTENT route (route -p: survives reboot/reconnect)...
route -p add %ROUTE_NET% mask %ROUTE_MASK% %GATEWAY%
if errorlevel 1 (
    echo [!] FAILED: route may already exist, or this window is NOT admin.
    echo     Right-click this file and choose "Run as administrator".
    goto :end
)

echo [3/3] Relevant entries in route table:
route print | findstr /C:"10.21.31.0"

echo.
echo DONE. Test with:  ping 10.21.31.103   ping 10.21.31.104   ping 10.21.31.106
:end
endlocal
pause
