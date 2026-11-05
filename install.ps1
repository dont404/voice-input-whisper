# Голосовой ввод — установщик только с Whisper
# Запуск: правый клик → «Выполнить с помощью PowerShell», или install.bat
$ErrorActionPreference = 'Stop'
$VoiceDir = $PSScriptRoot
Set-Location $VoiceDir

function Info($m)  { Write-Host "== $m" -ForegroundColor Cyan }
function Ok($m)    { Write-Host "   $m" -ForegroundColor Green }
function Warn($m)  { Write-Host "   $m" -ForegroundColor Yellow }

# --- 1. Python ---------------------------------------------------------------
Info "Проверка Python"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Warn "Python не найден — ставлю Python 3.12 через winget…"
    winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    $env:Path += ";$env:LOCALAPPDATA\Programs\Python\Python312;$env:LOCALAPPDATA\Programs\Python\Python312\Scripts"
} else {
    Ok "Python найден: $($python.Source)"
}
python --version

# --- 2. Библиотеки и модель Whisper ------------------------------------------
Info "Библиотеки (faster-whisper и остальные)"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet faster-whisper 'av<19' nvidia-cublas-cu12 nvidia-cudnn-cu12 sounddevice pyperclip keyboard pystray pillow
if ($LASTEXITCODE -ne 0) { throw "Не удалось установить библиотеки Python" }
Ok "библиотеки готовы"

Info "Модель Whisper large-v3-turbo (проверка или скачивание)…"
$WhisperDir = Join-Path $VoiceDir 'models'
$WhisperCode = "from faster_whisper import WhisperModel; import sys; WhisperModel('large-v3-turbo', device='cpu', compute_type='int8', download_root=sys.argv[1])"
$env:HF_HUB_ETAG_TIMEOUT = '60'
$env:HF_HUB_DOWNLOAD_TIMEOUT = '180'
$env:HF_ENDPOINT = 'https://hf-mirror.com'
python -c $WhisperCode $WhisperDir
if ($LASTEXITCODE -ne 0) {
    Warn "Зеркало не ответило — пробую Hugging Face напрямую…"
    $env:HF_ENDPOINT = 'https://huggingface.co'
    python -c $WhisperCode $WhisperDir
}
if ($LASTEXITCODE -ne 0) { throw "Не удалось подготовить модель Whisper. Запустите установщик ещё раз: скачивание продолжится с места обрыва." }
Ok "модель Whisper готова"

# --- 3. Ярлыки: рабочий стол + автозапуск -------------------------------------
$Wsh = New-Object -ComObject WScript.Shell
$Target = "$env:LOCALAPPDATA\Programs\Python\Python312\pythonw.exe"
if (-not (Test-Path $Target)) { $Target = (Get-Command pythonw).Source }
$ScriptArgs = '"' + (Join-Path $VoiceDir 'Голосовой_ввод.py') + '"'
$WorkDir = $VoiceDir

function Make-Shortcut($path) {
    $s = $Wsh.CreateShortcut($path)
    $s.TargetPath = $Target
    $s.Arguments = $ScriptArgs
    $s.WorkingDirectory = $WorkDir
    $s.IconLocation = "$Target,0"
    $s.Description = 'Голосовой ввод — F9 и говорите'
    $s.Save()
}

Info "Ярлык на рабочем столе"
$Desktop = [Environment]::GetFolderPath('Desktop')
Make-Shortcut (Join-Path $Desktop 'Голосовой ввод.lnk')
Ok (Join-Path $Desktop 'Голосовой ввод.lnk')

Info "Автозапуск (ярлык в папке «Автозагрузка»)"
$Startup = [Environment]::GetFolderPath('Startup')
Make-Shortcut (Join-Path $Startup 'Голосовой ввод.lnk')
Ok "программа будет стартовать вместе с Windows"

# --- 4. Запуск ----------------------------------------------------------------
Info "Запуск программы…"
Start-Process $Target -ArgumentList $ScriptArgs -WorkingDirectory $WorkDir
Write-Host ""
Write-Host "УСТАНОВКА ЗАВЕРШЕНА." -ForegroundColor Green
Write-Host "Программа живёт в трее (значок у часов). Удерживайте F9 и говорите,"
Write-Host "отпустили — текст вставлен. Правый клик по значку — меню (клавиши, выход)."
