# AgCloud

## Prometheus Docker Setup

This project includes a custom Dockerfile for running Prometheus in a containerized environment.

### Build the Prometheus Docker Image

```sh
cd prometheus-docker
docker build -t agcloud-prometheus .
```

### Run Prometheus

```sh
docker run -p 9090:9090 --name prometheus agcloud-prometheus
```

Prometheus will start with the configuration from `prometheus-docker/prometheus.yml` and expose the default port 9090.

### Notes

- The Dockerfile installs Prometheus, mounts the config file, and sets up CA certificates.
- You can push the image to your local registry or Docker Hub if needed.