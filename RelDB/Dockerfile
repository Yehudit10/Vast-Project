# syntax=docker/dockerfile:1
FROM docker:27-dind

# ---- Versions ----
ARG KUBECTL_VER=v1.30.14
ARG MINIKUBE_VER=v1.36.0
ARG HELM_VER=v3.15.3
ARG CRICTL_VER=v1.30.0

# Stability for curl in secure/slow network
ENV CURL_FLAGS="--cacert /etc/ssl/certs/ca-certificates.crt --retry 5 --retry-delay 2 --insecure"

# ---- OS tools ----
RUN apk add --no-cache \
      bash curl tar gzip ca-certificates iptables ip6tables socat jq postgresql16-client libc6-compat

WORKDIR /work

# ---- External files next to the Dockerfile ----
# Must be in the directory during build
COPY values.yaml     /work/values.yaml
COPY netfree-ca.crt  /tmp/netfree-ca.crt

# ---- Copy init SQL files into the image (order matters) ----
COPY initdb/schema.sql                  /work/initdb/02_schema.sql
COPY initdb/02_event_logs_partition.sql /work/initdb/03_event_logs_partition.sql
COPY initdb/03_partitions.sql           /work/initdb/04_partitions.sql
COPY initdb/loader.sql                  /work/initdb/05_loader.sql
# COPY initdb/04_cron.sql                 /work/initdb/06_cron.sql

# If a NetFree certificate exists — approve it in the system (will also help curl)
RUN if [ -s /tmp/netfree-ca.crt ]; then \
      install -m 0644 /tmp/netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt && \
      update-ca-certificates || true ; \
      ln -sf /etc/ssl/certs/ca-certificates.crt /etc/ssl/cert.pem ; \
    fi

# ---- kubectl ----
RUN curl -fsSL $CURL_FLAGS -o /usr/local/bin/kubectl \
      https://dl.k8s.io/release/${KUBECTL_VER}/bin/linux/amd64/kubectl \
 && chmod +x /usr/local/bin/kubectl

# ---- Helm ----
RUN curl -fsSL $CURL_FLAGS -o /tmp/helm.tgz \
      https://get.helm.sh/helm-${HELM_VER}-linux-amd64.tar.gz \
 && tar -xzf /tmp/helm.tgz -C /tmp \
 && mv /tmp/linux-amd64/helm /usr/local/bin/helm \
 && chmod +x /usr/local/bin/helm \
 && rm -rf /tmp/linux-amd64 /tmp/helm.tgz

# ---- Minikube ----
RUN curl -fsSL $CURL_FLAGS -o /usr/local/bin/minikube \
      https://storage.googleapis.com/minikube/releases/${MINIKUBE_VER}/minikube-linux-amd64 \
 && chmod +x /usr/local/bin/minikube

# ---- crictl ----
RUN curl -fsSL $CURL_FLAGS -o /tmp/crictl.tgz \
      https://github.com/kubernetes-sigs/cri-tools/releases/download/${CRICTL_VER}/crictl-${CRICTL_VER}-linux-amd64.tar.gz \
 && tar -xzf /tmp/crictl.tgz -C /usr/local/bin crictl \
 && rm -f /tmp/crictl.tgz

# ---- ENTRYPOINT that starts dockerd, handles the certificate, and runs the entire flow ----
RUN cat > /work/entrypoint.sh <<'BASH'
#!/usr/bin/env bash
set -euo pipefail

# === Parameters can be overridden at runtime (docker run -e KEY=VAL) ===
: "${K8S_VERSION:=v1.30.14}"
: "${CPU:=2}"
: "${MEM:=2200mb}"
: "${NAMESPACE:=db}"
: "${RELEASE:=pg}"
: "${BITNAMI_IMAGE:=docker.io/bitnami/postgresql:16}"
: "${POSTGRES_ADMIN_PASSWORD:=PgAdmin}"
: "${POSTGRES_PASSWORD:=Pg123}"
: "${VALUES_FILE:=/work/values.yaml}"
: "${NETFREE_CERT_PATH:=/tmp/netfree-ca.crt}"
: "${NETFREE_CERT_DIR_IN_NODE:=/usr/local/share/ca-certificates}"

export DOCKER_HOST=unix:///var/run/docker.sock
export DOCKER_TLS_CERTDIR=

log(){ echo -e "\n===> $*"; }

trust_netfree_in_dind(){
  if [ -s "$NETFREE_CERT_PATH" ]; then
    log "Trust NetFree CA inside this container (dind + dockerd)"
    cp "$NETFREE_CERT_PATH" /usr/local/share/ca-certificates/netfree-self.crt || true
    update-ca-certificates --fresh || true
    ln -sf /etc/ssl/certs/ca-certificates.crt /etc/ssl/cert.pem || true
    for h in registry-1.docker.io docker.io auth.docker.io \
             production.cloudflare.docker.com downloads.registry-1.docker.io; do
      mkdir -p "/etc/docker/certs.d/$h"
      cp "$NETFREE_CERT_PATH" "/etc/docker/certs.d/$h/ca.crt" || true
    done
  else
    log "No NetFree CA provided at $NETFREE_CERT_PATH; skipping dind trust"
  fi
}

start_dockerd(){
  if ! docker info >/dev/null 2>&1; then
    log "Starting Docker daemon (dind) in background..."
    mkdir -p /var/lib/docker
    nohup dockerd --host=unix:///var/run/docker.sock >/tmp/dockerd.log 2>&1 &
    for i in $(seq 1 180); do
      docker info >/dev/null 2>&1 && break
      sleep 1
      if [ "$i" -eq 180 ]; then
        echo "Docker failed to start"; 
        exit 1
      fi
    done
  fi
  log "Docker is up."
}

install_netfree_in_node(){
  if [ -s "$NETFREE_CERT_PATH" ]; then
    log "Install NetFree CA inside minikube node"
    minikube cp "$NETFREE_CERT_PATH" /tmp/netfree-ca.crt || true
    minikube ssh -- "sudo mkdir -p ${NETFREE_CERT_DIR_IN_NODE} && \
      sudo mv /tmp/netfree-ca.crt ${NETFREE_CERT_DIR_IN_NODE}/netfree-ca.crt && \
      sudo chmod 644 ${NETFREE_CERT_DIR_IN_NODE}/netfree-ca.crt && \
      (sudo update-ca-certificates || sudo update-ca-trust || true) && \
      (sudo systemctl restart containerd || sudo service containerd restart || sudo systemctl restart docker || true)"
    log "NetFree CA installed + containerd restarted inside node."
  else
    log "No NetFree CA to install in node."
  fi
}

prepull_or_load(){
  log "(Optional) Try pulling ${BITNAMI_IMAGE} inside node"
  if minikube ssh -- "sudo crictl pull ${BITNAMI_IMAGE} || sudo nerdctl -n k8s.io pull ${BITNAMI_IMAGE}"; then
    log "Image exists in node."
  else
    log "Pull in host docker → minikube image load"
    docker pull "${BITNAMI_IMAGE}"
    minikube image load "${BITNAMI_IMAGE}"
  fi
}

helm_and_ns(){
  log "Add Helm repo + ensure namespace"
  helm repo add bitnami https://charts.bitnami.com/bitnami >/dev/null 2>&1 || echo "Helm repo 'bitnami' already exists, skipping add"
  helm repo update
  kubectl get ns "${NAMESPACE}" >/dev/null 2>&1 || kubectl create namespace "${NAMESPACE}"
}

create_secret(){
  log "Ensure pg-auth secret exists"
  if kubectl -n "${NAMESPACE}" get secret pg-auth >/dev/null 2>&1; then
    echo "Secret pg-auth already exists, skipping creation"
  else
    kubectl -n "${NAMESPACE}" create secret generic pg-auth \
      --from-literal=postgres-password="${POSTGRES_ADMIN_PASSWORD}" \
      --from-literal=password="${POSTGRES_PASSWORD}"
    echo "Secret pg-auth created"
  fi
}

install_pg(){
  log "Install/Upgrade Bitnami PostgreSQL with ${VALUES_FILE}"
  helm -n "${NAMESPACE}" upgrade --install "${RELEASE}" bitnami/postgresql -f "${VALUES_FILE}"
}

wait_ready(){
  log "Wait for PostgreSQL pod Ready"
  if ! kubectl -n "${NAMESPACE}" wait \
    --for=condition=ready pod \
    -l app.kubernetes.io/instance="${RELEASE}",app.kubernetes.io/name=postgresql \
    --timeout=15m; then
    echo "⚠️  PostgreSQL pod did not become Ready within 15 minutes, will keep checking service endpoints..."
  fi

  log "Wait for Service endpoints (${RELEASE}-postgresql)"
  for i in $(seq 1 180); do
    if kubectl -n "${NAMESPACE}" get endpoints "${RELEASE}-postgresql" \
         -o jsonpath='{.subsets[0].addresses[0].ip}' >/dev/null 2>&1; then
      log "✅ Service endpoints are ready"
      return 0
    fi
    sleep 2
  done

  echo "❌ Service endpoints not ready after 180 attempts (~6 minutes)"
  kubectl -n "${NAMESPACE}" get endpoints "${RELEASE}-postgresql" || echo "No endpoints found"
  exit 1
}


ensure_postgis(){
  log "Ensure PostGIS extension exists (with retry)"
  local ADMIN_PW USER_PW
  ADMIN_PW="$(kubectl -n "${NAMESPACE}" get secret pg-auth -o jsonpath='{.data.postgres-password}' | base64 -d)"
  USER_PW="$(kubectl -n "${NAMESPACE}" get secret pg-auth -o jsonpath='{.data.password}' | base64 -d)"

  for i in $(seq 1 120); do
    if kubectl run pg-client --rm -i --restart=Never -n "${NAMESPACE}" \
         --image="${BITNAMI_IMAGE}" \
         --env="PGPASSWORD=${ADMIN_PW}" -- \
         psql -h ${RELEASE}-postgresql -U postgres -d missions_db \
              -c "CREATE EXTENSION IF NOT EXISTS postgis;"; then
      log "PostGIS created/exists"
      break
    fi
    echo "waiting for postgres to accept connections... ($i)"
    sleep 5
    if [ "$i" -eq 120 ]; then
      echo "failed to connect to postgres in time"
      exit 1
    fi
  done

  log "Check PostGIS_Full_Version() as missions_user"
  kubectl run pg-client --rm -i --restart=Never -n "${NAMESPACE}" \
    --image="${BITNAMI_IMAGE}" \
    --env="PGPASSWORD=${USER_PW}" -- \
    psql -h ${RELEASE}-postgresql -U missions_user -d missions_db \
         -c "SELECT PostGIS_Full_Version();"
}

run_sqls_in_order(){
  log "Running local SQL files from /work/initdb (in order)"
  local ADMIN_PW
  ADMIN_PW="$(kubectl -n "${NAMESPACE}" get secret pg-auth -o jsonpath='{.data.postgres-password}' | base64 -d)"

  shopt -s nullglob
  files=(/work/initdb/*.sql)
  if [ ${#files[@]} -eq 0 ]; then
    log "No SQL files found under /work/initdb"
    return 0
  fi

  for f in "${files[@]}"; do
    log "Applying: $(basename "$f")"
    # Pipe the file into psql running inside a short-lived Bitnami client pod
    kubectl run pg-client --rm -i --restart=Never -n "${NAMESPACE}" \
      --image="${BITNAMI_IMAGE}" \
      --env="PGPASSWORD=${ADMIN_PW}" -- \
      psql -v ON_ERROR_STOP=1 \
           -h ${RELEASE}-postgresql -U postgres -d missions_db \
           -f - < "$f"
  done
  log "All SQL files applied."
}

# ==== FLOW ====
trust_netfree_in_dind
start_dockerd

log "Start minikube (K8s ${K8S_VERSION})"
minikube start --force --driver=docker --kubernetes-version="${K8S_VERSION}" --cpus="${CPU}" --memory="${MEM}"

log "Set kubectl context"
kubectl config use-context minikube

install_netfree_in_node
prepull_or_load
helm_and_ns
create_secret
install_pg
wait_ready
ensure_postgis
run_sqls_in_order

log "Done. PostgreSQL + PostGIS are up."

# Keep the container alive to view logs
exec tail -f /dev/null
BASH

RUN sed -i 's/\r$//' /work/entrypoint.sh && chmod +x /work/entrypoint.sh

ENTRYPOINT ["/work/entrypoint.sh"]
