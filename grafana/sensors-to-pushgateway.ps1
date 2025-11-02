# ===============================================
# Push local sensor JSON metrics to Pushgateway
# ===============================================

# URL of Prometheus Pushgateway
$PushUrl = "http://pushgateway:9091/metrics/job/local_sensors"

# Use relative path inside the repo or container (cross-platform)
# Example: if script is under grafana/, look for ./local_sensors/
$BaseDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$SensorDir = Join-Path $BaseDir "local_sensors"

Write-Host "Monitoring folder: $SensorDir"
Write-Host "Pushing metrics to: $PushUrl"

while ($true) {
    Get-ChildItem -Path $SensorDir -Filter "*.json" | ForEach-Object {
        try {
            $data = Get-Content $_.FullName | ConvertFrom-Json
            $mic = $data.mic_id
            $body = @"
sound_volume_db{mic_id="$mic"} $($data.volume_db)
classifier_rate{mic_id="$mic"} $($data.classifier_rate)
mic_uptime_seconds{mic_id="$mic"} $($data.uptime_sec)
anomaly_count{mic_id="$mic"} $($data.anomaly_count)
"@
            Invoke-RestMethod -Uri "$PushUrl/instance/$mic" -Method Put -Body ($body + "`n") -ContentType "text/plain"
            Write-Host "✅ Pushed metrics for $mic"
        }
        catch {
            Write-Warning "⚠️ Failed for file $($_.Name): $_"
        }
    }

    Start-Sleep -Seconds 5
}
