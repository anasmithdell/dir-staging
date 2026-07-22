import sys
import yaml


def _str_representer(dumper, data):
    """Use literal block style for multi-line strings."""
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(str, _str_representer)


def parse_args():
    args = {
        "trust_domain": "",
        "base_fqdn": "",
        "namespace": "dir",
        "peers": [],
    }
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--trust-domain" and i + 1 < len(sys.argv):
            args["trust_domain"] = sys.argv[i + 1]
            i += 2
        elif arg == "--base-fqdn" and i + 1 < len(sys.argv):
            args["base_fqdn"] = sys.argv[i + 1]
            i += 2
        elif arg == "--namespace" and i + 1 < len(sys.argv):
            args["namespace"] = sys.argv[i + 1]
            i += 2
        elif arg == "--peer" and i + 1 < len(sys.argv):
            args["peers"].append(sys.argv[i + 1])
            i += 2
        else:
            i += 1
    return args


def patch_cluster_spiffeid(doc, trust_domain, peers):
    if doc.get("kind") != "ClusterSPIFFEID":
        return

    spec = doc.setdefault("spec", {})
    existing = spec.get("federatesWith") or []

    peers_filtered = [p for p in peers if p and p != trust_domain]

    combined = []
    for td in existing + peers_filtered:
        if td and td != trust_domain and td not in combined:
            combined.append(td)

    if combined:
        spec["federatesWith"] = combined


def patch_dir_configmap(doc, base_fqdn, namespace):
    if doc.get("kind") != "ConfigMap":
        return

    data = doc.get("data") or {}
    if "server.config.yml" not in data or "reconciler.config.yml" not in data:
        return

    # Apiserver config: advertise the external Zot registry to remote peers.
    server_cfg = yaml.safe_load(data["server.config.yml"]) or {}
    store = server_cfg.setdefault("store", {})
    if store.get("provider") == "oci":
        oci = store.setdefault("oci", {})
        oci["registry_address"] = f"zot.{base_fqdn}:443"
        oci["repository_name"] = oci.get("repository_name") or "dir"
        auth = oci.setdefault("auth_config", {})
        auth["insecure"] = "false"
        auth.setdefault("username", "admin")
        auth.setdefault("password", "admin")

    sync = server_cfg.setdefault("sync", {})
    sync_auth = sync.setdefault("auth_config", {})
    sync_auth.setdefault("username", "admin")
    sync_auth.setdefault("password", "admin")

    data["server.config.yml"] = yaml.safe_dump(
        server_cfg, default_flow_style=False, sort_keys=False
    )

    # Reconciler config: write to the in-cluster Zot service.
    reconciler_cfg = yaml.safe_load(data["reconciler.config.yml"]) or {}
    local = reconciler_cfg.setdefault("local_registry", {})
    local["registry_address"] = f"dir-zot.{namespace}.svc.cluster.local:5000"
    local["repository_name"] = local.get("repository_name") or "dir"
    auth = local.setdefault("auth_config", {})
    auth["insecure"] = "true"
    auth.setdefault("username", "admin")
    auth.setdefault("password", "admin")

    data["reconciler.config.yml"] = yaml.safe_dump(
        reconciler_cfg, default_flow_style=False, sort_keys=False
    )


def main():
    args = parse_args()

    try:
        input_text = sys.stdin.read()
        docs = [d for d in yaml.safe_load_all(input_text) if d is not None]
    except yaml.YAMLError as exc:
        print(f"ERROR: failed to parse YAML in postrender: {exc}", file=sys.stderr)
        sys.exit(1)

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        patch_cluster_spiffeid(doc, args["trust_domain"], args["peers"])
        patch_dir_configmap(doc, args["base_fqdn"], args["namespace"])

    yaml.dump_all(docs, sys.stdout, default_flow_style=False, sort_keys=False, explicit_start=True)


if __name__ == "__main__":
    main()
