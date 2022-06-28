# Sinfonia

Manages discovery of nearby cloudlets and deployment of backends for
edge-native applications.

Tier 1 is located in the cloud, Tier 2 is at various cloudlets where backends
could be deployed and Tier 3 is the mobile client application.

Tier 1 collects recent metrics from Tier 2 cloudlets and uses these in
combination with Tier 3 application / backend specific requirements to
pick one or more Tier 2 candidates for deployment.


## Deployment States

- Initializing
    - create kilo peer and deployment namespace
    - label namespace with application uuid + client pubkey
    - start application with helm
    - transition to Deployed

- Deployed
    - deployment requests bump expiration time
    - job runner is responsible for transition to Expiring
        - delete kilo peer
        - stop application with helm

- Expiring
    - deployment request transitions back to Deployed
        - (re)create kilo peer
        - (re)start application with helm
    - job runner will transition to Expired
        - delete application, deployment namespace

- Expired
    - reclaimed all state and resources
    - new deployment requests transition to Initializing

## Development workflows

### Tier 1

When developing/debugging Tier1 interactions it is often simplest to create a
local `cloudlets.yaml` config file that contains static data for one or more
Tier2 instances and then start a local tier1 instance with
`poetry run sinfonia-tier1 -c cloudlets.yaml`.

```yaml
name: Orchestrator@CMU
endpoint: http://cloudlet.elijah.cs.cmu.edu/api/v1/deploy
local_networks:
  - 128.2.0.0/16
  - 128.237.0.0/16
location: [40.4439, -79.9444]
accepted_clients:
  - 0.0.0.0/0
resources:
  cpu_ratio: 0.1
  mem_ratio: 0.5
  gpu_ratio: 0.0
  net_tx_rate: 11000
  net_rx_rate: 1000
---
name: Orchestrator@Home
endpoint: http://localhost:5000/api/v1/deploy
location: [40.4465, -79.9032]
local_networks:
  - 192.168.0.0/16
accepted_clients:
  - 192.168.0.0/16
```

## Versioning

There are two different versions in play,
- the main application version is used to tag releases and docker containers
- the Helm chart version.

The Helm chart `version` uses strict semver and should always be equal or
larger than the main application version. It is bumped whenever the Helm chart
changes, which includes anytime a new release is made.

The main application version uses semantic versioning for all releases. After
publishing the application version becomes `current_version.post.dev0`. However
the `appVersion` in the Helm chart remains at the last tagged release so keep
in mind that any development changes to the Helm chart will be using the last
released application Docker container and not the version of the source code
that is currently under development.
