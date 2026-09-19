# Alerting

Keep Grafana contact point credentials and any environment-specific guest allowlist outside this public repository. Review existing rules and queries before enabling notifications after deployment.

## Guest state

Use this instant PromQL query as query A in a Grafana-managed rule:

```promql
pve_up{id=~"qemu/.+|lxc/.+"}
  * on (id, instance) group_left(name, node, type)
    pve_guest_info
```

Each result is one guest with its `id`, `name`, `node`, and `type`. Replace the broad `id` regex above with an explicit allowlist of guests expected to run continuously. Add new guests deliberately; they will not be monitored automatically. Proxmox cannot tell a planned shutdown from a fault. An absent series is different from a value of zero.

In Grafana's summary annotation, use `VM {{ $labels.name }} ({{ $labels.id }}) stopped on {{ $labels.node }}`. Test both the firing and resolved message with a deliberately stopped, noncritical guest.

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

- Route only intended rules to the Telegram contact point. Keep the bot token and chat ID out of Git.
- Group by alert rule; a group can contain several guests. Choose a repeat interval that avoids noisy reminders.
- Use a pending period so brief restarts and load spikes do not page. Configure scrape failure as its own rule instead of treating missing guest data as a stopped guest.
- Review the guest allowlist whenever guests are added, retired, or scheduled to shut down.

Validate each PromQL expression against your own cluster before enabling its alert rule.
