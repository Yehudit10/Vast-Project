# AgCloud-Sounds

## AgCloud – Kafka on KinD

This project demonstrates how to deploy Kafka on KinD using the Bitnami Helm chart, configure topics with 7-day retention, and verify the setup with a smoke test using kcat.

### Prerequisites

- Docker Desktop installed and running

- Internet access for pulling images and charts

- Git (for cloning and versioning)

Files in this repo:

- Dockerfile – container with kubectl, kind, and helm

- values-kafka.yaml – Helm values for Kafka (single broker, auto topic creation disabled)

- create-topics.sh – script that creates topics with 7-day retention

- .gitattributes – ensures LF line endings for scripts

- .dockerignore – ignores irrelevant files during Docker build

### Build and Run

#### 1. Build the image

```bash
cd kafka-kind
docker build -t kafka-kind:local .
```

#### 2. Start KinD + Kafka

Run the container and mount the YAML and topic script. This will:

- Create a KinD cluster

- Deploy Kafka with Helm

- Copy and run create-topics.sh inside the broker pod

- Expose Kafka at localhost:29092

Linux / macOS (bash):

```bash
docker run --privileged --rm -it \
  -v "$PWD/values-kafka.yaml:/work/values-kafka.yaml:ro" \
  -v "$PWD/create-topics.sh:/work/create-topics.sh:ro" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -p 29092:29092 \
  kafka-kind:local
```

Windows (PowerShell):

```powershell
    docker run --privileged --rm -it `
    -v "${PWD}\values-kafka.yaml:/work/values-kafka.yaml:ro" `
    -v "${PWD}\create-topics.sh:/work/create-topics.sh:ro" `
    -v //var/run/docker.sock:/var/run/docker.sock `
    -p 29092:29092 `
    kafka-kind:local
```

At the end you should see:

Kafka reachable at: localhost:29092

### Smoke Test with kcat

#### 1. Create kcat pod

```bash
kubectl --kubeconfig $kc run kcat \
  --restart=Never \
  --image=docker.io/edenhill/kcat:1.7.1 \
  --image-pull-policy=IfNotPresent \
  --command -- /bin/sh -c "while true; do sleep 3600; done"
```

Wait until the pod is ready:

```bash
kubectl --kubeconfig $kc wait pod/kcat --for=condition=Ready --timeout=180s
```

#### 2. Produce a message

```bash
kubectl --kubeconfig $kc exec -it kcat -- sh -lc \
  "echo 'smoke-test' | kcat -P -b kafka.default.svc.cluster.local:9092 -t dev-robot-alerts -v"
```

#### 3. Consume a message

```bash
kubectl --kubeconfig $kc exec -it kcat -- sh -lc \
  "kcat -C -b kafka.default.svc.cluster.local:9092 -t dev-robot-alerts -o -1 -c 1 -q"
```

If you see smoke-test printed back, the setup works.

#### Notes

- Deployment uses 1 controller and 1 broker (no replication).

- Auto topic creation is disabled — topics are explicitly created via create-topics.sh.

- All topics have 7-day retention by default.

- Kafka is exposed at localhost:29092 for producers/consumers outside the cluster.
