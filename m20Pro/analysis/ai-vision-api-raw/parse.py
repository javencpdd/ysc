import json

base = r"C:/Users/19046/Desktop/特种机器人/M20-pro/.workbuddy/tmp/api_analysis"
spec = json.load(open(base + r"\openapi.json", encoding="utf-8"))
caps = json.load(open(base + r"\capabilities.json", encoding="utf-8"))

print("=== INFO ===")
print(spec["info"]["title"], "|", spec["info"]["version"])
print()
print("=== PATHS (%d) ===" % len(spec["paths"]))
for path, item in spec["paths"].items():
    for method, op in item.items():
        if method not in ("get","post","put","delete","patch"):
            continue
        tags = ",".join(op.get("tags", []))
        print(f"{method.upper():6} {path:55} [{tags}] {op.get('summary','')}")
print()
print("=== TAGS ===")
for t in spec.get("tags", []):
    print(f"- {t['name']}: {t.get('description','')[:120]}")
print()
print("=== CAPABILITIES (count=%s) ===" % caps.get("count"))
groups = {}
for c in caps["items"]:
    g = c["group"]
    groups.setdefault(g, []).append(c)
for g, items in groups.items():
    print(f"\n--- {g} ({len(items)}) ---")
    for c in items:
        stream = "Y" if c.get("stream") else "-"
        snap = "Y" if c.get("snapshot_path") else "-"
        print(f"{c['id']:14} in={c['input']:6} stream={stream} snap={snap} ready={c['model_ready']} | {c['title']}")
        print(f"{'':14} {c['summary'][:90]}")
        print(f"{'':14} task={c['task_path']}")
