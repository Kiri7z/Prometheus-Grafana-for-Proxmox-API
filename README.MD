# Proxmox VE monitoring with Prometheus and Grafana

Docker Compose stack for Proxmox VE API metrics. It runs Grafana, Prometheus, [prometheus-pve-exporter](https://github.com/prometheus-pve/prometheus-pve-exporter), and node_exporter. Image versions are pinned in `docker-compose.yaml` so an update is deliberate and reproducible.

## What is monitored

- Proxmox nodes, storage, QEMU VMs, and LXC containers through the Proxmox API.
- The Docker host through node_exporter.
- The included [Proxmox dashboard](dashboards/proxmox-via-prometheus.json) is based on dashboard 10347 and includes local improvements. Import it in Grafana and select the Prometheus data source.

**QEMU disk limitation:** `pve_disk_size_bytes` gives the virtual disk size, and `pve_disk_read_bytes` / `pve_disk_write_bytes` give I/O counters. In our cluster `pve_disk_usage_bytes` is zero for every QEMU VM, so it cannot be used as guest filesystem utilization. The dashboard only shows disk usage percentages for LXC guests. To alert on free space *inside* a QEMU guest, collect filesystem metrics from the guest OS (for example, node_exporter on Linux or windows_exporter on Windows) or a verified QEMU Guest Agent integration. Proxmox storage usage is a separate metric.

## One-time setup

1. Create a dedicated Proxmox API user and token with read-only permissions, following the [exporter documentation](https://github.com/prometheus-pve/prometheus-pve-exporter). Do not use a root token.
2. Create local configuration files from the examples:

   ```sh
   mkdir -p secrets
   cp pve/pve.example.yml secrets/pve.yml
   cp prometheus/targets.example.yml prometheus/targets.yml
   chmod 700 secrets
   sudo chgrp 101 secrets/pve.yml
   chmod 640 secrets/pve.yml
   ```

3. Edit `secrets/pve.yml` with the Proxmox API token. Set `verify_ssl: true` when the API certificate is trusted. Edit `prometheus/targets.yml` with **one reachable Proxmox node**; the exporter obtains cluster metrics through its API. Add more targets only when you specifically need them and understand the duplicate series they can produce.

   Exporter 3.9.0 runs as UID/GID 101. The `root:101` and `0640` file permissions let only the exporter group read the bind-mounted token file; keep the `secrets` directory at `0700` on the host. Verify the UID/GID if you change the exporter image.
4. Validate and start the stack:

   ```sh
   docker compose config --quiet
   docker compose pull
   docker compose up -d
   docker compose ps
   ```

5. In Grafana, add Prometheus at `http://prometheus:9090`, then import `dashboards/proxmox-via-prometheus.json` and choose that data source. Check `http://localhost:9090/targets` for the `prometheus`, `node`, and `pve` jobs.

`secrets/`, `prometheus/targets.yml`, and `.env` are ignored by Git. The example files contain placeholders only. Never commit a real `pve.yml`, Telegram bot token, Grafana password, or exported Grafana contact point with credentials.

## Updating an existing deployment

Make a Proxmox backup of the monitoring container/VM first. Export any dashboards and alert rules edited through Grafana before replacing containers. Preserve the local `secrets/pve.yml` and `prometheus/targets.yml` files, then pull the reviewed Git branch on the server. Run `docker compose config --quiet`, `docker compose pull`, and `docker compose up -d`. Afterward verify container versions, Prometheus targets, dashboards, and alert delivery. Avoid `docker compose down -v`: the named volumes hold Grafana and Prometheus data.

The repository does not configure pfSense, HAProxy, or TLS termination.
