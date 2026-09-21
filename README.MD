# Prometheus and Grafana monitoring for Proxmox VE

This repository runs a Docker Compose monitoring stack for a Proxmox VE cluster. It started as a dashboard and setup guide; after two years of use, the configuration and dashboard were updated to reflect what worked in production.

![Grafana dashboard showing Proxmox guest and storage metrics](images/grafana-dashboard.png)

*An earlier dashboard screenshot. The dashboard JSON in this repository contains the current layout.*

| Component | Purpose |
| --- | --- |
| [prometheus-pve-exporter](https://github.com/prometheus-pve/prometheus-pve-exporter) | Reads cluster, node, guest, and storage metrics from the Proxmox API. This link points to the exporter's **upstream project**, not to a copy of this repository. |
| pve-qga-exporter | Reads filesystem usage inside running QEMU guests through the Proxmox API and QEMU Guest Agent. |
| Prometheus | Scrapes and stores metrics from the exporters. |
| Grafana | Displays the included Proxmox dashboard. |
| node_exporter | Reports metrics for the host running this Compose stack. |

The versions used by this project are pinned in [docker-compose.yaml](docker-compose.yaml). The dashboard JSON is in [dashboards/proxmox-via-prometheus.json](dashboards/proxmox-via-prometheus.json).

## What the dashboard shows

- CPU, RAM, status, and virtual disk capacity for QEMU VMs and LXC containers.
- CPU and RAM usage for Proxmox nodes.
- Usage of local storage per node and shared PBS storage once per storage name.
- Guest CPU, memory, network, and disk I/O history where Proxmox exposes those metrics.
- Filesystem usage inside QEMU guests that have a working QEMU Guest Agent.

**Disk capacity is different from filesystem usage inside a VM.** The standard Proxmox resource metrics report a QEMU virtual disk's configured size and I/O. The included `pve-qga-exporter` additionally calls `get-fsinfo` through QEMU Guest Agent and exports used and total bytes for filesystems inside supported QEMU guests. Proxmox *storage* usage is monitored separately.

## 1. Create a read-only Proxmox API token

1. In the Proxmox UI, open **Datacenter → Permissions → Users** and create a dedicated monitoring user, for example `monitoring@pve`. An existing read-only service account also works.
2. Under **Datacenter → Permissions**, grant that user the `PVEAuditor` role at `/` so the exporter can read cluster-wide data.
3. Create an API token for the user. If the token uses privilege separation, grant the token the same read-only access: its effective permissions are limited by both the token and its user. Copy the token value when it is displayed; Proxmox does not show it again.

Filesystem collection through QEMU Guest Agent requires `VM.Audit` and `VM.Monitor` on `/vms`. A minimal custom role can be created and assigned to both the user and a privilege-separated token:

```sh
pveum role add GuestAgentMonitor --privs "VM.Audit VM.Monitor"
pveum acl modify /vms --user monitoring@pve --role GuestAgentMonitor
pveum acl modify /vms --token 'monitoring@pve!exporter' --role GuestAgentMonitor
```

The QEMU Guest Agent must also be enabled in Proxmox and installed and running inside each guest that should report filesystem usage.

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

`secrets/`, `prometheus/targets.yml`, `pve/pve.yml`, and `.env` are ignored by Git. The example files contain placeholders. Do not commit API tokens, passwords, or exported configurations containing credentials.

## 3. Start and verify the stack

Install Docker Engine with the Compose plugin, then run:

```sh
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose ps
```

On the monitoring host, open `http://localhost:9090/targets`. The `prometheus`, `node`, `pve`, and `pve-qga` jobs should be **UP**. In the Prometheus query page, try `pve_up`, `pve_guest_info`, `pve_storage_info`, and `pve_qga_fs_used_bytes` to confirm that the Proxmox API data is present. Grafana is served on port 3000; complete its initial account setup before exposing it to other users.

## 4. Set up Grafana

1. In **Connections → Data sources**, add **Prometheus** with URL `http://prometheus:9090`. Grafana and Prometheus share the Compose network, so Grafana uses the service name rather than `localhost`.
2. In **Dashboards → New → Import**, upload [dashboards/proxmox-via-prometheus.json](dashboards/proxmox-via-prometheus.json) and select the Prometheus data source.
3. Select the Proxmox API target in the dashboard's `instance` variable and check that guest names, node totals, and storage names match your cluster.

The included dashboard builds on Grafana dashboard [10347, Proxmox via Prometheus](https://grafana.com/grafana/dashboards/10347-proxmox-via-prometheus/) and includes local improvements to guest names, node resource panels, and shared storage display. For host-level metrics from node_exporter, you can also import the independent [Node Exporter Full dashboard, ID 1860](https://grafana.com/grafana/dashboards/1860-node-exporter-full/).

## Repository layout

```text
.
├── README.MD
├── docker-compose.yaml
├── dashboards/proxmox-via-prometheus.json
├── prometheus/
│   ├── prometheus.yml
│   └── targets.example.yml
├── qga-exporter/
│   ├── Dockerfile
│   └── qga_exporter.py
└── pve/pve.example.yml
```

HAProxy configuration, the TLS certificate, and domain settings are not included in this repository.
