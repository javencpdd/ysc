#!/usr/bin/env bash
# P5 存储治理：安装日志轮换与 journald 限额（幂等，可重复执行）。
#
# 必须在 103 上执行：
#   sudo bash /home/test/yolo8/deploy/install-retention.sh
#   bash /home/test/yolo8/deploy/install-retention.sh --check   # 只检查不安装
#
# 装两样：
#   1) /etc/logrotate.d/lite3-yolo8     —— logs/*.log 每天轮转、留 7 份、压缩
#   2) /etc/systemd/journald.conf.d/lite3-yolo8.conf —— journal 上限 200M / 7 天
#
# 为什么用 copytruncate：console 与 worker 都是长驻进程、持有 fd 追加写，
# 没有实现 SIGHUP 重开日志，rename 那套会让进程继续往已轮转的旧文件里写。
# copytruncate 是唯一不需要改代码的选择（m20-ai-detect ADR-008 同结论）。
set -u

APP=/home/test/yolo8
SRC_LOGROTATE="$APP/deploy/lite3-yolo8.logrotate"
SRC_JOURNALD="$APP/deploy/lite3-yolo8-journald.conf"
DST_LOGROTATE=/etc/logrotate.d/lite3-yolo8
DST_JOURNALD_DIR=/etc/systemd/journald.conf.d
DST_JOURNALD="$DST_JOURNALD_DIR/lite3-yolo8.conf"

say()  { printf '%s\n' "$1"; }

do_check() {
  echo "===== 存储治理安装状态 ====="
  if [ -f "$DST_LOGROTATE" ]; then
    echo "[ok]   logrotate 已安装：$DST_LOGROTATE"
  else
    echo "[缺]   logrotate 未安装"
  fi
  if [ -f "$DST_JOURNALD" ]; then
    echo "[ok]   journald 限额已安装：$DST_JOURNALD"
  else
    echo "[缺]   journald 限额未安装"
  fi
  echo "----- logs/ 当前占用 -----"
  du -sh "$APP"/logs/*.log 2>/dev/null | sort -h | tail -8
  echo "合计：$(du -sh "$APP/logs" 2>/dev/null | cut -f1)"
  echo "----- 最近轮转产物 -----"
  ls -1 "$APP"/logs/*.log.* 2>/dev/null | tail -5 || echo "（暂无，首次轮转后生成）"
}

if [ "${1:-}" = "--check" ]; then
  do_check
  exit 0
fi

[ -f "$SRC_LOGROTATE" ] || { echo "缺少 $SRC_LOGROTATE"; exit 1; }
[ -f "$SRC_JOURNALD" ] || { echo "缺少 $SRC_JOURNALD"; exit 1; }

if [ "$(id -u)" -ne 0 ]; then
  echo "需要 root（写 /etc）；请用：sudo bash $0"
  exit 1
fi

say "== 安装 logrotate"
# logs/ 是 group-writable：logrotate 不写 su 会报 "parent directory has
# insecure permissions" 并**跳过**这个文件（配了等于没配）。按实际属主渲染。
RENDERED=$(mktemp)
OWNER=$(stat -c "%U %G" "$APP/logs" 2>/dev/null || true)
if [ -n "$OWNER" ]; then
  sed "s|^[[:space:]]*su .*|    su $OWNER|" "$SRC_LOGROTATE" > "$RENDERED"
  say "  属主渲染为：su $OWNER"
else
  cp "$SRC_LOGROTATE" "$RENDERED"
  say "  取不到属主，沿用配置里的 su"
fi
install -m 644 "$RENDERED" "$DST_LOGROTATE"
rm -f "$RENDERED"
if command -v logrotate >/dev/null 2>&1; then
  # --debug 只解析不执行；有 error 行说明这条配置实际不会生效
  if logrotate --debug "$DST_LOGROTATE" 2>&1 | grep -q "^error:"; then
    say "  警告：logrotate 解析有 error，轮转不会生效："
    logrotate --debug "$DST_LOGROTATE" 2>&1 | grep "^error:" | head -3
  else
    say "  logrotate 配置解析 OK"
  fi
else
  say "  警告：本机没有 logrotate 二进制，配置已就位但不会自动轮转"
fi

say "== 安装 journald 限额"
mkdir -p "$DST_JOURNALD_DIR"
install -m 644 "$SRC_JOURNALD" "$DST_JOURNALD"
systemctl restart systemd-journald 2>/dev/null \
  && say "  systemd-journald 已重启" || say "  警告：重启 systemd-journald 失败（可忽略，下次启动生效）"

say ""
say "安装完成。用 --check 复查状态。"
