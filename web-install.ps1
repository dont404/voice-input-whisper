$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$ArchiveUrl = 'https://github.com/dont404/voice-input-whisper/releases/latest/download/GolosovoyVvod.zip'
$ExpectedHash = '59df30f3625382a2f89a33ade0165026f16d22cee05a9ba04c4789c803383108'
$Work = Join-Path $env:TEMP 'VoiceInputInstall'
$Destination = Join-Path $env:LOCALAPPDATA 'VoiceInput'
$Archive = Join-Path $Work 'GolosovoyVvod.zip'
$AppDir = Join-Path $Destination 'Voice'

function Info($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "   $text" -ForegroundColor Green }

function Test-DownloadedArchive {
    if (-not (Test-Path $Archive)) { return $false }
    if ((Get-Item $Archive).Length -eq 0) { return $false }
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLower() -eq $ExpectedHash
}

try {
    Info 'Подготовка установки голосового ввода'
    New-Item -ItemType Directory -Force -Path $Work, $Destination | Out-Null

    if (Test-DownloadedArchive) {
        Ok 'Полный архив уже скачан — пропускаю загрузку'
    } else {
        Info 'Скачивание программы и модели Whisper (около 1,5 ГБ)'
        & curl.exe --fail -L -C - --retry 8 --retry-all-errors --connect-timeout 30 --output $Archive $ArchiveUrl
        if ($LASTEXITCODE -ne 0) { throw 'Скачивание прервалось. Запустите ту же команду ещё раз — загрузка продолжится.' }
    }

    if (-not (Test-DownloadedArchive)) {
        Info 'Архив не прошёл проверку — скачиваю заново'
        Remove-Item -LiteralPath $Archive -Force -ErrorAction SilentlyContinue
        & curl.exe --fail -L --retry 8 --retry-all-errors --connect-timeout 30 --output $Archive $ArchiveUrl
        if ($LASTEXITCODE -ne 0 -or -not (Test-DownloadedArchive)) {
            throw 'Не удалось получить целый архив. Проверьте интернет и повторите команду.'
        }
    }
    Ok 'Архив проверен и не повреждён'

    $SettingsBackup = Join-Path $Work 'Голосовой_ввод.ini'
    $ExistingSettings = Join-Path $AppDir 'Голосовой_ввод.ini'
    $HasSettings = Test-Path -LiteralPath $ExistingSettings
    if ($HasSettings) { Copy-Item -LiteralPath $ExistingSettings -Destination $SettingsBackup -Force }

    Info 'Распаковка программы'
    Expand-Archive -LiteralPath $Archive -DestinationPath $Destination -Force
    if ($HasSettings) { Copy-Item -LiteralPath $SettingsBackup -Destination $ExistingSettings -Force }

    $Installer = Join-Path $AppDir 'install.ps1'
    if (-not (Test-Path -LiteralPath $Installer)) { throw 'В архиве не найден основной установщик.' }

    Info 'Установка Python, библиотек, ярлыков и модели'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Installer
    if ($LASTEXITCODE -ne 0) { throw 'Основной установщик завершился с ошибкой.' }

    Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host ''
    Write-Host 'ГОТОВО! Голосовой ввод установлен и запущен.' -ForegroundColor Green
    Write-Host 'Удерживайте F9 и говорите. Отпустите F9 — текст будет вставлен.' -ForegroundColor Green
    Write-Host 'Значок программы находится у часов. Больше ничего настраивать не нужно.' -ForegroundColor Green
} catch {
    Write-Host ''
    Write-Host ('ОШИБКА: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Закройте окно, проверьте интернет и запустите ту же команду ещё раз.' -ForegroundColor Yellow
    Write-Host 'Уже скачанные файлы будут использованы повторно.' -ForegroundColor Yellow
    exit 1
}
