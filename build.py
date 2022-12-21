# SPDX-FileCopyrightText: 2022 Carnegie Mellon University
# SPDX-License-Identifier: 0BSD

# build/maintenance tasks that are a bit too big for tasks.toml

from pathlib import Path

import jsonpatch
import requests
import yaml


def update_deployment_files(
    kubevirt_release: str = "v0.57.1",
):
    """refresh k3s, kilo and kubevirt related resources"""

    project_root = Path(__file__).resolve().parent
    files_root = project_root / "deploy-tier2" / "files"
    files_root.mkdir(exist_ok=True)

    manifest_patches = [
        # podmonitor_jsonpatch
        # [
        #    {"op": "test", "path": "/kind", "value": "PodMonitor"},
        #    {
        #        "op": "add",
        #        "path": "/metadata/labels/release",
        #        "value": "kube-prometheus-stack",
        #    },
        # ],
        # servicemonitor_jsonpatch
        # [
        #    {"op": "test", "path": "/kind", "value": "ServiceMonitor"},
        #    {
        #        "op": "add",
        #        "path": "/metadata/labels/release",
        #        "value": "kube-prometheus-stack",
        #    },
        # ],
        # wgexporter_jsonpatch
        [
            {"op": "test", "path": "/kind", "value": "DaemonSet"},
            {"op": "test", "path": "/metadata/name", "value": "wg-exporter"},
            {
                "op": "test",
                "path": "/spec/template/spec/containers/0/args/0",
                "value": "-a",
            },
            {"op": "remove", "path": "/spec/template/spec/containers/0/args/0"},
            {
                "op": "add",
                "path": "/spec/template/spec/containers/0/args/0",
                "value": "-a=true",
            },
            {
                "op": "add",
                "path": "/spec/template/spec/hostNetwork",
                "value": True,
            },
        ],
    ]

    kilo_manifests = "https://raw.githubusercontent.com/squat/kilo/main/manifests"

    kubevirt_manifests = (
        f"https://github.com/kubevirt/kubevirt/releases/download/{kubevirt_release}"
    )

    components = [
        ("https://get.k3s.io", "k3s-installer.sh"),
        (f"{kilo_manifests}/crds.yaml", "kilo-crds.yaml"),
        (f"{kilo_manifests}/kilo-k3s.yaml", "kilo-k3s.yaml"),
        (f"{kilo_manifests}/kube-router.yaml", "kilo-kube-router.yaml"),
        # (f"{kilo_manifests}/peer-validation.yaml", "kilo-peer-validation.yaml"),
        (f"{kilo_manifests}/podmonitor.yaml", "kilo-podmonitor.yaml"),
        (f"{kilo_manifests}/wg-exporter.yaml", "kilo-wg-exporter.yaml"),
        (f"{kubevirt_manifests}/kubevirt-operator.yaml", "kubevirt-operator.yaml"),
        (f"{kubevirt_manifests}/kubevirt-cr.yaml", "kubevirt-cr.yaml"),
    ]
    for url, dest in components:
        print("updating", dest)
        r = requests.get(url)
        r.raise_for_status()

        with open(files_root / dest, "wb") as f:
            if dest.endswith(".yaml"):
                result = []
                for manifest in yaml.safe_load_all(r.content):
                    for patch in manifest_patches:
                        try:
                            jsonpatch.apply_patch(manifest, patch, in_place=True)
                        except jsonpatch.JsonPatchTestFailed:
                            continue
                    result.append(yaml.dump(manifest))
                f.write("---\n".join(result).encode("utf-8"))
            else:
                f.write(r.content)
