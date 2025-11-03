$job = "sound_dashboard"
$instance = "mic-001"

$volume = 40
$rate = 0.8
$uptime = 0
$anomalies = 0

while ($true) {
    $volume += Get-Random -Minimum -3 -Maximum 3
    $rate += (Get-Random -Minimum -0.02 -Maximum 0.02)
    $uptime += 5
    if ((Get-Random -Minimum 0 -Maximum 10) -gt 8) { $anomalies++ }

    if ($volume -lt 20) { $volume = 20 }
    elseif ($volume -gt 90) { $volume = 90 }

    if ($rate -lt 0.5) { $rate = 0.5 }
    elseif ($rate -gt 1.0) { $rate = 1.0 }

    $body = @"
sound_volume_db $volume
classifier_rate $rate
mic_uptime_seconds $uptime
app_anomaly_total $anomalies
"@

    Invoke-RestMethod -Uri "http://pushgateway:9091/metrics/job/$job/instance/$instance" `
        -Method Put -Body ($body + "`n") -ContentType "text/plain"

    Write-Host "Pushed: V=$volume, R=$rate, U=$uptime, A=$anomalies"
    Start-Sleep -Seconds 5
}
