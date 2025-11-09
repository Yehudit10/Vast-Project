# run_weekly.ps1
# -------------------------------------------
# Runs the docker-compose service once a week in a clean and stable manner
# -------------------------------------------

# ===== Settings =====
$ProjectDir = "C:\Users\user\Documents\weed-baseline\AgCloud\weed"  # update if needed
$Service    = "weed-detector"
$LogFile    = "C:\logs\weed-weekly.log"
$LockFile   = "C:\temp\weed-weekly.lock"
$WaitForDockerMinutes = 5

# Create folders for log/lock
New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $LockFile) | Out-Null

# Prevent overlap
if (Test-Path $LockFile) { exit 0 }
New-Item -ItemType File -Path $LockFile -Force | Out-Null

# Short logging function with timestamp
function Write-Log($msg) {
  $stamp = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
  "$stamp | $msg" | Tee-Object -FilePath $LogFile -Append
}

try {
  Write-Log "JOB START"

  # Start Docker Desktop if it’s not running
  if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
    $dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerExe) {
      Write-Log "Starting Docker Desktop..."
      Start-Process $dockerExe | Out-Null
    } else {
      Write-Log "Docker Desktop not found at $dockerExe"
    }
  }

  # Wait for Docker engine to start
  $deadline = (Get-Date).AddMinutes($WaitForDockerMinutes)
  do {
    try { docker info | Out-Null; $up=$true } catch { Start-Sleep -Seconds 5 }
  } until ($up -or (Get-Date) -gt $deadline)
  if (-not $up) {
    Write-Log "Docker engine did not become ready within $WaitForDockerMinutes minutes."
    exit 98
  }

  # Correct context (harmless if already correct)
  docker context use desktop-linux 2>$null | Out-Null

  Push-Location $ProjectDir

  # Header for execution
  Write-Log "BEGIN build+run for service '$Service'"

  # Important: do not treat stderr output as a fatal error
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"

  # Build and run: returns the container’s own exit code
  # --no-deps: only this service; --abort-on-container-exit: stops when the service finishes
  "===== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') :: DOCKER START =====" | Tee-Object -FilePath $LogFile -Append
  docker compose up --no-deps --build --abort-on-container-exit --exit-code-from $Service $Service `
    2>&1 | Tee-Object -FilePath $LogFile -Append
  "===== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') :: DOCKER END   =====" | Tee-Object -FilePath $LogFile -Append

  $code = $LASTEXITCODE
  $ErrorActionPreference = $prev

  if ($code -ne 0) {
    Write-Log "JOB FAILED with exit code $code"
    exit $code
  } else {
    Write-Log "JOB SUCCEEDED (exit code 0)"
  }

} finally {
  Pop-Location 2>$null
  Remove-Item $LockFile -ErrorAction SilentlyContinue
  Write-Log "JOB END"
}
