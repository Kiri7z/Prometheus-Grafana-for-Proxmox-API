# Prometheus and Grafana monitoring for Proxmox VE

This repository runs a Docker Compose monitoring stack for a Proxmox VE cluster. It started as a dashboard and setup guide; after two years of use, the configuration and dashboard were updated to reflect what worked in production.

| Component | Purpose |
| --- | --- |
| [prometheus-pve-exporter](https://github.com/prometheus-pve/prometheus-pve-exporter) | Reads cluster, node, guest, and storage metrics from the Proxmox API. This link points to the exporter's **upstream project**, not to a copy of this repository. |
| Prometheus | Scrapes and stores metrics from the exporters. |
| Grafana | Displays the included Proxmox dashboard and manages alerts. |
| node_exporter | Reports metrics for the host running this Compose stack. |

The versions used by this project are pinned in [docker-compose.yaml](docker-compose.yaml). The dashboard JSON is in [dashboards/proxmox-via-prometheus.json](dashboards/proxmox-via-prometheus.json).

## What the dashboard shows

- CPU, RAM, status, and virtual disk capacity for QEMU VMs and LXC containers.
- CPU and RAM usage for Proxmox nodes.
- Usage of local storage per node and shared PBS storage once per storage name.
- Guest CPU, memory, network, and disk I/O history where Proxmox exposes those metrics.

**Disk capacity is different from free space inside a VM.** The Proxmox API reports a QEMU virtual disk's configured size and I/O, but it does not reliably report used filesystem space inside that guest. The dashboard shows guest filesystem usage for LXC containers only. For a QEMU guest, install an exporter inside the operating system, such as node_exporter for Linux or windows_exporter for Windows, if you need a free-space alert. Proxmox *storage* usage is monitored separately.

## 1. Create a read-only Proxmox API token

1. In the Proxmox UI, open **Datacenter → Permissions → Users** and create a dedicated monitoring user, for example `monitoring@pve`. An existing read-only service account also works.
2. Under **Datacenter → Permissions**, grant that user the `PVEAuditor` role at `/` so the exporter can read cluster-wide data.
3. Create an API token for the user. If the token uses privilege separation, grant the token the same read-only access: its effective permissions are limited by both the token and its user. Copy the token value when it is displayed; Proxmox does not show it again.

Use a token for monitoring rather than an administrator password. See the [Proxmox user-management guide](https://pve.proxmox.com/pve-docs/pve-admin-guide.pdf) and the [exporter's setup instructions](https://github.com/prometheus-pve/prometheus-pve-exporter#proxmox-ve-configuration) for permission details.

## 2. Create local configuration files

From the repository root:

```sh
mkdir -p secrets
cp pve/pve.example.yml secrets/pve.yml
cp prometheus/targets.example.yml prometheus/targets.yml
chmod 700 secrets
sudo chgrp 101 secrets/pve.yml
chmod 640 secrets/pve.yml
```

Edit `secrets/pve.yml` with the monitoring user, token name, and token value:

```yaml
default:
  user: monitoring@pve
  token_name: exporter
  token_value: REPLACE_WITH_YOUR_TOKEN
  verify_ssl: true
```

The exporter image currently runs as UID/GID 101, so group 101 needs read access to the mounted token file. Check this again if you change the exporter image. Keep TLS verification enabled when the Proxmox API certificate is trusted by the exporter; `verify_ssl: false` is an explicit workaround for an untrusted certificate.

In `prometheus/targets.yml`, put one reachable Proxmox node's hostname or IP address:

```yaml
- targets:
    - node1.example.com
```

The exporter can obtain cluster data through that node's API. Scraping every node with the same cluster token may create duplicate series. The hostname should resolve **from the exporter container**, not just from your browser.

`secrets/`, `prometheus/targets.yml`, `pve/pve.yml`, and `.env` are ignored by Git. The example files contain placeholders. Do not commit an API token, Grafana password, Telegram bot token, chat ID, or a Grafana export that contains credentials.

## 3. Start and verify the stack

Install Docker Engine with the Compose plugin, then run:

```sh
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose ps
```

On the monitoring host, open `http://localhost:9090/targets`. The `prometheus`, `node`, and `pve` jobs should be **UP**. In the Prometheus query page, try `pve_up`, `pve_guest_info`, and `pve_storage_info` to confirm that the Proxmox API data is present. Grafana is served on port 3000; complete its initial account setup before exposing it to other users.

## 4. Set up Grafana

1. In **Connections → Data sources**, add **Prometheus** with URL `http://prometheus:9090`. Grafana and Prometheus share the Compose network, so Grafana uses the service name rather than `localhost`.
2. In **Dashboards → New → Import**, upload [dashboards/proxmox-via-prometheus.json](dashboards/proxmox-via-prometheus.json) and select the Prometheus data source.
3. Select the Proxmox API target in the dashboard's `instance` variable and check that guest names, node totals, and storage names match your cluster.

The included dashboard builds on Grafana dashboard [10347, Proxmox via Prometheus](https://grafana.com/grafana/dashboards/10347-proxmox-via-prometheus/) and includes local improvements to guest names, node resource panels, and shared storage display. For host-level metrics from node_exporter, you can also import the independent [Node Exporter Full dashboard, ID 1860](https://grafana.com/grafana/dashboards/1860-node-exporter-full/).

## 5. Configure alerts

Grafana stores alert rules and Telegram contact-point credentials in its own data volume; they are not part of this public repository. [docs/alerting.md](docs/alerting.md) contains reusable PromQL queries and explains the choices behind these rules:

| Alert | Example condition |
| --- | --- |
| Expected-to-run guest stopped | Guest status below 1 for 5 minutes; explicitly select which guests must always run. |
| Guest or Proxmox node CPU | Above 80% for 5 minutes. |
| Proxmox storage usage | Above 90% for 5 minutes; shared PBS storage should create one alert, not one per node. |

Create a Telegram contact point in Grafana, enter the bot token and chat ID there, and send a test notification. Use `name`, `id`, `node`, and `storage` labels in the notification template so messages identify the affected object. Keep the bot token outside Git.

## Updating an existing installation

Back up the monitoring VM or container first. Export dashboards and alert rules that you edited through Grafana. Pull the reviewed `main` branch on the server, keep the local `secrets/pve.yml` and `prometheus/targets.yml`, then run `docker compose config --quiet`, `docker compose pull`, and `docker compose up -d`. Confirm the targets, dashboard, and Telegram delivery afterward.

Avoid `docker compose down -v` during an update: the named volumes hold Prometheus and Grafana data.

## Repository layout

```text
.
├── README.MD
├── docker-compose.yaml
├── dashboards/proxmox-via-prometheus.json
├── docs/alerting.md
├── prometheus/
│   ├── prometheus.yml
│   └── targets.example.yml
└── pve/pve.example.yml
```

HAProxy configuration, the TLS certificate, and domain settings are not included in this repository.
