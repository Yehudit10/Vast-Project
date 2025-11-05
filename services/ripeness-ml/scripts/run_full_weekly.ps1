# Get date 7 days ago in ISO format
$lastWeek = (Get-Date).AddDays(-7).ToString("yyyy-MM-ddTHH:mm:ss")

# Create request body
$body = @{
    since_ts = $lastWeek
    limit = 1000
} | ConvertTo-Json

# Run prediction on all images from last week
Write-Host "Running predictions for all images from last week..."
Invoke-RestMethod -Method Post -Uri "http://localhost:8088/predict-batch" -Body $body -ContentType "application/json"

# Wait a bit for DB to catch up
Start-Sleep -Seconds 5

# Create weekly rollup
Write-Host "Creating weekly rollup..."
Invoke-RestMethod -Method Post -Uri "http://localhost:8088/rollup/weekly"

Write-Host "Weekly processing complete!"