$ErrorActionPreference = "Stop"
$root   = "A:\deepseek work area\PCClean"
$src    = "A:\deepseek work area\installer"
$build  = Join-Path $env:TEMP "pcclean_build"
$stage  = Join-Path $build "stage"
$csc    = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$zip    = Join-Path $build "payload.zip"
$outExe = Join-Path $build "PCClean_Setup.exe"

Write-Host "1/6 prepare build dir"
if (Test-Path $build) { Remove-Item $build -Recurse -Force }
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Copy-Item (Join-Path $src "Setup.cs") $build -Force
Copy-Item (Join-Path $src "Uninstall.cs") $build -Force
Copy-Item (Join-Path $src "setup.manifest") $build -Force
Copy-Item (Join-Path $src "uninstall.manifest") $build -Force
Copy-Item (Join-Path $src "setup_asinvoker.manifest") $build -Force

Write-Host "2/6 compile uninstaller"
& $csc /nologo /target:winexe /codepage:65001 "/win32manifest:$build\uninstall.manifest" "/out:$stage\Uninstall_PCClean.exe" /r:System.Windows.Forms.dll "$build\Uninstall.cs"
if ($LASTEXITCODE -ne 0) { throw "uninstaller compile failed" }

Write-Host "3/6 copy app files"
& robocopy $root $stage /E /XD __pycache__ build dist .github /XF *.pyc smoke_test.py collect_test.py launch_test.py executor_test.py dialog_test.py space_test.py launcher.cs app.manifest /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed: $LASTEXITCODE" }

Write-Host "4/6 create payload.zip"
Add-Type -AssemblyName System.IO.Compression.FileSystem
if (Test-Path $zip) { Remove-Item $zip -Force }
[System.IO.Compression.ZipFile]::CreateFromDirectory($stage, $zip, [System.IO.Compression.CompressionLevel]::Optimal, $false)
"payload.zip = {0:N1} MB" -f ((Get-Item $zip).Length / 1MB)

Write-Host "5/6 compile setup (admin) + test build (asInvoker)"
& $csc /nologo /target:winexe /codepage:65001 "/win32manifest:$build\setup.manifest" "/out:$outExe" "/resource:$zip,payload.zip" /r:System.Windows.Forms.dll "$build\Setup.cs"
if ($LASTEXITCODE -ne 0) { throw "setup compile failed" }
& $csc /nologo /target:winexe /codepage:65001 "/win32manifest:$build\setup_asinvoker.manifest" "/out:$build\Setup_test.exe" "/resource:$zip,payload.zip" /r:System.Windows.Forms.dll "$build\Setup.cs"
if ($LASTEXITCODE -ne 0) { throw "test build compile failed" }

Write-Host "6/6 copy final"
Copy-Item $outExe "A:\deepseek work area\PCClean_Setup.exe" -Force
"PCClean_Setup.exe = {0:N1} MB" -f ((Get-Item "A:\deepseek work area\PCClean_Setup.exe").Length / 1MB)
if (Test-Path "A:\deepseek work area\_stage") { Remove-Item "A:\deepseek work area\_stage" -Recurse -Force }
"BUILD OK"
