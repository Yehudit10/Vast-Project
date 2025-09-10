import os, subprocess, time, pathlib, sys, pytest

@pytest.mark.integration
def test_docker_end_to_end():
    if not os.environ.get("RUN_DOCKER_IT"):
        pytest.skip("Set RUN_DOCKER_IT=1 to run docker-compose integration test")

    def run(cmd):
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        assert res.returncode == 0, f"Command failed:\n{cmd}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        return res.stdout.strip()

    # Clean & start core services
    run("docker compose down -v || true")
    run("rm -f out/latency.csv || true")
    run("docker compose up -d --build mosquitto minio mc mqtt_ingest")

    # Give services a moment to come up
    time.sleep(5)

    # Run publisher (blocks until done)
    run("docker compose up --build mqtt_publisher")

    # Count S3 objects via mc
    out = run("""\
docker exec -i mqtt-mc-1 sh -c '
  mc alias set local http://minio:9000 minioadmin minioadmin >/dev/null 2>&1
  mc ls --recursive --json local/images | wc -l
'""" )
    s3_count = int(out.strip() or "0")

    # Count CSV rows (minus header)
    csv_path = pathlib.Path("out/latency.csv")
    csv_rows = 0
    if csv_path.exists():
        with csv_path.open() as f:
            csv_rows = max(0, sum(1 for _ in f) - 1)

    assert s3_count > 0, "No objects found in MinIO bucket"
    assert s3_count == csv_rows, f"S3 objects ({s3_count}) != CSV rows ({csv_rows})"
