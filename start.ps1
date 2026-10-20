param(
    [switch]$Local,
    [switch]$Quantized,
    [switch]$Doctor,
    [switch]$Share,
    [int]$Port = 7860
)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root
$UvCommand = Get-Command uv -ErrorAction SilentlyContinue
$Uv = if ($UvCommand) { $UvCommand.Source } else { Join-Path $HOME ".local\bin\uv.exe" }
if (!(Test-Path $Uv)) {
    Write-Host "Installing uv from https://astral.sh/uv/install.ps1 into your user account."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $Installer = Join-Path ([IO.Path]::GetTempPath()) ("longbook-uv-" + [Guid]::NewGuid() + ".ps1")
    try {
        Invoke-WebRequest "https://astral.sh/uv/install.ps1" -OutFile $Installer -UseBasicParsing
        $env:UV_NO_MODIFY_PATH = "1"
        & $Installer
        if (!(Test-Path $Uv)) { throw "uv not found after installation; check UV_INSTALL_DIR." }
    } finally {
        if (Test-Path $Installer) { Remove-Item $Installer -Force }
    }
}
$env:GRADIO_ANALYTICS_ENABLED = "False"
$env:HF_HUB_DISABLE_TELEMETRY = "1"
$ArgsList = @("run", "--python", "3.11", "--project", $Root)
if ($Local -or $Quantized) { $ArgsList += @("--extra", "local") }
if ($Quantized) { $ArgsList += @("--extra", "quantized") }
if ($Doctor) {
    $ArgsList += @("longbook", "doctor")
} else {
    $ArgsList += @("longbook", "ui", "--port", "$Port")
    if ($Share) { $ArgsList += "--share" }
}
& $Uv @ArgsList
if ($LASTEXITCODE -ne 0) { throw "LongBook exited with code $LASTEXITCODE." }
