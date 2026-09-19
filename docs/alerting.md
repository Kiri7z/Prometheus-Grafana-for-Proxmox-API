# Alerting plan

The three legacy Grafana rules (`Stopped VM`, `CPU usage`, `Storage usage`) are paused. Their queries used an old, fixed Prometheus `instance` label; do not simply unpause them after deployment. Keep Grafana contact point credentials in Grafana, outside this repository.

## Guest state

Use this instant PromQL query as query A in a Grafana-managed rule:

```promql
pve_up{id=~"qemu/.+|lxc/.+"}
  * on (id, instance) group_left(name, node, type)
    pve_guest_info
```

Each result is one guest with its `id`, `name`, `node`, and `type`. Alert when A is below 1 for 5 minutes. Select the guests expected to run continuously before enabling the rule; Proxmox cannot tell a planned shutdown from a fault. An absent series is different from a value of zero, so monitor the `pve` scrape separately.

In Grafana's summary annotation, use `VM {{ $labels.name }} ({{ $labels.id }}) stopped on {{ $labels.node }}`. Test the query with a deliberately stopped, noncritical guest and check both the firing and resolved message.

## Guest CPU

```promql
100 * pve_cpu_usage_ratio{id=~"qemu/.+|lxc/.+"}
  * on (id, instance) group_left(name, node, type)
    pve_guest_info
```

This reports the percentage of the guest's allocated CPU capacity. As a starting point, alert above 90% for 10 minutes. High CPU is often expected during scheduled work, so tune the threshold and pending time after observing real workloads.

## Storage usage

```promql
(
  100 * pve_disk_usage_bytes{id=~"storage/.+"}
    / pve_disk_size_bytes{id=~"storage/.+"}
    * on (id, instance) group_left(storage, node, plugintype)
      pve_storage_info{plugintype="dir"}
)
or
max by (storage, plugintype) (
  100 * pve_disk_usage_bytes{id=~"storage/.+"}
    / pve_disk_size_bytes{id=~"storage/.+"}
    * on (id, instance) group_left(storage, node, plugintype)
      pve_storage_info{plugintype="pbs"}
)
```

The `dir` series retain `node` and `storage`; the shared PBS storages appear once each. Other storage plugin types need an explicit decision about whether they are local or shared. Start with a warning above 85% for 15 minutes and a critical rule above 95% for 5 minutes. If a storage already exceeds a threshold, expect a real alert when enabling the rule.

## Notification noise

- Route only these intended rules to a dedicated Telegram contact point. Keep the bot token and chat ID out of Git.
- Group by alert rule; a group can contain several guests or storages. Set the repeat interval to a useful reminder cadence, such as 24 hours, rather than the default 4 hours.
- Use a pending period so brief restarts and load spikes do not page. Configure scrape failure as its own rule instead of treating missing guest data as a stopped guest.
- Confirm which guests are expected to run, maintenance schedules, thresholds, and the Telegram destination before turning on notifications.

All three PromQL expressions were evaluated against the upgraded stack on 2026-09-19. They returned 17 guest state series, 17 guest CPU series, and 8 deduplicated storage series at that time.
