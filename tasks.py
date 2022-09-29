# SPDX-FileCopyrightText: 2022 Carnegie Mellon University
# SPDX-License-Identifier: 0BSD

# pyinvoke file for maintenance tasks

import re

from invoke import task


@task
def update_dependencies(c):
    """Update python package dependencies"""
    # update project + pre-commit check dependencies
    c.run("poetry update")
    c.run("poetry run pre-commit autoupdate")
    # make sure project still passes pre-commit and unittests
    c.run("poetry run pre-commit run -a")
    c.run("poetry run pytest")
    # commit updates
    c.run("git commit -m 'Update dependencies' poetry.lock .pre-commit-config.yaml")


def get_current_version(c):
    """Get the current application version.
    Helm chart version should always be >= application version.
    """
    r = c.run("poetry run tbump -c .tbump.helm.toml current-version", hide="out")
    return r.stdout.strip()


def bump_current_version(c, part):
    """Simplistic version bumping."""
    current_version = get_current_version(c)
    major, minor, patch = re.match(r"(\d+)\.(\d+)\.(\d+)", current_version).groups()
    if part == "major":
        return f"{int(major)+1}.0.0"
    if part == "minor":
        return f"{major}.{int(minor)+1}.0"
    return f"{major}.{minor}.{int(patch)+1}"


@task
def bump_helm(c, part="patch"):
    """Bump helm chart version"""
    release = bump_current_version(c, part)
    c.run(f"poetry run tbump -c .tbump.helm.toml --no-tag --no-push {release}")
    # c.run(f"git tag -s -m v{release} v{release}")


@task
def build_release(c, part="patch"):
    """Bump application version, build test release and add a signed tag"""
    release = bump_current_version(c, part)
    c.run(f"poetry run tbump -c .tbump.main.toml --no-tag --no-push {release}")
    c.run("poetry build")
    c.run(f"git tag -s -m v{release} v{release}")


@task
def publish(c):
    """Publish application, bump version to dev and push release tags"""
    # c.run("poetry publish")
    new_version = get_current_version(c) + ".post.dev0"
    c.run(f"poetry run tbump -c .tbump.main.toml --no-tag --no-push {new_version}")
    # c.run("git push")
    # c.run("git push --tags")


@task
def update_deployment_files(c):
    """refresh k3s, kilo and kubevirt related resources"""
    from pathlib import Path

    import jsonpatch
    import requests
    import yaml

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

    kubevirt_release = "v0.57.1"
    kubevirt_manifests = \
        f"https://github.com/kubevirt/kubevirt/releases/download/{kubevirt_release}"

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


@task
def build_docker_dev(c):
    """Build and push a Docker image to GHCR (needs authentication)"""
    c.run("docker build -t ghcr.io/cmusatyalab/sinfonia:dev .")
    c.run("docker push ghcr.io/cmusatyalab/sinfonia:dev")


@task
def build_helm_dev(c):
    """Build and publish a Helm chart for development"""
    c.run("helm lint charts/*")
    # c.run("helm package charts/helloworld")
    # c.run("helm package charts/openrtist")
    c.run("helm package charts/sinfonia --version=0.0.0 --app-version=dev")
    # c.run("git checkout gh-pages")
    # c.run("helm repo index . --merge index.yaml")
    # c.run("git add index.yaml *.tgz")
    # c.run("git commit --no-verify -m 'Publish Helm charts'")
    # c.run("git checkout main")
