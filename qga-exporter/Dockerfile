FROM prompve/prometheus-pve-exporter:3.9.0

COPY qga_exporter.py /opt/qga-exporter/qga_exporter.py

ENTRYPOINT ["/opt/prometheus-pve-exporter/bin/python", "/opt/qga-exporter/qga_exporter.py"]
