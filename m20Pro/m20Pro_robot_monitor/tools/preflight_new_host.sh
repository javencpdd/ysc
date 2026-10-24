#!/usr/bin/env bash
# ============================================================================
# 新机器预检（只读）—— 在目标 M20 的 **AOS** 上跑，不改任何东西。
#
# 用途：换机部署前确认"这台车是否具备条件"，把移植文档 §1 的核对项一次跑完。
#
# 用法：
#   bash preflight_new_host.sh                          # 只做环境预检（§1–§6）
#   bash preflight_new_host.sh /home/user/m20monitor     # 额外体检安装路径（§7）
#   bash preflight_new_host.sh -h                        # 帮助
#
# 退出码：0 = 可以用；1 = 有阻塞项（红色 ❌）；黄色 ⚠️ 不阻塞。
#
# ⚠️ 全部只读。其中 basic_server md5 与厂商链路检查需要 root，会走 `sudo -S`
#    （本仓库约定 sudo 口令是半角单引号 `'`）。不想输口令就跳过那几项。
# ============================================================================
set -u

#: 本仓库逆向基准（42 条指令表对应的二进制）
BASELINE_MD5="e578e07a2039a4180885c670687e70ea"
#: 控制台的常见默认安装目录（只用于"是否已装过"的提示）
DEFAULT_DIR="/home/djw/monitor"

ok()   { printf '  \033[32m✅\033[0m %s\n' "$*"; }
no()   { printf '  \033[31m❌\033[0m %s\n' "$*"; BLOCK=$((BLOCK+1)); }
warn() { printf '  \033[33m⚠️\033[0m  %s\n' "$*"; }
BLOCK=0

# 只在需要时提权：口令默认是半角单引号 `'`，可用 M20_SUDO_PASS 覆盖
# （远程部署脚本 install_remote.sh 会以 root 调本脚本，此时 sudo 不会再问口令）
SUDO_PASS="${M20_SUDO_PASS:-}"
[ -z "$SUDO_PASS" ] && SUDO_PASS="'"
sudo_run() { printf '%s\n' "$SUDO_PASS" | sudo -S "$@" 2>/dev/null; }

echo "=============================================="
echo " M20 控制台 · 新机器预检（只读）"
echo "=============================================="

echo
echo "== 1. 系统 =="
if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release && echo "  $PRETTY_NAME"
fi
echo "  python: $(python3 -V 2>&1)"
case "$(python3 -V 2>&1)" in
    *"3.8"*) ok "Python 3.8（与本仓库兼容目标一致）" ;;
    *)       warn "非 3.8 —— 代码是 3.8 兼容写的，通常也能跑，但未在此版本验证" ;;
esac

echo
echo "== 2. basic_server 版本（最关键） =="
BS=/opt/robot/share/basic_server/bin/basic_server
if [ -f "$BS" ]; then
    MD5=$(sudo_run md5sum "$BS" | awk '{print $1}')
    if [ -z "$MD5" ]; then
        warn "读不到 md5（需要 sudo 口令）。请手动跑：sudo md5sum $BS"
    elif [ "$MD5" = "$BASELINE_MD5" ]; then
        ok "md5 一致 → 42 条指令表 / magic 结论可直接沿用"
    else
        warn "md5=$MD5 与本仓库基准 $BASELINE_MD5 不同"
        warn "  → 必须重跑逆向对比（docs/deploy-to-second-host.md §1.2），别假设兼容"
    fi
else
    no "找不到 $BS —— 这台车可能不是 M20 Pro，或固件布局不同"
fi

echo
echo "== 3. 厂商链路（控制台依赖它们，自己不实现） =="
[ -d /opt/robot/scripts/board_resources/rtsp_service ] \
    && ok "本地推流目录在（push_video.sh + mediamtx）" \
    || no "本地推流目录缺失 → 相机页永远没画面"
[ -x /opt/robot/scripts/wifi/ap_start.sh ] \
    && ok "热点重建脚本在" \
    || no "热点重建脚本缺失 → 热点面板只能读不能写"
[ -f /opt/robot/scripts/wifi/password ] \
    && ok "热点密码文件在" \
    || no "热点密码文件缺失 → 热点面板只能读不能写"
[ -f /var/opt/robot/conf/host_name ] \
    && ok "热点名文件在（$(sudo_run cat /var/opt/robot/conf/host_name 2>/dev/null || echo 读不到)）" \
    || warn "热点名文件缺失"
if [ -d /home/user/rtmp_1012 ]; then
    ok "外推中继目录在"
    if systemctl is-enabled m20video >/dev/null 2>&1; then
        ok "m20video.service 已 enable"
    else
        warn "m20video.service 未 enable（外推面板会报未安装，不影响其它功能）"
    fi
else
    warn "外推中继目录缺失（不影响其它功能）"
fi

echo
echo "== 4. 相机 =="
if command -v lsusb >/dev/null 2>&1; then
    lsusb | grep -qi SM_USB_107X && ok "USB 相机已识别（SM_USB_107X）" \
        || no "未识别到 SM_USB_107X（检查 USB 线与相机供电）"
else
    warn "无 lsusb 命令，跳过"
fi
N=$(ls /dev/video* 2>/dev/null | wc -l)
if [ "$N" -ge 2 ]; then
    ok "/dev/video* 共 $N 个"
else
    no "/dev/video* 只有 $N 个（相机未通电或未枚举，休眠中也会这样）"
fi

echo
echo "== 5. 网络 =="
ip -4 -o addr show 2>/dev/null | awk '{printf "  %-10s %s\n", $2, $4}'
if ss -lun 2>/dev/null | grep -q ':30000'; then
    ok "basic_server 30000/udp 在听"
else
    no "30000/udp 没在听 → basic_server 没起来（控制台将收不到任何状态）"
fi

echo
echo "== 6. 装机现状 =="
if [ -d "$DEFAULT_DIR" ]; then
    warn "$DEFAULT_DIR 已存在 → 这是升级场景，用 _apply.sh 而不是 install.sh"
else
    ok "$DEFAULT_DIR 不存在 → 干净，可首次安装"
fi
for h in m20-ap-ctl m20-video-ctl; do
    if [ -x "/usr/local/sbin/$h" ]; then
        ok "helper $h 已在"
    else
        warn "helper $h 未装（install.sh 第 8 步会装；也可单独跑 deploy/install_helpers.sh）"
    fi
done
for s in m20-ap-ctl m20-video-ctl; do
    [ -f "/etc/sudoers.d/$s" ] && ok "sudoers $s 在" || warn "sudoers $s 未装"
done

# ---------------------------------------------------------------- 7. 安装路径体检
# 用法：bash preflight_new_host.sh [候选安装路径]
# 不给参数就跳过本节。给参数时会告诉你"这个路径能不能用、运行用户会是谁"。
check_install_path() {
    local P="$1" owner run_user n avail_kb
    echo
    echo "== 7. 安装路径体检：$P =="

    # ---- 形态检查
    case "$P" in
        /*) ok "绝对路径" ;;
        *)  no "不是绝对路径（必须以 / 开头，否则会写进 systemd 单元的相对路径）" ;;
    esac
    # ⚠️ 必须写 `*" "*`（两侧都有 *）—— 只写 `*" "` 只能匹配**以空格结尾**的字符串，
    #    中间带空格的路径会被误判为通过（2026-10-18 自测抓到）。
    case "$P" in
        *" "*|*$'\t'*) no "含空白字符 → systemd 会把 ExecStart 拆词，服务起不来（status=203/EXEC）" ;;
        *"#"*)         no "含 # → install.sh 的 sed 用 # 作分隔符，会直接失败（单元写成空文件）" ;;
        *"&"*)         no "含 & → sed 替换串里 & 展开成旧路径，路径会错乱" ;;
        *'$'*)         no "含 \$ → 会被 shell 当变量展开，路径错乱" ;;
        *)             ok "无空白 / # / & / \$ 等破坏性字符" ;;
    esac
    case "$P" in
        /tmp/*|/var/tmp/*|/run/*|/dev/shm/*|*/../*|*/./*)
            no "位于临时目录或含 . / .. 段 → 重启会被清空 / 路径不可预测" ;;
        *)  ok "不在临时目录下（不会因重启丢失）" ;;
    esac
    case "$P" in
        *m20pro_console*)
            no "路径里带 m20pro_console —— 这看起来是**解包目录**。
       解包目录只是中转站，不该当安装目录（见文档 §3.4）" ;;
        *) : ;;
    esac

    # ---- 运行用户推断（与 install.sh 完全同逻辑）
    owner=$(basename "$(dirname "$P")")
    if [[ "$P" == /home/* ]] && id -u "$owner" >/dev/null 2>&1; then
        run_user="$owner"
        ok "运行用户 → $run_user（父目录名 $owner 是已存在用户）"
    else
        run_user="${SUDO_USER:-$(id -un)}"
        if [[ "$P" == /home/* ]]; then
            warn "父目录名 $owner 不是已存在用户 → 运行用户降级为 $run_user"
        else
            ok "运行用户 → $run_user（非 /home/*，取 sudo 调用者）"
        fi
    fi
    if [ "$run_user" = "root" ]; then
        no "运行用户会变成 root！别以 root 直接执行 install.sh（要么挂普通用户下，要么用 sudo）"
    fi

    # ---- 现状（空目录 / 升级 / 别人的目录）
    if [ -e "$P" ]; then
        if [ -d "$P" ]; then
            n=$(ls -A "$P" 2>/dev/null | wc -l)
            if [ "$n" -eq 0 ]; then
                ok "目录已存在但是空的（正合适）"
            elif [ -f "$P/backend/main.py" ] && [ -d "$P/venv" ]; then
                warn "已是一个装好的控制台（$n 项）→ 这是**升级**，用 _apply.sh 或直接重跑 install.sh"
            else
                no "目录已存在且非空（$n 项），但不是控制台 → 别拿它当安装目录，换个新的"
                echo "      （install.sh 会对 backend/ tools/ note/ 做 rsync --delete，"
                echo "        会删掉同名目录里多余的文件）"
            fi
        else
            no "路径已存在但不是目录"
        fi
    else
        ok "目录不存在（install.sh 会自动 mkdir -p）"
    fi

    # ---- 磁盘
    avail_kb=$(df -Pk "$(dirname "$P")" 2>/dev/null | awk 'NR==2{print $4}')
    if [ -n "$avail_kb" ]; then
        if [ "$avail_kb" -ge 524288 ]; then
            ok "所在分区可用 $(( avail_kb / 1024 )) MB（安装约需 50MB + HLS 增长）"
        else
            no "所在分区仅剩 $(( avail_kb / 1024 )) MB，不够（venv 就 23MB，HLS 还会涨）"
        fi
    fi

    echo
    if [ "$BLOCK" -eq 0 ]; then
        printf ' \033[32m→ 这个路径可以用。\033[0m下一步：\n'
        echo "   sudo bash /tmp/m20pro_console/deploy/install.sh $P"
        echo "   装完核对运行用户： systemctl show m20pro-console -p User --value   # 应为 $run_user"
    else
        printf ' \033[31m→ 这个路径有问题（见上面 ❌），换一个再来。\033[0m\n'
    fi
}

# 可选的安装路径体检（第 2 个参数 / 第 1 个位置参数）
CANDIDATE_PATH=""
case "${1:-}" in
    "")          ;;
    -h|--help)
        echo "用法：bash preflight_new_host.sh [候选安装路径]"
        echo "  不给路径：只做环境预检（§1–§6）"
        echo "  给路径  ：额外体检该安装路径能不能用（§7），并打印应执行的 install.sh 命令"
        exit 0 ;;
    *)           CANDIDATE_PATH="$1" ;;
esac

if [ -n "$CANDIDATE_PATH" ]; then
    check_install_path "$CANDIDATE_PATH"
else
    echo
    echo "=============================================="
    if [ "$BLOCK" -eq 0 ]; then
        printf ' \033[32m环境预检通过，可以部署。\033[0m\n'
        echo " 建议把候选安装路径也一起体检（会告诉你运行用户是谁）："
        echo "   bash $0 /home/user/m20monitor"
    else
        printf ' \033[31m环境有 %d 个阻塞项（❌），先解决再部署。\033[0m\n' "$BLOCK"
    fi
    echo " 说明：note/移植部署流程.md §3 / §9"
    echo "=============================================="
fi

[ "$BLOCK" -eq 0 ] && exit 0 || exit 1
