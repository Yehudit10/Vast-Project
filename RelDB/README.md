# PostgreSQL External Database Setup Guide

This guide explains how to **build**, **deploy**, and **connect** to a PostgreSQL database externally (outside the Kubernetes cluster).  
It also includes **test commands** to verify that the database was built correctly.

---

# only to netfree
Before we start you have to download TSL.

---

## 1. Build & Deploy

### Build Docker Image (if custom)
```bash
docker build -t pg-postgis-minikube:latest .
```

### Build Volume
```bash
docker volume create pgdata
```

### Run Dockerfile
```bash
docker run --privileged --cgroupns=host --name pg-mini -v pgdata:/var/lib/postgresql/data -d pg-postgis-minikube:latest
```

### See the logs
```bash
docker logs -f pg-mini
```

Where `values.yaml` should define:
```yaml
primary:
  service:
    type: NodePort
    nodePorts:
      postgresql: 30032
```

---

## 2. Connect from Outside

You have **two options** to connect externally:

---

### 🔹 Option 1: Using NodePort

#### Get Minikube IP
```bash
minikube ip
```
Example: `192.168.49.2`

#### Connect with psql
```bash
psql -h 192.168.49.2 -p 30032 -U missions_user -d missions_db
```

> Password is stored in the Kubernetes secret:
```bash
kubectl -n db get secret pg-auth -o jsonpath="{.data.password}" | base64 -d
```

#### Connect with Python (psycopg2)
```python
import psycopg2

conn = psycopg2.connect(
    host="192.168.49.2",
    port=30032,
    dbname="missions_db",
    user="missions_user",
    password="your_password"
)

cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM regions;")
print(cur.fetchone())
cur.close()
conn.close()
```

---

### 🔹 Option 2: Using Port-Forward (Recommended for local development)

This method creates a **temporary tunnel** from your local machine to the PostgreSQL service inside Kubernetes.  
It works even if the Node IP is not directly reachable.

#### Step 1: Start port-forward
```bash
kubectl -n db port-forward svc/pg-postgresql 5432:5432
```
Keep this terminal window open.  
Now your PostgreSQL service is available at **localhost:5432** on your Windows or Linux host.

#### Step 2: Connect with psql
```bash
psql -h 127.0.0.1 -p 5432 -U missions_user -d missions_db
```

#### Step 3: Connect with Python (psycopg2)
```python
import psycopg2

conn = psycopg2.connect(
    host="127.0.0.1",
    port=5432,
    dbname="missions_db",
    user="missions_user",
    password="your_password"
)

cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM regions;")
print(cur.fetchone())
cur.close()
conn.close()
```

---

## 3. Verification Tests

After deploying, run this to come in psql:

```bash
kubectl -n db run pg-client --rm -it --restart=Never   --image=docker.io/bitnami/postgresql:16   --env="PGPASSWORD=Missions!ChangeMe123" --   psql -h pg-postgresql -p 5432 -U missions_user -d missions_db
```

Run these to confirm DB is working:

### 1. Check tables exist
```sql
\dt
```

### 2. Test query on regions
```sql
SELECT * FROM regions LIMIT 5;
```

### 3. Insert test row
```sql
INSERT INTO missions (id, name) VALUES (999, 'Test Mission');
```

### 4. Verify row exists
```sql
SELECT * FROM missions WHERE id=999;
```

### 5. Cleanup
```sql
DELETE FROM missions WHERE id=999;
```

---

## 4. Troubleshooting

- If you see `Connection refused`: check NodePort mapping with
  ```bash
  kubectl -n db get svc pg-postgresql
  ```

- If password fails: make sure to decode the secret again.

- If schema is empty: ensure your initdb scripts ran correctly.

---

## ✅ Summary

- **Build** with `docker build` (if needed).  
- **Deploy** with `helm upgrade`.  
- **Connect** via either **NodePort** (`minikube ip` + NodePort) or **Port-Forward** (`localhost:5432`).  
- **Verify** using SELECT, INSERT, and DELETE test queries.

---
