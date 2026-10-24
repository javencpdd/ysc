#!/usr/bin/env bash
# ============================================================
# 部署前环境预检查（**只读，不创建/不修改任何文件**）
#
# 用途：在决定"部署到哪个目录"之前，先判断这台机器适不适合部署、这个路径合不合适。
#
# 用法（在目标 GOS 主机上执行，随便哪个目录都行）：
#   bash deploy/preflight.sh                          # 检查当前项目目录
#   bash deploy/preflight.sh --base ~/m20-ai-detect   # 检查候选目录（首次部署前推荐）
#   bash deploy/preflight.sh --skip-network           # 跳过相机/AI 连通性（离线现场）
#   bash deploy/preflight.sh --strict                 # WARN 也算不通过
#
# 退出码：0 = 可以部署（可能带 WARN）；1 = 有 FAIL，先修
# ============================================================
set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="${M20AI_BASE_DIR:-$(dirname "$SELF_DIR")}"
SKIP_NET=0
STRICT=0
SRC_F=""
AI_BASE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --base)          BASE="${2:-}"; shift 2 ;;
        --src-front)     SRC_F="${2:-}"; shift 2 ;;
        --ai-base)       AI_BASE="${2:-}"; shift 2 ;;
        --skip-network)  SKIP_NET=1; shift ;;
        --strict)        STRICT=1; shift ;;
        -h|--help)       sed -n '2,/^set -uo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "未知参数：$1（--help 看用法）" >&2; exit 2 ;;
    esac
done

PASS=0; WARN=0; FAIL=0
ok()   { printf "  \033[32m[PASS]\033[0m %-22s %s\n" "$1" "$2"; PASS=$((PASS+1)); }
warn() { printf "  \033[33m[WARN]\033[0m %-22s %s\n" "$1" "$2"; WARN=$((WARN+1)); }
bad()  { printf "  \033[31m[FAIL]\033[0m %-22s %s\n" "$1" "$2"; FAIL=$((FAIL+1)); }
sec()  { printf "\n\033[1m%s\033[0m\n" "$1"; }

# 路径规范化：既支持真相对路径，也兼容「漏写开头 /」这种最常见的误操作。
# 顺序：$PWD/原值（真相对路径）→ /原值（补斜杠）→ 兜底 $PWD/原值。
if [[ "$BASE" != /* ]]; then
    _orig="$BASE"
    if [[ -d "$PWD/$BASE" ]]; then
        BASE="$PWD/$BASE"
        warn "路径" "相对路径 $_orig → 解析为 $BASE（建议直接传绝对路径）"
    elif [[ -d "/$BASE" ]]; then
        BASE="/$BASE"
        warn "路径" "看起来漏了开头的 /：$_orig → 已按 /$_orig 解析为 $BASE"
    else
        BASE="$PWD/$BASE"
        warn "路径" "相对路径 $_orig → 解析为 $BASE（该目录不存在）"
    fi
fi
if command -v readlink >/dev/null 2>&1; then
    BASE="$(readlink -f "$BASE" 2>/dev/null || echo "$BASE")"
fi

printf "\033[36m===== 部署前预检查（只读）=====\033[0m\n"
printf "候选工作空间：%s\n" "$BASE"

# ---------- 1. 系统与账户 ----------
sec "1) 系统与账户"
ME="$(id -un)"
if [[ "$ME" == "user" ]]; then ok "运行账户" "user（与本工程 unit 的 User=user 一致）"
else warn "运行账户" "${ME}（unit 写死 User=user；非 user 部署需同步改 unit）"; fi

if [[ -r /etc/os-release ]]; then
    . /etc/os-release
    case "${VERSION_ID:-}" in
        20.04) ok "操作系统" "${PRETTY_NAME}" ;;
        *)     warn "操作系统" "${PRETTY_NAME}（本工程在 Ubuntu 20.04 验证；其他版本一般可用）" ;;
    esac
else warn "操作系统" "读不到 /etc/os-release"; fi
ok "架构" "$(uname -m)"

# ---------- 2. 运行时依赖 ----------
sec "2) 运行时依赖"
if command -v python3 >/dev/null 2>&1; then
    PYV="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)"
    python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,6) else 1)' 2>/dev/null \
        && ok "python3" "$PYV（零第三方依赖，够用）" \
        || bad "python3" "$PYV 低于 3.6"
else bad "python3" "未安装（apt install python3）"; fi

if command -v ffmpeg >/dev/null 2>&1; then
    ok "ffmpeg" "$(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3)"
else bad "ffmpeg" "未安装（apt install ffmpeg）——抽帧与抓帧都依赖它"; fi

for c in tar sed find awk; do
    command -v "$c" >/dev/null 2>&1 || warn "基础命令" "缺 $c"
done

# ---------- 3. 资源 ----------
sec "3) 磁盘与内存"
AVAIL_KB="$(df -Pk "$(dirname "$BASE")" 2>/dev/null | awk 'NR==2{print $4}')"
if [[ -n "${AVAIL_KB:-}" ]]; then
    AVAIL_GB=$(( AVAIL_KB / 1048576 ))
    if   [[ $AVAIL_GB -ge 5 ]]; then ok "可用磁盘" "${AVAIL_GB} GB（≥5 GB）"
    elif [[ $AVAIL_GB -ge 1 ]]; then warn "可用磁盘" "${AVAIL_GB} GB（建议 ≥5 GB：raw/ + results/ + saved/）"
    else bad "可用磁盘" "${AVAIL_GB} GB，空间不足"; fi
else warn "可用磁盘" "无法读取 $(dirname "$BASE") 所在分区"; fi

MEM_MB="$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo 2>/dev/null)"
if [[ -n "${MEM_MB:-}" ]]; then
    [[ $MEM_MB -ge 512 ]] && ok "可用内存" "${MEM_MB} MB" || warn "可用内存" "${MEM_MB} MB（偏低）"
fi

# ---------- 4. 目标路径 ----------
sec '4) 目标路径（BASE 必须是「含 src/m20_ai_detect 的那一层」）'
if [[ -z "$BASE" || "$BASE" == "/" ]]; then
    bad "路径合法性" "不能为空或根目录"
else
    if [[ -d "$BASE" ]]; then
        if [[ -f "$BASE/src/m20_ai_detect/__init__.py" ]]; then
            ok "路径内容" "已是本工程（升级安装）"
        elif [[ -z "$(ls -A "$BASE" 2>/dev/null)" ]]; then
            ok "路径内容" "空目录（首次安装）"
        else
            warn "路径内容" "非空且不是本项目（$(ls -A "$BASE" 2>/dev/null | head -3 | tr '\n' ' ')…）——确认不覆盖别人的东西"
        fi
        [[ -w "$BASE" ]] && ok "目录可写" "user 可写" || bad "目录可写" "$BASE 不可写（install.sh 以 user 同步）"
    else
        PAR="$(dirname "$BASE")"
        if [[ -d "$PAR" && -w "$PAR" ]]; then
            ok "路径内容" "不存在，但父目录可写（将新建）"
        else
            bad "路径内容" "$BASE 不存在且父目录不可写（$PAR）"
        fi
    fi

    FSTYPE="$(stat -f -c %T "$BASE" 2>/dev/null || stat -f -c %T "$(dirname "$BASE")" 2>/dev/null)"
    case "$FSTYPE" in
        ext2/ext3|ext4|xfs|btrfs|overlay|overlayfs|tmpfs)
            [[ "$FSTYPE" == "tmpfs" ]] && warn "文件系统" "tmpfs（重启即丢，不要用）" || ok "文件系统" "$FSTYPE" ;;
        nfs*|cifs|smb*|vfat|msdos|fuseblk)
            bad "文件系统" "$FSTYPE（丢权限位/不支持 POSIX，必须换本地盘）" ;;
        "") warn "文件系统" "无法识别" ;;
        *)  warn "文件系统" "$FSTYPE（未验证，建议 ext4）" ;;
    esac

    case "$BASE" in
        /tmp/*|/var/tmp/*) warn "路径位置" "$BASE 在临时目录，重启会丢" ;;
        /opt/robot/*)      warn "路径位置" "在厂商目录下，固件/脚本升级可能被覆盖" ;;
        /root/*)           bad "路径位置" "root 家目录，user 无法维护" ;;
        *" "*)             warn "路径位置" "含空格，unit 与 shell 需额外转义" ;;
        *)                 ok "路径位置" "$BASE" ;;
    esac

    UNIT=/etc/systemd/system/m20-ai-detect.service
    if [[ -f "$UNIT" ]]; then
        UD="$(sed -n 's/^WorkingDirectory=//p' "$UNIT" | head -1)"
        if [[ "$UD" == "$BASE" ]]; then ok "与 unit 一致" "$UD"
        else warn "与 unit 一致" "unit 指向 $UD，候选是 $BASE（换路径需改 unit 4 处，见手册 §1.3）"; fi
    else
        ok "与 unit 一致" "尚未安装 unit（首次部署，bootstrap.sh 会装）"
    fi
fi

# ---------- 5. 既有部署与端口 ----------
sec "5) 既有部署与冲突"
if systemctl cat m20-ai-detect.service >/dev/null 2>&1; then
    ST="$(systemctl is-active m20-ai-detect 2>/dev/null || true)"
    [[ "$ST" == "active" ]] && warn "已有采样器" "active（部署会重启它；确认当前无关键任务）" \
                            || ok "已有采样器" "${ST:-inactive}（将安装并启动）"
else ok "已有采样器" "未安装（首次部署）"; fi

if command -v ss >/dev/null 2>&1; then
    if ss -ltnp 2>/dev/null | grep -qE ':(5050)\b'; then
        OWNER="$(ss -ltnp 2>/dev/null | grep -E ':(5050)\b' | head -1 | sed -n 's/.*users:((\"\([^\"]*\)\".*/\1/p')"
        if echo "$OWNER" | grep -qiE 'python|webconsole'; then
            ok "控制台端口" "5050 已被本工程控制台占用（说明控制台在跑，非冲突）"
        else
            warn "控制台端口" "5050 被占用（$OWNER）——改 m20-ai-console.env 的 M20AIC_PORT"
        fi
    else
        ok "控制台端口" "5050 空闲"
    fi
else warn "控制台端口" "无 ss 命令，跳过"; fi

for u in /usr/local/sbin/m20-ai-console-helper /etc/sudoers.d/m20-ai-console; do
    [[ -e "$u" ]] && ok "受控提权" "$u 已存在" || warn "受控提权" "$u 缺失（console-bootstrap.sh 会装）"
done

# ---------- 6. 网络与上游 ----------
sec "6) 网络与上游（--skip-network 可跳过）"
if [[ "$SKIP_NET" == "1" ]]; then
    warn "网络检查" "已跳过（--skip-network）"
else
    # 从 .env 读默认值（有就读，没有用内置默认）
    if [[ -f "$BASE/m20-ai-detect.env" ]]; then
        [[ -z "$SRC_F" ]] && SRC_F="$(sed -n 's/^M20AI_SRC_F=//p' "$BASE/m20-ai-detect.env" | head -1)"
        [[ -z "$AI_BASE" ]] && AI_BASE="$(sed -n 's/^M20AI_AI_BASE=//p' "$BASE/m20-ai-detect.env" | head -1)"
    fi
    [[ -z "$SRC_F" ]] && SRC_F="rtsp://10.21.31.103:8554/video1"
    [[ -z "$AI_BASE" ]] && AI_BASE="http://jsxy.aihyzh.com:30881"

    if command -v ffmpeg >/dev/null 2>&1; then
        # ⚠️ 必须 -nostdin + stdin 指向 /dev/null：否则在终端里跑时 ffmpeg 会进入
        # 交互命令模式（"Enter command: <target>|all ..."），一直等输入直到被 timeout 杀掉，
        # 导致"明明能抓到帧却判失败"（2026-10-18 实测踩到）。
        probe_cam() {
            timeout 15 ffmpeg -nostdin -loglevel error -hide_banner -fflags nobuffer -flags low_delay \
                -rtsp_transport tcp -i "$1" -frames:v 1 -f null - </dev/null >/dev/null 2>&1
        }
        cam_ok=0; cam_try=0; cam_rc=0
        for cam_try in 1 2 3; do
            probe_cam "$SRC_F"
            cam_rc=$?                 # 注意：必须在 if 之外取 $?，否则拿到的是 if 语句的退出码
            if [[ "$cam_rc" -eq 0 ]]; then cam_ok=1; break; fi
            sleep 1
        done
        if [[ "$cam_ok" == "1" ]]; then
            ok "相机源" "可达（第 $cam_try 次取到 1 帧）：$SRC_F"
        else
            case "$cam_rc" in
                124) why="12s 超时、未取到帧" ;;
                *)   why="连接或解码失败（rc=$cam_rc）" ;;
            esac
            bad "相机源" "$SRC_F 连续 3 次失败：$why
     查：AOS MediaMTX 是否在推流 / 相机供电（DevEnable.Video）/ 是否同网段
     若只是偶发抖动，重跑一次 preflight 即可"
        fi
    fi

    if getent hosts "$(echo "$AI_BASE" | sed -E 's#https?://##; s#[:/].*##')" >/dev/null 2>&1; then
        ok "DNS 解析" "ok"
    else
        bad "DNS 解析" "失败（GOS 需经 AOS 出网，见 ADR-003）"
    fi

    CODE="$(curl -s -m 6 -o /dev/null -w '%{http_code}' "$AI_BASE" 2>/dev/null || echo 000)"
    if [[ "$CODE" =~ ^[23] ]]; then ok "AI 服务" "HTTP $CODE  $AI_BASE"
    else bad "AI 服务" "HTTP $CODE  $AI_BASE（服务不可用时采集会空转+积压）"; fi
fi

# ---------- 7. 提权 ----------
sec "7) 提权可用性"
# 用 sudo -l 探测白名单（直接执行 helper 会因参数非法返回非 0，误判成"没权限"）
if sudo -n -l /usr/local/sbin/m20-ai-console-helper >/dev/null 2>&1; then
    ok "受控提权" "helper 白名单可用（部署脚本可自动重启服务）"
elif sudo -n true 2>/dev/null; then
    ok "受控提权" "全权免密 sudo 可用"
else
    warn "受控提权" "helper/sudo 均不可免密（首次部署需手工输口令；GOS 口令为半角单引号 '）"
fi

# ---------- 结论 ----------
printf "\n\033[1m===== 结论 =====\033[0m\n"
printf "  PASS %d ｜ WARN %d ｜ FAIL %d\n" "$PASS" "$WARN" "$FAIL"
if [[ $FAIL -gt 0 ]]; then
    printf "  \033[31m✗ 不建议现在部署：先修上面的 FAIL 项。\033[0m\n"
    exit 1
elif [[ $WARN -gt 0 && "$STRICT" == "1" ]]; then
    printf "  \033[33m⚠ --strict：存在 WARN，按不通过处理。\033[0m\n"
    exit 1
else
    printf "  \033[32m✓ 可以部署。\033[0m 下一步：\n"
    printf "     模式 A（开发机推）：HOST=<别名> NO_RESTART=1 ./deploy/install.sh\n"
    printf "     模式 B（就地覆盖）：bash deploy/install-local.sh [--from <dir|tar.gz>]\n"
    printf "     首次装机随后跑：bash deploy/bootstrap.sh && bash deploy/console-bootstrap.sh\n"
fi
