# --- Auto send MinIO messages to match metadata ---
param (
    [int]$Count = 10  # how many latest metadata messages to match
)

Write-Host "`n[INFO] Fetching last $Count metadata messages from Kafka..." -ForegroundColor Cyan

# 1️⃣ Get last metadata messages (inside the Kafka container)
$cmd = "/opt/bitnami/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka:9092 --topic dev-aerial-images-keys --from-beginning --timeout-ms 5000 2>/dev/null"
$metaMessages = docker exec kafka bash -c $cmd |
    Select-String -Pattern '"file_name"' |
    ForEach-Object { ($_ -split '\"file_name\"\s*:\s*\"')[1] -split '\"' | Select-Object -First 1 } |
    Where-Object { $_ -match '^drone-01_' } |
    Select-Object -Last $Count

if (-not $metaMessages) {
    Write-Host "[WARN] No metadata messages found." -ForegroundColor Yellow
    exit
}

Write-Host "`n[INFO] Found $($metaMessages.Count) image names:" -ForegroundColor Green
$metaMessages | ForEach-Object { Write-Host " - $_" }

# 2️⃣ Build MinIO JSON messages for each file_name
$today = (Get-Date).ToString('yyyy-MM-dd')
$minioMessages = $metaMessages | ForEach-Object {
    $keyName = $_
    return '{"EventName":"s3:ObjectCreated:Put","Key":"imagery/air/' + $today + '/123/' + $keyName + '"}'
}

Write-Host "`n[INFO] Sending MinIO messages to Kafka topic 'image.new.aerial'..." -ForegroundColor Cyan

# 3️⃣ Send them to Kafka (inside container)
$producerCmd = "/opt/bitnami/kafka/bin/kafka-console-producer.sh --bootstrap-server kafka:9092 --topic image.new.aerial"
$minioMessages | docker exec -i kafka bash -c $producerCmd

Write-Host "`n[DONE] Sent $($minioMessages.Count) messages successfully.`n" -ForegroundColor Green
