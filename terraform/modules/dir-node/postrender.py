import sys
import yaml


def main():
    trust_domain = ""
    peers = []

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--trust-domain" and i + 1 < len(sys.argv):
            trust_domain = sys.argv[i + 1]
            i += 2
        elif arg == "--peer" and i + 1 < len(sys.argv):
            peers.append(sys.argv[i + 1])
            i += 2
        else:
            i += 1

    try:
        input_text = sys.stdin.read()
        docs = [d for d in yaml.safe_load_all(input_text) if d is not None]
    except yaml.YAMLError as exc:
        print(f"ERROR: failed to parse YAML in postrender: {exc}", file=sys.stderr)
        sys.exit(1)

    peers_filtered = [p for p in peers if p and p != trust_domain]

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        if doc.get("kind") != "ClusterSPIFFEID":
            continue

        spec = doc.setdefault("spec", {})
        existing = spec.get("federatesWith") or []

        combined = []
        for td in existing + peers_filtered:
            if td and td != trust_domain and td not in combined:
                combined.append(td)

        if combined:
            spec["federatesWith"] = combined

    yaml.dump_all(docs, sys.stdout, default_flow_style=False, sort_keys=False, explicit_start=True)


if __name__ == "__main__":
    main()
