Tier 1
======

- actually use gathered metrics in decision making

- Tier1 GET should return list of cloudlets without deploying

- document cloudlet.yaml local configuration file


Tier 2
======

- Tier2 to Tier1 reporting

    %:
       v  cpu
       v  memory
       v  uplink
       v  downlink
       o  loadavg
       o  gpu utilization

- report USE metrics (usage, saturation, errors)?

- expand reporting to Tier1 to include
    - `location`
    - `accepted_clients`
    - `rejected_clients`
    - `local_networks`?

- clean up connecting to cluster, right now there is an ugly hack to fix --help
  when we don't have cluster credentials.

- merge Tier2/cluster.py with Tier1/cloudlets.py (inherit from)
  useful to track common items to report like location and client ACLs

- automatically handle prometheus port tunnelling for non-local cloudlets

    Check for the KUBERNETES_SERVICE_HOST and KUBERNETES_SERVICE_PORT
    environment variables and the existence of service account token file at
    /var/run/secrets/kubernetes.io/serviceaccount/token

  maybe we can leverage the existing Kilo VPN infrastructure?

- check if application uuid actually exists before handing off to helm

- report known/supported application uuids to Tier 1?
