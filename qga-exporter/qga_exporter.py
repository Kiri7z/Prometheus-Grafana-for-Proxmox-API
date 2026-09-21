import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml
from prometheus_client import REGISTRY, start_http_server
from prometheus_client.core import GaugeMetricFamily
from proxmoxer import ProxmoxAPI


CONFIG_PATH = os.getenv("PVE_CONFIG", "/etc/prometheus/pve.yml")
TARGETS_PATH = os.getenv("PVE_TARGETS", "/etc/prometheus/targets.yml")
MODULE = os.getenv("PVE_MODULE", "default")
PORT = int(os.getenv("QGA_EXPORTER_PORT", "9222"))
WORKERS = int(os.getenv("QGA_EXPORTER_WORKERS", "4"))
TIMEOUT = int(os.getenv("QGA_EXPORTER_TIMEOUT", "8"))
PSEUDO_FILESYSTEMS = {
    "tmpfs",
    "devtmpfs",
    "squashfs",
    "overlay",
    "sysfs",
    "proc",
    "cdfs",
    "udf",
    "iso9660",
}
PSEUDO_MOUNTPOINTS = {"system reserved", "recovery"}

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger("pve-qga-exporter")


def load_yaml(path):
    with open(path, encoding="utf-8") as source:
        return yaml.safe_load(source)


def load_settings():
    modules = load_yaml(CONFIG_PATH)
    if MODULE not in modules:
        raise ValueError(f"Module {MODULE!r} is not present in {CONFIG_PATH}")

    target = os.getenv("PVE_TARGET")
    if not target:
        target_groups = load_yaml(TARGETS_PATH)
        target = target_groups[0]["targets"][0]

    return target, modules[MODULE]


def make_api(target, module):
    connection = {
        "user": module["user"],
        "verify_ssl": module.get("verify_ssl", True),
        "timeout": TIMEOUT,
    }
    if "token_name" in module and "token_value" in module:
        connection.update(
            token_name=module["token_name"],
            token_value=module["token_value"],
        )
    elif "password" in module:
        connection["password"] = module["password"]
    else:
        raise ValueError("The selected PVE module has no token or password")

    return ProxmoxAPI(target, **connection)


def disk_name(filesystem):
    names = []
    for disk in filesystem.get("disk") or []:
        name = disk.get("dev") or disk.get("serial")
        if not name:
            bus = disk.get("bus-type", "disk")
            target = disk.get("target", "")
            name = f"{bus}{target}"
        names.append(str(name))
    return ",".join(sorted(set(names)))


def fetch_guest(target, module, guest):
    node = guest["node"]
    vmid = str(guest["vmid"])
    name = guest.get("name") or f"VM {vmid}"
    labels = [f"qemu/{vmid}", vmid, name, node]

    try:
        api = make_api(target, module)
        response = api.nodes(node).qemu(vmid).agent("get-fsinfo").get()
        filesystems = response.get("result", []) if isinstance(response, dict) else response
        return labels, filesystems, None
    except Exception as error:  # One unavailable guest must not break the complete scrape.
        return labels, [], error


class QgaFilesystemCollector:
    def __init__(self, target, module):
        self.target = target
        self.module = module
        self.lock = threading.Lock()

    def collect(self):
        with self.lock:
            started = time.monotonic()
            used_metric = GaugeMetricFamily(
                "pve_qga_fs_used_bytes",
                "Filesystem space used inside a QEMU guest reported by QEMU Guest Agent.",
                labels=["filesystem", "id", "vmid", "name", "node", "mountpoint", "fstype", "disk"],
            )
            size_metric = GaugeMetricFamily(
                "pve_qga_fs_size_bytes",
                "Filesystem size inside a QEMU guest reported by QEMU Guest Agent.",
                labels=["filesystem", "id", "vmid", "name", "node", "mountpoint", "fstype", "disk"],
            )
            success_metric = GaugeMetricFamily(
                "pve_qga_fs_scrape_success",
                "Whether filesystem information was collected from a QEMU guest.",
                labels=["id", "vmid", "name", "node"],
            )

            api = make_api(self.target, self.module)
            resources = api.cluster.resources.get(type="vm")
            guests = [
                resource
                for resource in resources
                if resource.get("type") == "qemu" and resource.get("status") == "running"
            ]

            with ThreadPoolExecutor(max_workers=WORKERS) as executor:
                futures = [
                    executor.submit(fetch_guest, self.target, self.module, guest)
                    for guest in guests
                ]
                for future in as_completed(futures):
                    guest_labels, filesystems, error = future.result()
                    success_metric.add_metric(guest_labels, 0 if error else 1)
                    if error:
                        LOGGER.warning(
                            "Guest Agent filesystem query failed for %s (%s): %s",
                            guest_labels[2],
                            guest_labels[0],
                            error,
                        )
                        continue

                    for filesystem in filesystems:
                        if filesystem.get("type", "").lower() in PSEUDO_FILESYSTEMS:
                            continue
                        if filesystem.get("mountpoint", "").lower() in PSEUDO_MOUNTPOINTS:
                            continue
                        used = filesystem.get("used-bytes")
                        size = filesystem.get("total-bytes")
                        if used is None or size is None or size <= 0:
                            continue

                        mountpoint = str(filesystem.get("mountpoint", "unknown"))
                        filesystem_labels = [f"{guest_labels[0]}:{mountpoint}"] + guest_labels + [
                            mountpoint,
                            str(filesystem.get("type", "unknown")),
                            disk_name(filesystem),
                        ]
                        used_metric.add_metric(filesystem_labels, used)
                        size_metric.add_metric(filesystem_labels, size)

            duration_metric = GaugeMetricFamily(
                "pve_qga_collection_duration_seconds",
                "Time spent collecting QEMU Guest Agent filesystem metrics.",
            )
            duration_metric.add_metric([], time.monotonic() - started)

            yield used_metric
            yield size_metric
            yield success_metric
            yield duration_metric


def main():
    target, module = load_settings()
    REGISTRY.register(QgaFilesystemCollector(target, module))
    start_http_server(PORT)
    LOGGER.info("Listening on port %d and querying Proxmox target %s", PORT, target)
    threading.Event().wait()


if __name__ == "__main__":
    main()
