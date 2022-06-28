Tier 1
======

- actually use gathered metrics in decision making

- Tier1 GET should return list of cloudlets without deploying

- Better documentation for cloudlet.yaml local configuration file


Tier 2
======

- figure out how to discover when the kubernetes cluster is actually fully
  deployed and ready to deploy backends.
  Althought the tier2 pod starts pretty quickly, it takes almost 4 minutes
  before all the other pods are done after a reboot. And this is on a cloudlet
  where all containers are fully cached and kernel modules have already been
  built.

- How to handle a multi-node cloudlet, we have to check resource utilization on
  a per node basis and report the best available one(s)?

- Tier2 to Tier1 reporting

    %:
       v  cpu
       v  memory
       v  uplink
       v  downlink
       v  gpu utilization
       o  loadavg

- report USE metrics (usage, saturation, errors)?

- expand reporting to Tier1 to include
    - `location`
    - `accepted_clients`
    - `rejected_clients`
    - `local_networks`?

- clean up connecting to cluster, right now there is an ugly hack to fix --help
  when we don't have cluster credentials.

- merge Tier2/cluster.py with Tier1/cloudlets.py, useful to track common items
  to report like location and client ACLs

- handle prometheus port tunnelling for non-local cloudlets

    Check for the KUBERNETES_SERVICE_HOST and KUBERNETES_SERVICE_PORT
    environment variables and the existence of service account token file at
    /var/run/secrets/kubernetes.io/serviceaccount/token.

  maybe we can leverage the existing Kilo VPN infrastructure?

- report known/supported application uuids to Tier 1?


Tier 3
======

- Improve dependencies.  Should we move this back to click for argument
  parsing, or switch the rest over to typer.

- Split out functionality, merge common code.
