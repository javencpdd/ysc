#!/bin/bash
# 真实链路验证：对生产中的 forward-f.log 做一次轮转，确认
#   1) 内容完整搬到历史文件（不丢）
#   2) 当前文件被截断但依然存在（gst 的 fd 不受影响，写入不中断）
#   3) 历史文件命名符合配置
# 用法（需 root）: bash verify-real-rotate.sh [上限字节]
LIMIT="${1:-100000}"
D=/home/user/rtmp_1012/logs
F="$D/forward-f.log"
KEEP_BAK=/tmp/forward-f.log.before

echo "================ 轮转前 ================"
ls -l "$F"
echo "行数: $(wc -l < "$F")"
cp -f "$F" "$KEEP_BAK"
echo "已备份到 $KEEP_BAK ($(stat -c %s "$KEEP_BAK") 字节)"
INODE_BEFORE=$(stat -c %i "$F")
echo "当前文件 inode = $INODE_BEFORE"

echo
echo "================ 触发轮转 (上限 ${LIMIT} 字节) ================"
M20LOG_MAX_BYTES="$LIMIT" M20LOG_VERBOSE=1 /usr/local/sbin/m20-log-rotate.sh
echo "(退出码 $?)"

echo
echo "================ 轮转后 ================"
ls -l "$D"

echo
echo "---- 校验 1: 内容完整性 ----"
H="$D/forward-f.1.log"
if [ -f "$H" ]; then
    B=$(stat -c %s "$KEEP_BAK"); A=$(stat -c %s "$H")
    echo "备份=$B 字节  历史.1=$A 字节"
    if diff -q "$KEEP_BAK" "$H" >/dev/null 2>&1; then
        echo "结果: 内容完全一致 —— 零丢失 ✅"
    elif [ "$A" -ge "$B" ]; then
        echo "结果: 历史文件 >= 备份（追赶复制带上了轮转瞬间的新行）✅"
        echo "---- 历史文件比备份多出的行 ----"
        diff "$KEEP_BAK" "$H" | head -5
    else
        echo "结果: 历史文件比备份少 $((B-A)) 字节 ⚠️"
    fi
else
    echo "结果: 未生成历史文件 ❌"
fi

echo
echo "---- 校验 2: 当前文件仍存在且 fd 未断 ----"
if [ -f "$F" ]; then
    echo "当前文件存在，大小=$(stat -c %s "$F") 字节"
    echo "inode 变化: $INODE_BEFORE -> $(stat -c %i "$F")  ($([ "$INODE_BEFORE" = "$(stat -c %i "$F")" ] && echo '未变 —— truncate 语义正确' || echo '已变'))"
    echo "当前文件权限/属主: $(stat -c '%U:%G %a' "$F")"
else
    echo "当前文件不存在 ❌（说明用了 mv 语义，gst 的 fd 会写进历史文件）"
fi

echo
echo "---- 校验 3: 命名格式 ----"
ls -1 "$D" | grep '^forward-f' || true
