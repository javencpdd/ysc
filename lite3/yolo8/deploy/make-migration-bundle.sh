#!/usr/bin/env bash
# 生成 yolo8 换机迁移包（在源机 103 上执行，只读原工程，产出在 /tmp）
#
#   bash /home/test/yolo8/deploy/make-migration-bundle.sh [输出目录]
#
# 权威依据：note/23-yolo8移植部署流程.md §3 打包清单。
# 本脚本把清单固化成可复用命令，避免每次手打 --exclude 漏项。
#
# 收进包：src console deploy config note model(仅 aarch64 资产)
# 排除：  logs pic deploy/backup-* __pycache__ *.bak-* .git *.pyc
#         model/yolov8n_amd.engine(x86专用) model/exports model/uploads
set -euo pipefail

SRC="${SRC:-/home/test/yolo8}"
OUT="${1:-/tmp}"
TS="$(date +%Y%m%d-%H%M%S)"
PKG="$OUT/yolo8-migration-$TS.tgz"

[ -d "$SRC" ] || { echo "找不到工程目录：$SRC（可用 SRC=... 覆盖）" >&2; exit 1; }

# 打包前先扫一遍凭据，避免把明文令牌带进包
# 字符类变形：pattern 匹配真实令牌，但不会匹配到本行自身
if grep -rqE 'jack1[4]19|1761f47[d]560a2ec3c278215a733d57f0' "$SRC" 2>/dev/null; then
  echo "警告：工程内仍检出已知令牌明文，请先脱敏再打包" >&2
  echo "  （迁移包要求 token 为占位符 CHANGE_ME_ON_TARGET_HOST）" >&2
  exit 2
fi

cd "$SRC"
tar czf "$PKG" \
  --exclude=logs --exclude=pic \
  --exclude=deploy/backup-* --exclude=__pycache__ \
  --exclude=model/yolov8n_amd.engine --exclude=model/exports --exclude=model/uploads \
  --exclude='*.bak-*' --exclude=.git --exclude='*.pyc' \
  src console deploy config note model

# 自检：排除项一个都不该出现
BAD="$(tar tzf "$PKG" | grep -cE 'backup-|\.bak-|__pycache__|amd\.engine|/logs/|/pic/|exports/|uploads/|\.pyc|\.git/' || true)"
[ "$BAD" = "0" ] || { echo "自检失败：包内含 $BAD 个应排除项" >&2; exit 3; }

echo "已生成：$PKG"
ls -lh "$PKG"
echo
echo "包内顶层条目："
tar tzf "$PKG" | awk -F/ 'NF>1{print $1}' | sort | uniq -c | sort -rn
echo
echo "md5：$(md5sum "$PKG" | cut -d' ' -f1)"
echo
echo "下一步：scp $PKG ysc@<新103>:/tmp/  然后按 note/23-yolo8移植部署流程.md §6 阶段 3 起执行"
