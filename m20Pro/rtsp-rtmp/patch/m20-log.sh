#!/bin/bash
# ============================================================================
# m20-log.sh —— 日志写入 + 文件大小上限轮转库
#
# 设计目标（对应 2026-10-16 用户提出的需求）：
#   1) 单个日志文件达到上限（默认 10MB）自动切分，新建/清空后继续写入
#   2) 保留最近 N 个历史文件（默认 5），超出删除最旧的
#   3) 轮转文件带序号或时间戳命名
#   4) 切换过程不丢日志、不中断写入（含"长期持有 fd"的写入方）
#   5) 多进程 / 多线程（多进程追加）场景安全
#   6) 上限、份数、目录、命名格式均可配置，且有默认值
#   7) 对调用方保持原有日志调用方式不变
#
# 用法：
#   source /path/to/m20-log.sh
#   m20log_emit <file> <一行内容>      # 写一行（写前按需轮转）—— 推荐
#   m20log      <file> <消息...>       # 同上，内部拼成一行
#   m20log_check <file>                # 只检查并按需轮转（不写内容）
#   m20log_rotate <file> [force]       # 强制轮转（不看大小）
#   m20log_scan <dir> [glob]           # 扫描目录内所有日志并按需轮转
#
# 独立执行（供巡检/命令行使用）：
#   m20-log.sh --scan <dir> [glob]
#   m20-log.sh --rotate <file> [force]
#   m20-log.sh --self-test             # 内置自检
#
# ---------------------------------------------------------------------------
# 为什么默认用 copytruncate 而不是 mv？（关键）
#
#   本项目的推流进程是这样写日志的（rtmp_forward.sh L331/333）：
#         taskset -c "$CPUSET" "${PIPE[@]}" >>"$LOG_FILE" 2>&1 &
#   即 gst-launch 在启动时打开一次 fd 并长期持有。此时若用 mv 改名：
#     - 新文件被创建，但 gst 的 fd 仍指向旧 inode → 日志继续写进已被改名的
#       .1 文件，新的 .log 永远是空的，且 .1 会无限增长（这正是 475MB 的成因）。
#   copytruncate 的做法是「复制内容到轮转文件 + 把原文件截断为 0」：
#     - fd 不变、写入不中断，进程无感知。
#     - 代价：cp 与 truncate 之间存在极小窗口（毫秒级），窗口内写入的字节
#       会随截断丢失。若要零丢失且写入方是「每次 open 追加」（如 shell 的
#       printf >> file），可把 M20LOG_MODE 设为 mv，那样是原子改名、零丢失。
# ---------------------------------------------------------------------------
#
# 并发安全：
#   - 轮转前用 flock 对 <dir>/.m20log.<name>.lock 加互斥锁（等待
#     M20LOG_LOCK_WAIT 秒，超时则放弃本轮，绝不阻塞日志写入）。
#   - 拿到锁后做「双重检查」：可能别的进程刚轮转完，此时大小已回落，直接返回。
#   - 写入一律用 >>（O_APPEND）。单次写入小于 PIPE_BUF(4096B) 时内核保证原子，
#     故多行并发追加不会互相覆盖；超长单行仍可能与另一行交错，属 POSIX 固有限制。
# ============================================================================

# ------------------------------ 可配置参数 ----------------------------------
# 说明：全部可用环境变量覆盖；未设置时使用下面的默认值。
# 建议在 config.env 中统一配置。
: "${M20LOG_MAX_BYTES:=10485760}"     # 单文件大小上限(字节)，默认 10MB(10*1024*1024)
                                      #   达到或超过该值即触发一次轮转
: "${M20LOG_KEEP:=5}"                 # 保留的历史文件份数，默认 5（不含当前正在写的）
                                      #   => 隐含总空间上限 = MAX_BYTES * (KEEP+1)
                                      #      例 10MB * (5+1) = 60MB
: "${M20LOG_CATCHUP_ROUNDS:=4}"       # copytruncate 的追赶轮数：复制期间若文件仍在增长，
                                      #   最多再追加追赶几轮，用于压缩「复制->截断」的
                                      #   丢失窗口。默认 4。0 = 只复制一次（最快但丢失最多）
: "${M20LOG_TOTAL_MAX_BYTES:=0}"      # 【总空间硬上限】同一日志文件族（当前 + 所有历史）
                                      #   的合计字节上限。默认 0 = 不额外限制（由上面
                                      #   两个参数隐式决定）。若 > 0，即使历史份数没到
                                      #   KEEP，只要合计超过该值就从最旧开始删除，
                                      #   直到落回上限内（当前正在写的文件永不删）。
                                      #   用于「磁盘就这么大」的场景做兜底。
: "${M20LOG_DIR:=}"                   # 日志目录。用于：① m20log_scan 扫描目标目录；
                                      #   ② 若设置，轮转产生的历史文件也放到该目录
                                      #   （默认留空 = 与当前日志文件同目录）
: "${M20LOG_NAME_FMT:=seq}"           # 轮转文件命名格式：
                                      #   seq -> {base}.{n}.{ext}   例 forward-f.1.log
                                      #   ts  -> {base}-{ts}.{ext}  例 forward-f-20261016-030900.log
                                      #   也可直接写模板，占位符：{base} {ext} {n} {ts}
: "${M20LOG_MODE:=copytruncate}"      # 轮转模式：
                                      #   copytruncate = 复制后截断（fd 不变，写入不中断；默认）
                                      #   mv           = 原子改名（零丢失，但仅适用于
                                      #                   「每次 open 追加」的写入方）
: "${M20LOG_TS_FMT:=%Y%m%d-%H%M%S}"   # {ts} 占位符的 date 格式，默认 20261016-030900
: "${M20LOG_LOCK_WAIT:=0}"            # 抢锁等待秒数。默认 0 = 非阻塞：抢不到锁立即放弃
                                      #   本轮（说明别的进程正在轮转，交给它做即可）。
                                      #   设为 >0 反而有害：竞争进程会被阻塞，醒来时
                                      #   正好撞上 truncate，白白多丢日志。
: "${M20LOG_MIN_CHECK_INTERVAL:=1}"   # m20log_emit 的最小检查间隔(秒)。
                                      #   低频日志靠它保证「迟早会被检查到」。0 = 每次都检查
: "${M20LOG_CHECK_BYTES:=4096}"       # m20log_emit 累积写入多少字节后做一次大小检查。
                                      #   这是主要触发条件（确定性，不依赖时钟）：
                                      #   高频日志按量触发，不会因「1 秒内写完」而漏检。
                                      #   副作用：单文件实际大小最多超出上限约该值(默认 4KB)
: "${M20LOG_VERBOSE:=0}"              # 1 = 轮转时向 stderr 打印一行提示

# --------------------------------- 内部函数 ---------------------------------

_m20log_size() { stat -c %s "$1" 2>/dev/null || echo 0; }

# 获取互斥锁。成功返回 0，失败返回 1。
#   优先 flock（util-linux，Ubuntu 自带）；不可用时回退到 mkdir 原子锁，
#   保证「没有 flock 也不会退化成永不轮转」。
#   注意：调用方负责在结束后 _m20log_unlock。
_M20LOG_LOCK_DIR=""
_m20log_lock() {
    local lock="$1"
    mkdir -p "$(dirname "$lock")" 2>/dev/null || return 1
    # 先用 touch 探测可写：因为「exec 只带重定向且失败」会让非交互 shell 直接
    # 退出（连 || 都不会执行），必须先确保打开一定成功再 exec。
    touch "$lock" 2>/dev/null || return 1
    exec 9>>"$lock" 2>/dev/null || return 1
    if command -v flock >/dev/null 2>&1; then
        # 默认非阻塞：拿不到锁说明别的进程正在轮转，交给它做，自己立即继续写
        if [ "${M20LOG_LOCK_WAIT:-0}" -gt 0 ]; then
            flock -w "$M20LOG_LOCK_WAIT" 9 2>/dev/null && return 0
        else
            flock -n 9 2>/dev/null && return 0
        fi
        exec 9>&- 2>/dev/null
        return 1
    fi
    # 回退：mkdir 是原子的。带陈旧检测（超过 60s 视为死锁残留并清除）
    _M20LOG_LOCK_DIR="${lock}.d"
    if mkdir "$_M20LOG_LOCK_DIR" 2>/dev/null; then
        return 0
    fi
    if [ -d "$_M20LOG_LOCK_DIR" ]; then
        local age now mt
        now="$(date +%s)"
        mt="$(stat -c %Y "$_M20LOG_LOCK_DIR" 2>/dev/null || echo "$now")"
        age=$(( now - mt ))
        if [ "$age" -gt 60 ]; then
            rmdir "$_M20LOG_LOCK_DIR" 2>/dev/null
            mkdir "$_M20LOG_LOCK_DIR" 2>/dev/null && return 0
        fi
    fi
    exec 9>&- 2>/dev/null
    return 1
}

_m20log_unlock() {
    if [ -n "$_M20LOG_LOCK_DIR" ] && [ -d "$_M20LOG_LOCK_DIR" ]; then
        rmdir "$_M20LOG_LOCK_DIR" 2>/dev/null
        _M20LOG_LOCK_DIR=""
    fi
    flock -u 9 2>/dev/null
    exec 9>&- 2>/dev/null
    return 0
}

# 锁文件路径（与日志文件同目录，文件名做安全化）
_m20log_lockfile() {
    local d b
    d="$(dirname "$1")"
    b="$(basename "$1" | tr -c 'A-Za-z0-9._-' '_')"
    printf '%s/.m20log.%s.lock' "$d" "$b"
}

# 历史文件存放目录：M20LOG_DIR 优先，否则与源文件同目录
_m20log_hotdir() {
    if [ -n "$M20LOG_DIR" ]; then
        printf '%s' "$M20LOG_DIR"
    else
        dirname "$1"
    fi
}

# 依据模板生成轮转文件名。$2 = 序号(seq) 或 任意值(ts 模式下不使用)
_m20log_target() {
    local file="$1" n="$2" dir base ext tpl out ts
    dir="$(_m20log_hotdir "$file")"
    base="$(basename "$file")"
    ext="${base##*.}"
    if [ "$base" = "$ext" ]; then ext="log"; else base="${base%.*}"; fi

    tpl="$M20LOG_NAME_FMT"
    case "$tpl" in
        seq) tpl='{base}.{n}.{ext}' ;;
        ts)  tpl='{base}-{ts}.{ext}' ;;
    esac

    ts="$(date +"$M20LOG_TS_FMT" 2>/dev/null || date +%Y%m%d-%H%M%S)"
    out="$tpl"
    out="${out//\{base\}/$base}"
    out="${out//\{ext\}/$ext}"
    out="${out//\{n\}/$n}"
    out="${out//\{ts\}/$ts}"
    printf '%s/%s' "$dir" "$out"
}

# ts 模式：清理超出 KEEP 的历史（按修改时间倒序，保留最新的 KEEP 个）
_m20log_prune_ts() {
    local file="$1" dir base ext cnt=0 f
    dir="$(_m20log_hotdir "$file")"
    base="$(basename "$file")"
    ext="${base##*.}"
    if [ "$base" = "$ext" ]; then ext="log"; else base="${base%.*}"; fi
    [ -d "$dir" ] || return 0

    # ls -1t : 按 mtime 倒序（最新在前）
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        cnt=$(( cnt + 1 ))
        if [ "$cnt" -gt "$M20LOG_KEEP" ]; then
            rm -f "$dir/$f" 2>/dev/null
        fi
    done <<EOF
$(ls -1t "$dir" 2>/dev/null | grep -E "^${base}-.+\.${ext}$")
EOF
}

# seq 模式：把 .1..KEEP-1 逆序后移，腾出 .1；再删除越界的旧文件
_m20log_shift_seq() {
    local file="$1" i src dst
    i=$(( M20LOG_KEEP - 1 ))
    while [ "$i" -ge 1 ]; do
        src="$(_m20log_target "$file" "$i")"
        dst="$(_m20log_target "$file" "$(( i + 1 ))")"
        [ -f "$src" ] && mv -f "$src" "$dst" 2>/dev/null
        i=$(( i - 1 ))
    done
    # 清理越界（例如 KEEP 调小后残留的 .6 .7 ...）
    i=$(( M20LOG_KEEP + 1 ))
    while [ "$i" -le $(( M20LOG_KEEP + 50 )) ]; do
        rm -f "$(_m20log_target "$file" "$i")" 2>/dev/null
        i=$(( i + 1 ))
    done
}

# 总空间硬上限：合计超过 M20LOG_TOTAL_MAX_BYTES 时，从最旧的开始删除历史文件。
# 当前正在写的文件永不删除。仅在 M20LOG_TOTAL_MAX_BYTES > 0 时生效。
_m20log_prune_total() {
    local file="$1" limit="${M20LOG_TOTAL_MAX_BYTES:-0}"
    [ "$limit" -gt 0 ] || return 0

    local dir base ext
    dir="$(_m20log_hotdir "$file")"
    base="$(basename "$file")"
    ext="${base##*.}"
    if [ "$base" = "$ext" ]; then ext="log"; else base="${base%.*}"; fi
    [ -d "$dir" ] || return 0

    # 历史文件，按 mtime 由新到旧（末尾即最旧）
    local files=() f total sz i
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        [ "$dir/$f" = "$file" ] && continue      # 跳过当前文件
        files+=("$dir/$f")
    done < <(ls -1t "$dir" 2>/dev/null | grep -E "^${base}[.-].+\.${ext}$")

    # 给「当前正在写的文件」预留一个满文件的空间：
    # 否则两次轮转之间当前文件持续增长，会短暂突破总上限。
    # 目标：历史总和 <= limit - 单文件上限
    local budget=$(( limit - ${M20LOG_MAX_BYTES:-0} ))
    [ "$budget" -lt 0 ] && budget=0

    total=0
    for f in ${files[@]+"${files[@]}"}; do
        total=$(( total + $(_m20log_size "$f") ))
    done

    for (( i=${#files[@]}-1; i>=0; i-- )); do
        [ "$total" -le "$budget" ] && break
        sz="$(_m20log_size "${files[$i]}")"
        if rm -f "${files[$i]}" 2>/dev/null; then
            total=$(( total - sz ))
        fi
    done
    return 0
}

# ---------------------------------------------------------------------------
# m20log_rotate <file> [force]
#   检查（或强制）轮转单个日志文件。返回 0 表示正常（未轮转也算正常）。
# ---------------------------------------------------------------------------
m20log_rotate() {
    local file="$1" force="${2:-}"
    [ -n "$file" ] || return 1
    [ -f "$file" ] || return 0

    local lock hotdir
    lock="$(_m20log_lockfile "$file")"
    hotdir="$(_m20log_hotdir "$file")"
    mkdir -p "$hotdir" "$(dirname "$lock")" 2>/dev/null

    # 加互斥锁（flock 优先，回退 mkdir 原子锁）
    if ! _m20log_lock "$lock"; then
        [ "$M20LOG_VERBOSE" = "1" ] && \
            printf 'm20log: 抢锁超时(%ss)，跳过本轮: %s\n' "$M20LOG_LOCK_WAIT" "$file" >&2
        return 0
    fi

    # 双重检查：拿到锁后重新判断大小（别的进程可能刚轮转完）
    if [ "$force" != "force" ] && [ "$(_m20log_size "$file")" -lt "$M20LOG_MAX_BYTES" ]; then
        _m20log_unlock
        return 0
    fi

    local target tmp
    case "$M20LOG_NAME_FMT" in
        ts|'{base}-{ts}.{ext}')
            target="$(_m20log_target "$file" 1)"
            # 同一秒内多次轮转会撞名，追加 -p<PID> 区分（不影响字典序排序）
            [ -e "$target" ] && target="${target%.log}-p$$.log"
            ;;
        *)
            _m20log_shift_seq "$file"
            target="$(_m20log_target "$file" 1)"
            ;;
    esac

    local ok=0
    case "$M20LOG_MODE" in
        mv)
            # 原子改名：零丢失，但仅适用于「每次 open 追加」的写入方
            if mv -f "$file" "$target" 2>/dev/null; then ok=1; fi
            ;;
        copytruncate|*)
            # 「追赶式复制」：单纯 cat 再 truncate 会丢掉复制期间新增的字节，
            # 高并发下丢失可达数十个百分点。这里分多轮追加追赶：
            #   记录上轮已复制到的偏移 -> 把 [偏移, 当前末尾] 追加到临时文件 ->
            #   若文件还在增长则再来一轮，直到稳定或达到轮数上限。
            # 这样丢失仅剩「最后一轮读取之后到 truncate 之间」的极小窗口。
            tmp="${target}.tmp.$$"
            : >"$tmp" 2>/dev/null
            local prev=0 cur=0 round=0
            while [ "$round" -lt "${M20LOG_CATCHUP_ROUNDS:-4}" ]; do
                cur="$(_m20log_size "$file")"
                [ "$cur" -le "$prev" ] && break
                tail -c +"$(( prev + 1 ))" "$file" >>"$tmp" 2>/dev/null || break
                prev="$cur"
                round=$(( round + 1 ))
            done
            if [ "$round" -gt 0 ] && mv -f "$tmp" "$target" 2>/dev/null; then
                : >"$file" 2>/dev/null      # truncate 为 0（fd 不变，写入不中断）
                ok=1
            else
                rm -f "$tmp" 2>/dev/null
            fi
            ;;
    esac

    [ "$M20LOG_NAME_FMT" = "ts" ] && _m20log_prune_ts "$file"
    _m20log_prune_total "$file"

    if [ "$ok" = "1" ] && [ "$M20LOG_VERBOSE" = "1" ]; then
        printf 'm20log: 已轮转 %s -> %s (上限 %s 字节, 保留 %s 份, 模式 %s)\n' \
            "$file" "$target" "$M20LOG_MAX_BYTES" "$M20LOG_KEEP" "$M20LOG_MODE" >&2
    fi

    _m20log_unlock
    return 0
}

# ---------------------------------------------------------------------------
# m20log_check <file>   只做「达到上限就轮转」的检查，不写内容
# ---------------------------------------------------------------------------
m20log_check() {
    local file="$1"
    [ -n "$file" ] && [ -f "$file" ] || return 0
    [ "$(_m20log_size "$file")" -ge "$M20LOG_MAX_BYTES" ] || return 0
    m20log_rotate "$file"
}

# ---------------------------------------------------------------------------
# m20log_emit <file> <一行内容>
#   追加一行；写前按 M20LOG_MIN_CHECK_INTERVAL 节流做一次大小检查。
# ---------------------------------------------------------------------------
# 初值取 -1：保证「第一次调用必定检查」（SECONDS 从 0 开始，0-(-1)=1 >= 默认间隔 1）
_M20LOG_LAST_CHECK="${_M20LOG_LAST_CHECK:--1}"
_M20LOG_ACC="${_M20LOG_ACC:-0}"
m20log_emit() {
    local file="$1"; shift
    [ -n "$file" ] || return 1
    local line="$*"
    local do_check=0 interval now
    interval="${M20LOG_MIN_CHECK_INTERVAL:-1}"
    now="${SECONDS:-0}"

    # 触发条件（任一满足即检查）：
    #   ① interval=0 → 每次都检查
    #   ② 累积写入字节数达到 M20LOG_CHECK_BYTES（主触发条件，确定性，不依赖时钟）
    #   ③ 距上次检查已超过 interval 秒（保证低频日志也会被检查到）
    _M20LOG_ACC=$(( _M20LOG_ACC + ${#line} + 1 ))
    if [ "$interval" = "0" ]; then
        do_check=1
    elif [ "$_M20LOG_ACC" -ge "${M20LOG_CHECK_BYTES:-4096}" ]; then
        do_check=1
    elif [ $(( now - _M20LOG_LAST_CHECK )) -ge "$interval" ]; then
        do_check=1
    fi

    if [ "$do_check" = "1" ]; then
        _M20LOG_ACC=0
        _M20LOG_LAST_CHECK=$now
        m20log_check "$file"
    fi

    printf '%s\n' "$line" >>"$file" 2>/dev/null
    return 0
}

# ---------------------------------------------------------------------------
# m20log <file> <消息...>    多参数版 emit（内部用空格拼成一行）
# ---------------------------------------------------------------------------
m20log() {
    local file="$1"; shift
    m20log_emit "$file" "$*"
}

# ---------------------------------------------------------------------------
# m20log_scan <dir> [glob]   扫描目录内日志文件并按需轮转
#   默认 glob 为 '*.log'（只匹配一级目录，不含子目录；跳过已轮转的历史文件）
# ---------------------------------------------------------------------------
m20log_scan() {
    local dir="${1:-$M20LOG_DIR}" glob="${2:-*.log}" f
    [ -n "$dir" ] && [ -d "$dir" ] || return 0
    for f in "$dir"/$glob; do
        [ -f "$f" ] || continue
        m20log_check "$f"
    done
    return 0
}

# ---------------------------------------------------------------------------
# 独立执行入口
# ---------------------------------------------------------------------------
if [ "${BASH_SOURCE[0]}" = "$0" ] 2>/dev/null || [ "${0##*/}" = "m20-log.sh" ]; then
    case "${1:-}" in
        --scan)   shift; m20log_scan "${1:-$M20LOG_DIR}" "${2:-*.log}" ;;
        --rotate) shift; m20log_rotate "$1" "${2:-}" ;;
        --check)  shift; m20log_check "$1" ;;
        --self-test)
            d="$(mktemp -d /tmp/m20log-test.XXXXXX)" || exit 1
            export M20LOG_MAX_BYTES=2000 M20LOG_KEEP=3 M20LOG_VERBOSE=1
            f="$d/app.log"
            i=0
            while [ "$i" -lt 400 ]; do
                m20log_emit "$f" "$(printf 'line %04d %s' "$i" '............................')"
                i=$(( i + 1 ))
            done
            echo "--- 目录内容 ---"; ls -1 "$d"
            echo "--- 当前文件大小: $(_m20log_size "$f") ---"
            m20log_scan "$d"
            rm -rf "$d"
            ;;
        -h|--help|*)
            sed -n '2,60p' "$0"
            ;;
    esac
fi
