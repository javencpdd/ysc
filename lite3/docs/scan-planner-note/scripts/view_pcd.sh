#!/usr/bin/env bash
# ============================================================
# 点云查看（不依赖 GUI，headless 可用）
#
#   bash scripts/view_pcd.sh top          # 终端里直接画 ASCII 俯视图（最快，不用传文件）
#   bash scripts/view_pcd.sh ds           # 降采样 -> map/lite3_view.pcd（纯 xyz，小文件）
#   bash scripts/view_pcd.sh pub          # 发布到 /cloud_pcd，用 Foxglove 看 3D
#   bash scripts/view_pcd.sh info         # 点数 / 每点字节 / 坐标范围（正确解析版）
#
# 环境变量：
#   CROP="zmin,zmax"                       # 只保留该高度范围的点（切掉漂移脏点）
#   CROP="xmin,xmax,ymin,ymax,zmin,zmax"   # 完整包围盒裁剪
#   OUT=/path/to.pcd                       # 降采样输出路径（默认 map/lite3_view.pcd）
# 例：CROP="-0.5,3.0" bash scripts/view_pcd.sh ds
#
# 注意：本机 PCD 每点 32 字节（FIELDS 有 8 个：x y z intensity + 4 个法向量字段），
#       只按 16 字节采样会把法向量当成坐标，范围统计会失真。
#       np.fromfile 的 offset 是【相对当前位置】的，读完头部后再传 offset 会整体
#       错位一个头部长度（255 B），表现为俯视图退化成一条线 / 3D 里全是散点。
# ============================================================

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="$(dirname "$HERE")"
MAP="${MAP:-$WS/map/lite3.pcd}"
ACTION="${1:-top}"
TARGET="${2:-1500000}"

run_py() {
  python3 - "$MAP" "$TARGET" "$1" <<'PY'
import sys, os, struct
import numpy as np

path, target = sys.argv[1], int(sys.argv[2])

f = open(path, "rb")
hdr = []
while True:
    line = f.readline().decode("ascii", "ignore").strip()
    hdr.append(line)
    if line.startswith("DATA"):
        break
off = f.tell()
fields = [h for h in hdr if h.startswith("FIELDS")][0].split()[1:]
sizes = [int(s) for s in [h for h in hdr if h.startswith("SIZE")][0].split()[1:]]
n = int([h for h in hdr if h.startswith("POINTS")][0].split()[1])
stride = sum(sizes)
dt = np.dtype({"names": fields,
               "formats": ["<f4"] * len(fields),
               "itemsize": stride})
arr = np.fromfile(f, dtype=dt, count=n)  # f 已在数据起点；offset 是相对当前位置的，再传 off 会错位 255 字节
xyz = np.stack([arr["x"], arr["y"], arr["z"]], axis=1).astype(np.float64)

# 真实数据里混有两类脏点（FAST-LIO 保存所致），不过滤则统计与绘图全废：
#   a) NaN / Inf
#   b) float32 垃圾值，约 ±3.4e38（min/max 会被它们拉爆，看起来像"发散"其实是脏点）
ok = np.isfinite(xyz).all(axis=1)
# 阈值默认 30 m：真实场地在十几米量级；发散后的点动辄几百到几十万米，
# 阈值太宽（如 1e5）会把"中等垃圾"也留下，图上就糊成一片散点。
LIMIT = float(sys.argv[4]) if len(sys.argv) > 4 else 12.0
ok &= (np.abs(xyz) < LIMIT).all(axis=1)
dropped = len(xyz) - int(ok.sum())
xyz = xyz[ok]

print("文件   : %s" % path)
print("有效点 : %d（已剔除 NaN/Inf/垃圾值 %d 个）" % (len(xyz), dropped))
print("点数   : %d（%.1f 百万）" % (n, n / 1e6))
print("每点   : %d 字节，字段 %s" % (stride, ",".join(fields)))
print("x %8.1f ~ %8.1f" % (xyz[:, 0].min(), xyz[:, 0].max()))
print("y %8.1f ~ %8.1f" % (xyz[:, 1].min(), xyz[:, 1].max()))
print("z %8.1f ~ %8.1f" % (xyz[:, 2].min(), xyz[:, 2].max()))

mode = sys.argv[3] if len(sys.argv) > 3 else "top"

# 可选裁剪：CROP="zmin,zmax" 或 CROP="xmin,xmax,ymin,ymax,zmin,zmax"
# 旧图尾部有 FAST-LIO 漂移污染（z 中位数 1.75 m、5%~95% 跨 4.3 m），
# 裁掉不合理高度后轮廓会清楚很多。
crop = os.environ.get("CROP", "").strip()
if crop:
    v = [float(t) for t in crop.split(",")]
    if len(v) == 2:
        m = (xyz[:, 2] >= v[0]) & (xyz[:, 2] <= v[1])
    elif len(v) == 6:
        m = ((xyz[:, 0] >= v[0]) & (xyz[:, 0] <= v[1]) &
             (xyz[:, 1] >= v[2]) & (xyz[:, 1] <= v[3]) &
             (xyz[:, 2] >= v[4]) & (xyz[:, 2] <= v[5]))
    else:
        print("CROP 格式错误（2 或 6 个数字）"); sys.exit(1)
    print("裁剪   : %s -> 保留 %d 点（%.1f%%）" % (crop, int(m.sum()), 100 * m.sum() / max(1, len(xyz))))
    xyz = xyz[m]

if mode == "ds":
    # 注意用过滤【后】的长度 len(xyz)，不是原始点数 n，否则索引越界
    k = min(len(xyz), target)
    idx = np.random.choice(len(xyz), size=k, replace=False)
    out = xyz[idx]
    dst = os.environ.get("OUT", path.replace("lite3.pcd", "lite3_view.pcd"))
    with open(dst, "wb") as g:
        g.write(b"VERSION 0.7\n")
        g.write(b"FIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\n")
        g.write(("WIDTH %d\nHEIGHT 1\nPOINTS %d\nDATA binary\n" % (k, k)).encode())
        out.astype("<f4").tofile(g)
    print("降采样 : %d 点 -> %s（%.1f MB）"
          % (k, dst, k * 12 / 1e6))

elif mode == "top":
    W, H = 76, 30
    x0, x1 = xyz[:, 0].min(), xyz[:, 0].max()
    y0, y1 = xyz[:, 1].min(), xyz[:, 1].max()
    if x1 - x0 < 1e-6 or y1 - y0 < 1e-6:
        print("范围退化，无法画图"); sys.exit(0)
    ix = np.clip(((xyz[:, 0] - x0) / (x1 - x0) * (W - 1)).astype(int), 0, W - 1)
    iy = np.clip(((y1 - xyz[:, 1]) / (y1 - y0) * (H - 1)).astype(int), 0, H - 1)
    grid = np.zeros((H, W), dtype=int)
    np.add.at(grid, (iy, ix), 1)
    zmin, zmax = xyz[:, 2].min(), xyz[:, 2].max()
    zgrid = np.full((H, W), np.nan)
    np.minimum.at(zgrid, (iy, ix), xyz[:, 2])
    ramp = " .:-=+*#%@"
    print()
    print("俯视图（x 向右 %.1f→%.1f，y 向下 %.1f→%.1f；字符深浅=该格点数）" % (x0, x1, y1, y0))
    print("+" + "-" * W + "+")
    for r in range(H):
        row = grid[r]
        mx = row.max() if row.max() > 0 else 1
        line = "".join(ramp[min(len(ramp) - 1, int(v / mx * (len(ramp) - 1)))] for v in row)
        print("|" + line + "|")
    print("+" + "-" * W + "+")
    print("高度 z %.1f ~ %.1f m" % (zmin, zmax))
PY
}

case "$ACTION" in
  info) run_py info ;;
  top)  run_py top ;;
  ds)   run_py ds ;;
  pub)
    VIEW="${VIEW:-$WS/map/lite3_view.pcd}"
    if [ ! -f "$VIEW" ]; then
      echo "[view_pcd] 先降采样：$VIEW 不存在，跑 ds ..."
      MAP="$MAP" run_py ds
    fi
    # ⚠️ source 前 set +u 会终止 shell
    set +u
    # shellcheck disable=SC1090
    source "$HERE/env.sh" >/dev/null 2>&1
    set -u
    # 参考系列表来自 TF 树，不是话题 frame_id。本机 TF 树原本没有 map 帧，
    # 所以补一条 map->camera_init 的恒等静态 TF，Foxglove 里选 map 也能出图。
    if ! pgrep -f "static_transform_publisher 0 0 0 0 0 0 map camera_init" >/dev/null 2>&1; then
      setsid nohup rosrun tf2_ros static_transform_publisher 0 0 0 0 0 0 map camera_init \
        >"$WS/logs/pcd_tf.log" 2>&1 </dev/null &
      sleep 2
    fi
    echo "[view_pcd] 发布 $VIEW -> /cloud_pcd（frame_id=camera_init，0.2 Hz 循环）"
    echo "[view_pcd] Foxglove：3D 面板订阅 /cloud_pcd，固定参考系选 camera_init 或 map（两者等价）"
    echo "[view_pcd] ⚠️ 只看到坐标轴 + 散点？多半是显示设置，不是数据："
    echo "[view_pcd]    3D 面板 -> Point size 调大到 3~5；Color by 改 z/intensity；"
    echo "[view_pcd]    把 z 的 min/max 夹到 -1~3 m 剔除残留脏点（旧图尾部有发散污染）"
    rosrun pcl_ros pcd_to_pointcloud "$VIEW" 0.2 _frame_id:=camera_init _latch:=true
    ;;
  *)
    echo "用法：bash scripts/view_pcd.sh {top|ds|pub|info} [降采样目标点数]"
    exit 1
    ;;
esac
