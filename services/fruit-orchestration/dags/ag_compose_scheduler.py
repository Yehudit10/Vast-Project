# dags/run_external_composes.py

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, get_current_context
from airflow.models import Variable
from datetime import datetime
import pendulum

# Use Israel local timezone for correct weekday calculation
TZ = pendulum.timezone("Asia/Jerusalem")

default_args = {"owner": "airflow"}

with DAG(
    dag_id="run_external_composes",
    start_date=datetime(2024, 1, 1, tzinfo=TZ),
    schedule="@daily",
    catchup=False,
    default_args=default_args,
) as dag:

    # ---------- Helpers to run docker compose (down / up-detached / curl / batch) ----------

    def compose_down_task(task_id, service_dir, project, compose_file="docker-compose.yml"):
        # Runs "docker compose down" via docker/compose image; also removes default network if left over
        cmd = f"""
        set -euo pipefail
        cd {service_dir}
        COMPOSE_IMAGE="docker/compose:latest"

        docker run --rm \
          -v /var/run/docker.sock:/var/run/docker.sock \
          --volumes-from "$HOSTNAME" \
          -w "{service_dir}" \
          $COMPOSE_IMAGE \
          -f {compose_file} -p {project} down -v --remove-orphans || true

        docker network rm {project}_default || true
        """
        return BashOperator(task_id=task_id, bash_command=cmd)

    def compose_up_detached_task(task_id, service_dir, project, env_file=None, compose_file="docker-compose.yml"):
        # Brings services up in detached mode after cleaning previous resources
        env_part = f"--env-file {env_file}" if env_file else ""
        cmd = f"""
        set -euo pipefail
        cd {service_dir}
        export DOCKER_BUILDKIT=1
        COMPOSE_IMAGE="docker/compose:latest"

        docker run --rm -v /var/run/docker.sock:/var/run/docker.sock --volumes-from "$HOSTNAME" -w "{service_dir}" $COMPOSE_IMAGE -f {compose_file} -p {project} down -v --remove-orphans || true
        docker network rm {project}_default || true

        docker run --rm \
          -v /var/run/docker.sock:/var/run/docker.sock \
          --volumes-from "$HOSTNAME" \
          -w "{service_dir}" \
          $COMPOSE_IMAGE \
          -f {compose_file} -p {project} {env_part} up -d --build
        """
        return BashOperator(task_id=task_id, bash_command=cmd)

    def compose_run_batch_task(task_id, service_dir, project, service_name, env_file=None, compose_file="docker-compose.yml"):
        # Runs a single service as a batch job; waits for completion and propagates its exit code
        env_part = f"--env-file {env_file}" if env_file else ""
        cmd = f"""
        set -euo pipefail
        cd {service_dir}
        export DOCKER_BUILDKIT=1
        COMPOSE_IMAGE="docker/compose:latest"

        # Clean before run
        docker run --rm -v /var/run/docker.sock:/var/run/docker.sock --volumes-from "$HOSTNAME" -w "{service_dir}" $COMPOSE_IMAGE -f {compose_file} -p {project} down -v --remove-orphans || true
        docker network rm {project}_default || true

        # Run batch (non-detached) and return the service exit code to Airflow
        docker run --rm \
          -v /var/run/docker.sock:/var/run/docker.sock \
          --volumes-from "$HOSTNAME" \
          -w "{service_dir}" \
          $COMPOSE_IMAGE \
          -f {compose_file} -p {project} {env_part} up --build --abort-on-container-exit --exit-code-from {service_name}
        rc=$?

        # Cleanup after batch
        docker run --rm -v /var/run/docker.sock:/var/run/docker.sock --volumes-from "$HOSTNAME" -w "{service_dir}" $COMPOSE_IMAGE -f {compose_file} -p {project} down -v --remove-orphans
        exit $rc
        """
        return BashOperator(task_id=task_id, bash_command=cmd)

    def curl_inside_network_task(task_id, url, docker_network):
        # Waits for a known HTTP endpoint inside a Docker network, then performs the POST
        cmd = f"""
        set -euo pipefail

        # Wait for service health check (max ~120 seconds)
        for i in $(seq 1 60); do
          if docker run --rm --network {docker_network} curlimages/curl:8.10.1 -fsS http://ripeness-api:8088/healthz >/dev/null; then
            echo "ripeness-api is healthy"
            break
          fi
          echo "waiting for ripeness-api..."
          sleep 2
        done

        # Actual POST request
        docker run --rm --network {docker_network} curlimages/curl:8.10.1 \
          --retry 5 --retry-delay 2 --fail-with-body \
          -X POST {url}
        echo
        """
        return BashOperator(task_id=task_id, bash_command=cmd)

    # ---------- Daily classifier job (runs normally every day) ----------
    run_classifier = BashOperator(
        task_id="run_classifier_compose",
        bash_command="""
        set -euo pipefail
        cd /opt/services/classifier
        export DOCKER_BUILDKIT=1
        COMPOSE_IMAGE="docker/compose:latest"

        docker run --rm -v /var/run/docker.sock:/var/run/docker.sock --volumes-from "$HOSTNAME" -w "/opt/services/classifier" $COMPOSE_IMAGE -f docker-compose.yml -p classifier_job down -v --remove-orphans || true
        docker network rm classifier_job_default || true

        # Run batch (not detached, wait for completion)
        docker run --rm -v /var/run/docker.sock:/var/run/docker.sock --volumes-from "$HOSTNAME" -w "/opt/services/classifier" $COMPOSE_IMAGE -f docker-compose.yml -p classifier_job --env-file .env up --build --abort-on-container-exit --exit-code-from batch
        rc=$?

        # Cleanup after batch
        docker run --rm -v /var/run/docker.sock:/var/run/docker.sock --volumes-from "$HOSTNAME" -w "/opt/services/classifier" $COMPOSE_IMAGE -f docker-compose.yml -p classifier_job down -v --remove-orphans
        exit $rc
        """
    )

    # ---------- Weekly branch: only continue on specific weekday ----------
    def should_post():
        """Run the weekly chain only on the selected weekday; otherwise skip."""
        ctx = get_current_context()
        now_local = ctx["logical_date"].in_timezone(TZ)

        # Variable allows custom weekday (1=Mon .. 7=Sun), default=2 (Tuesday)
        target_dow = int(Variable.get("ripeness_weekly_dow", default_var="2"))
        print(f"[weekly_gate] logical_date={now_local}, isoweekday={now_local.isoweekday()}, target={target_dow}")
        return "ripeness_up" if now_local.isoweekday() == target_dow else "skip_weekly"

    weekly_gate = BranchPythonOperator(
        task_id="weekly_gate",
        python_callable=should_post,
    )

    skip_weekly = EmptyOperator(task_id="skip_weekly")

    # ---------- Ripeness chain (runs only on the weekly day) ----------
    ripeness_up = compose_up_detached_task(
        task_id="ripeness_up",
        service_dir="/opt/services/ripeness",
        project="ripeness_job",
        env_file=".env",
        compose_file="docker-compose.yml"
    )

    ripeness_call = curl_inside_network_task(
        task_id="ripeness_call_predict_last_week",
        url="http://ripeness-api:8088/predict-last-week",
        docker_network="ag_cloud"  # Must match the external Docker network name
    )

    ripeness_down = compose_down_task(
        task_id="ripeness_down",
        service_dir="/opt/services/ripeness",
        project="ripeness_job",
        compose_file="docker-compose.yml"
    )

    # ---------- Fruit ripeness alert (weekly batch run, runs AFTER ripeness chain) ----------
    alerts_run = compose_run_batch_task(
        task_id="alerts_run",
        service_dir="/opt/services/fruit_ripeness_alert",
        project="fruit_ripeness_alert_job",
        service_name="fruit_ripeness_alert",       # Service name from the compose file
        env_file=None,                              # Set ".env" if you store secrets there
        compose_file="docker-compose.yml"
    )

    # ---------- Dependencies ----------
    run_classifier >> weekly_gate
    weekly_gate >> ripeness_up >> ripeness_call >> ripeness_down >> alerts_run
    weekly_gate >> skip_weekly
