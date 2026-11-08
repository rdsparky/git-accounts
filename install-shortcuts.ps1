# Creates "Git Accounts" shortcuts (with icon) in the Start menu and on the Desktop.
# Run: right-click > Run with PowerShell, or double-click install-shortcuts.cmd
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw = Join-Path $env:WINDIR "pyw.exe"
if (-not (Test-Path $pyw)) { throw "Python launcher (pyw.exe) not found; install Python 3.10+ from python.org (with tcl/tk)" }
$targets = @(
    (Join-Path ([Environment]::GetFolderPath("Programs")) "Git Accounts.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Git Accounts.lnk")
)
$shell = New-Object -ComObject WScript.Shell
foreach ($lnk in $targets) {
    $s = $shell.CreateShortcut($lnk)
    $s.TargetPath = $pyw
    $s.Arguments = "-3 `"$(Join-Path $here 'GitAccounts.pyw')`""
    $s.WorkingDirectory = $here
    $s.IconLocation = (Join-Path $here "assets\gitaccounts.ico") + ",0"
    $s.Description = "Switch and check Git/GitHub accounts per repository"
    $s.Save()
    Write-Host "Created $lnk"
}
