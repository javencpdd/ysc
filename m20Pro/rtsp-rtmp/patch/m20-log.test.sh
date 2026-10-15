#!/bin/bash
# m20-log.sh 回归测试（在 196 主机上运行）
# 用法: bash m20-log.test.sh /tmp/m20-log.sh
LIB="${1:-/tmp/m20-log.sh}"
PASS=0; FAIL=0
ck() { # ck <描述> <实际> <期望>
    if [ "$2" = "$3" ]; then echo "  [PASS] $1 (= $2)"; PASS=$((PASS+1));
    else echo "  [FAIL] $1 实际=$2 期望=$3"; FAIL=$((FAIL+1)); fi
}

run_case() { # run_case <目录> <环境变量赋值...> -- <行数>
    local d="$1"; shift
    local n="$1"; shift
    rm -rf "$d"; mkdir -p "$d"
    ( source "$LIB"; export "$@" >/dev/null 2>&1; :; ) >/dev/null 2>&1
    :
}

echo "======================== T1: 单文件上限 + 保留份数 ========================"
D=/tmp/MT1; rm -rf $D; mkdir -p $D
bash -c "source $LIB
export M20LOG_MAX_BYTES=2000 M20LOG_KEEP=3 M20LOG_CHECK_BYTES=600
f=$D/app.log
for i in \$(seq 1 300); do m20log_emit \"\$f\" \"line \$i xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\"; done" 2>/dev/null
ck "历史份数=KEEP(3)" "$(ls -1 $D/app.*.log 2>/dev/null | wc -l)" "3"
ck "存在 .1" "$([ -f $D/app.1.log ] && echo yes || echo no)" "yes"
ck "存在 .3" "$([ -f $D/app.3.log ] && echo yes || echo no)" "yes"
ck "不存在 .4" "$([ -f $D/app.4.log ] && echo yes || echo no)" "no"
ck "当前文件未超上限" "$([ $(stat -c %s $D/app.log) -le 2600 ] && echo yes || echo no)" "yes"

echo "======================== T2: 保留 KEEP=5 ========================"
D=/tmp/MT2; rm -rf $D; mkdir -p $D
bash -c "source $LIB
export M20LOG_MAX_BYTES=2000 M20LOG_KEEP=5 M20LOG_CHECK_BYTES=600
f=$D/app.log
for i in \$(seq 1 500); do m20log_emit \"\$f\" \"line \$i xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\"; done" 2>/dev/null
ck "历史份数=5" "$(ls -1 $D/app.*.log 2>/dev/null | wc -l)" "5"
ck "不存在 .6" "$([ -f $D/app.6.log ] && echo yes || echo no)" "no"

echo "======================== T3: 总空间硬上限 ========================"
D=/tmp/MT3; rm -rf $D; mkdir -p $D
bash -c "source $LIB
export M20LOG_MAX_BYTES=3000 M20LOG_KEEP=5 M20LOG_TOTAL_MAX_BYTES=12000 M20LOG_CHECK_BYTES=700
f=$D/app.log
for i in \$(seq 1 500); do m20log_emit \"\$f\" \"line \$i cccccccccccccccccccccccccccccccccccccccc\"; done" 2>/dev/null
# 只统计日志文件本身（du -sb 会把目录项 4096 字节算进来，会误判）
TOT=$(find $D -type f -name '*.log' -printf '%s\n' 2>/dev/null | awk '{s+=$1}END{print s+0}')
echo "  日志内容合计=${TOT} 字节 (总上限 12000，单文件上限 3000)"
ck "历史份数被压到 <5" "$([ $(ls -1 $D/app.*.log 2>/dev/null | wc -l) -lt 5 ] && echo yes || echo no)" "yes"
ck "合计 <= 总上限(12000)" "$([ "$TOT" -le 12000 ] && echo yes || echo no)" "yes"

echo "======================== T4: ts 时间戳命名 ========================"
D=/tmp/MT4; rm -rf $D; mkdir -p $D
bash -c "source $LIB
export M20LOG_MAX_BYTES=2000 M20LOG_KEEP=2 M20LOG_NAME_FMT=ts M20LOG_CHECK_BYTES=600
f=$D/forward-f.log
for i in \$(seq 1 200); do m20log_emit \"\$f\" \"line \$i dddddddddddddddddddddddddddddddddddddd\"; done" 2>/dev/null
echo "  目录: $(ls -1 $D)"
ck "存在时间戳命名文件" "$(ls -1 $D | grep -cE 'forward-f-[0-9]{8}-[0-9]{6}(-p[0-9]+)?\.log')" "2"
ck "历史不超过 KEEP=2" "$([ $(ls -1 $D/forward-f-*.log 2>/dev/null | wc -l) -le 2 ] && echo yes || echo no)" "yes"

echo "======================== T5: 多进程并发不丢不坏 ========================"
D=/tmp/MT5; rm -rf $D; mkdir -p $D
bash -c "source $LIB
export M20LOG_MAX_BYTES=4000 M20LOG_KEEP=3 M20LOG_CHECK_BYTES=800
f=$D/app.log
for p in 1 2 3 4 5 6 7 8; do
  ( for i in \$(seq 1 150); do m20log_emit \"\$f\" \"p\$p-line\$i bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\"; done ) &
done
wait" 2>/dev/null
TOT=$(cat $D/app.log $D/app.*.log 2>/dev/null | wc -l)
BAD=$(cat $D/app.log $D/app.*.log 2>/dev/null | grep -cvE '^p[1-8]-line[0-9]+ ')
echo "  期望 1200 行，实际 $TOT 行，丢失 $((1200-TOT))"
ck "丢失率 < 2%" "$([ $((1200-TOT)) -lt 24 ] && echo yes || echo no)" "yes"
ck "无半行/交错损坏" "$BAD" "0"

echo "======================== T6: 持有 fd 的写入方不中断 ========================"
D=/tmp/MT6; rm -rf $D; mkdir -p $D
bash -c "source $LIB
export M20LOG_MAX_BYTES=3000 M20LOG_KEEP=2
f=$D/app.log
( exec 3>>\"\$f\"; for i in \$(seq 1 400); do printf 'gstline %04d %s\n' \"\$i\" 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' >&3; sleep 0.005; done; exec 3>&- ) &
for k in \$(seq 1 12); do sleep 0.3; m20log_check \"\$f\"; done
wait" 2>/dev/null
ck "当前文件仍存在且非空" "$([ -s $D/app.log ] && echo yes || echo no)" "yes"
ck "最后一行写进了当前文件(未被 mv 走)" "$(tail -1 $D/app.log | grep -c 'gstline 0400')" "1"
ck "历史文件保存了旧内容" "$([ -s $D/app.1.log ] && echo yes || echo no)" "yes"

echo "======================== T7: mv 模式对照(应证明会坏) ========================"
D=/tmp/MT7; rm -rf $D; mkdir -p $D
bash -c "source $LIB
export M20LOG_MAX_BYTES=3000 M20LOG_KEEP=2 M20LOG_MODE=mv
f=$D/app.log
( exec 3>>\"\$f\"; for i in \$(seq 1 400); do printf 'gstline %04d %s\n' \"\$i\" 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' >&3; sleep 0.005; done; exec 3>&- ) &
for k in \$(seq 1 12); do sleep 0.3; m20log_check \"\$f\"; done
wait" 2>/dev/null
echo "  目录: $(ls -1 $D)"
ck "当前文件消失(日志全跑到 .1)" "$([ -f $D/app.log ] && echo no || echo yes)" "yes"

echo
echo "================= 汇总: PASS=$PASS  FAIL=$FAIL ================="
[ "$FAIL" -eq 0 ]
