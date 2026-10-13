import json

base = r"C:/Users/19046/Desktop/特种机器人/M20-pro/.workbuddy/tmp/api_analysis"
spec = json.load(open(base + r"\openapi.json", encoding="utf-8"))

def show(path, method):
    op = spec["paths"][path][method]
    print(f"### {method.upper()} {path} — {op.get('summary','')}")
    for p in op.get("parameters", []):
        s = p.get("schema", {})
        print(f"  - {p['name']} ({p['in']}{', required' if p.get('required') else ''}): {s.get('type','?')} enum={s.get('enum')} default={s.get('default')} | {p.get('description','')[:100]}")
    rb = op.get("requestBody")
    if rb:
        for ct, media in rb.get("content", {}).items():
            sch = media.get("schema", {})
            if "$ref" in sch:
                name = sch["$ref"].split("/")[-1]
                props = spec["components"]["schemas"][name]["properties"]
                req = spec["components"]["schemas"][name].get("required", [])
                print(f"  body({ct}) -> {name} required={req}")
                for k, v in props.items():
                    d = v.get("description", "")
                    print(f"    - {k}: enum={v.get('enum')} default={v.get('default')} | {d[:80]}")
            else:
                print(f"  body({ct}) -> {sch.get('type')} {list(sch.get('properties',{}).keys())}")
    print()

show("/api/v1/stream/ai-04-yolov8-object-detection", "get")
show("/api/v1/stream/ai-04-yolov8-object-detection/snapshot", "get")
show("/api/v1/stream/ai-04-yolov8-object-detection/push", "post")
show("/api/v1/tasks/ai-04-yolov8-object-detection", "post")
show("/api/v1/tasks/opencv-11-motion-detection", "post")
show("/api/v1/camera/probe", "get")
show("/api/v1/streams", "delete")
show("/api/v1/camera/sources", "get")
