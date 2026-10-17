import ctypes
import os
import subprocess
import sys
import time

exe = r"I:\AI\auto-voice-tiktok-shop\dist\AutoVoiceTikTokShop\AutoVoiceTikTokShop.exe"
print(f"Launching {exe}...")
proc = subprocess.Popen([exe])
print(f"Process PID: {proc.pid}")

time.sleep(3)

found_hwnd = None


def enum_windows_callback(hwnd, extra):
    global found_hwnd
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    if length > 0:
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value
        if "Auto Voice TikTok Shop" in title:
            # Kiem tra xem PID co trung voi proc.pid khong
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == proc.pid:
                found_hwnd = (hwnd, title)
                return False
    return True


WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)

print(f"EnumWindows found: HWND={found_hwnd[0] if found_hwnd else None}, Title={found_hwnd[1] if found_hwnd else None}")

# Su dung PowerShell qua file .ps1 de tranh escaping issue
ps_script = """
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$pid_target = $args[0]
$root = [System.Windows.Automation.AutomationElement]::RootElement
$condPid = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, [int]$pid_target)
$wnd = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $condPid)

if ($null -eq $wnd) {
    Write-Output "ERROR: Window not found for PID $pid_target"
    exit 1
}

Write-Output "WINDOW_NAME: $($wnd.Current.Name)"

$tabCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::TabItem)
$tabs = $wnd.FindAll([System.Windows.Automation.TreeScope]::Descendants, $tabCond)

Write-Output "TAB_COUNT: $($tabs.Count)"
for ($i = 0; $i -lt $tabs.Count; $i++) {
    Write-Output "TAB_NAME: $($tabs.Item($i).Current.Name)"
}
"""

with open("scripts/_temp_verify.ps1", "w", encoding="utf-8") as f:
    f.write(ps_script)

res = subprocess.run(
    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts/_temp_verify.ps1", str(proc.pid)],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)

print("--- UI Automation Output ---")
print(res.stdout)
if res.stderr:
    print("Stderr:", res.stderr)

try:
    os.remove("scripts/_temp_verify.ps1")
except Exception:
    pass

proc.terminate()
try:
    proc.wait(timeout=3)
except subprocess.TimeoutExpired:
    proc.kill()

print("Process terminated.")
