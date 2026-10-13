#!/bin/bash
# USB摄像头自适应推流脚本
# 功能：
#   1. 根据摄像头型号自动匹配分辨率和编码参数（可扩展多型号）
#   2. 每路推流独立监控，断联自动重连（指数退避）
#   3. 通过USB路径绑定设备，自动处理设备编号漂移
#   4. 两路推流完全独立，一路故障不影响另一路

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_TAG="[push_video]"
MAX_RETRY=0              # 最大重试次数，0=无限重试
RETRY_BASE_DELAY=2       # 基础重试延迟（秒）
RETRY_MAX_DELAY=30       # 最大重试延迟（秒）
HEALTH_CHECK_INTERVAL=3  # 健康检查间隔（秒）
STABLE_THRESHOLD=5       # 连续稳定N次后重置重试计数

# 日志配置
LOG_TO_FILE=0
LOG_FILE="$HOME/push_video.log"
LOG_FILE=$(eval echo "$LOG_FILE")

# 全局变量：记录两路设备的USB路径（用于漂移检测）
USB_PATH1=""
USB_PATH2=""

# ============================================================
# 日志系统
# ============================================================

_log_write() {
    local msg="$*"
    if [ "$LOG_TO_FILE" -eq 1 ]; then
        echo "$msg" >> "$LOG_FILE"
    else
        echo "$msg" >&2
    fi
}

log_info()         { _log_write "$(date '+%Y-%m-%d %H:%M:%S') $LOG_TAG [INFO]  $*"; }
log_error()        { _log_write "$(date '+%Y-%m-%d %H:%M:%S') $LOG_TAG [ERROR] $*"; }
log_stream()       { _log_write "$(date '+%Y-%m-%d %H:%M:%S') $LOG_TAG [$1] [INFO]  $*"; }
log_stream_error() { _log_write "$(date '+%Y-%m-%d %H:%M:%S') $LOG_TAG [$1] [ERROR] $*"; }

# ============================================================
# 设备型号配置（在此处添加新型号，易于扩展）
# ============================================================
# 每个型号定义：
#   detect_pattern  - lsusb 匹配关键字
#   profile_name    - 型号名称（用于日志）
#   width/height    - 分辨率
#   fps             - 帧率
#   encoder_params  - 编码器参数（GStreamer element properties）
#   cpu_affinity_v1 - video1 的CPU亲和性
#   cpu_affinity_v2 - video2 的CPU亲和性
#
# 示例：添加新型号只需在 detect_device_profile() 中增加一个分支即可
# ============================================================

# 默认配置（未识别设备使用此配置）
DEFAULT_WIDTH=1280
DEFAULT_HEIGHT=720
DEFAULT_FPS=30
DEFAULT_ENCODER_PARAMS="rc-mode=0 bps=1800000 bps-max=2000000 qp-min=12 qp-max=45"
DEFAULT_AFFINITY_V1="4,5"
DEFAULT_AFFINITY_V2="6,7"

# 检测设备型号，设置全局变量
# 参数: $1 = 可选的指定设备（如 /dev/video0），不指定则通过lsusb全局检测
# 结果写入全局变量: DEV_WIDTH, DEV_HEIGHT, DEV_FPS, DEV_ENCODER_PARAMS, DEV_AFFINITY_V1, DEV_AFFINITY_V2, DEV_PROFILE_NAME
detect_device_profile() {
    local specific_dev="${1:-}"
    local matched_profile=""

    if [ -n "$specific_dev" ] && command -v v4l2-ctl >/dev/null 2>&1; then
        # 通过v4l2-ctl获取设备名称进行精确匹配
        local dev_name
        dev_name=$(v4l2-ctl --device="$specific_dev" --info 2>/dev/null | grep -i "Card name" | sed 's/.*: //')
        log_info "设备名称: $dev_name ($specific_dev)"

        case "$dev_name" in
            *SM_USB_107X*|*SM107X*)
                matched_profile="SM_USB_107X"
                ;;
            # ========== 在此添加新型号 ==========
            # *SomeNewModel*)
            #     matched_profile="SomeNewModel"
            #     ;;
            *)
                matched_profile=""
                ;;
        esac
    fi

    # 如果未通过设备名称匹配到，回退到lsusb全局检测
    if [ -z "$matched_profile" ]; then
        local lsusb_output
        lsusb_output=$(lsusb 2>/dev/null)

        if echo "$lsusb_output" | grep -q "SM_USB_107X"; then
            matched_profile="SM_USB_107X"
        fi
        # ========== 在此添加新型号的lsusb匹配 ==========
        # if echo "$lsusb_output" | grep -q "SomeNewModel"; then
        #     matched_profile="SomeNewModel"
        # fi
    fi

    # 根据匹配结果设置参数
    case "$matched_profile" in
        SM_USB_107X)
            DEV_PROFILE_NAME="SM_USB_107X"
            DEV_WIDTH=800
            DEV_HEIGHT=600
            DEV_FPS=30
            DEV_ENCODER_PARAMS="rc-mode=1 bps=2000000 bps-max=2500000 gop=30 qp-min=12 qp-max=45 header-mode=each-idr"
            DEV_AFFINITY_V1="4,5"
            DEV_AFFINITY_V2="6,7"
            ;;
        # ========== 在此添加新型号的配置 ==========
        # SomeNewModel)
        #     DEV_PROFILE_NAME="SomeNewModel"
        #     DEV_WIDTH=1920
        #     DEV_HEIGHT=1080
        #     DEV_FPS=30
        #     DEV_ENCODER_PARAMS="rc-mode=1 bps=4000000"
        #     DEV_AFFINITY_V1="4,5"
        #     DEV_AFFINITY_V2="6,7"
        #     ;;
        *)
            DEV_PROFILE_NAME="Default(未知型号)"
            DEV_WIDTH=$DEFAULT_WIDTH
            DEV_HEIGHT=$DEFAULT_HEIGHT
            DEV_FPS=$DEFAULT_FPS
            DEV_ENCODER_PARAMS="$DEFAULT_ENCODER_PARAMS"
            DEV_AFFINITY_V1="$DEFAULT_AFFINITY_V1"
            DEV_AFFINITY_V2="$DEFAULT_AFFINITY_V2"
            ;;
    esac

    log_info "设备型号: $DEV_PROFILE_NAME, 分辨率: ${DEV_WIDTH}x${DEV_HEIGHT}@${DEV_FPS}fps"
}

# ============================================================
# 设备探测
# ============================================================

# 获取当前可用的v4l2视频采集设备列表（排除metadata设备）
get_available_devices() {
    local devices=()
    for dev in /dev/video*; do
        [ -e "$dev" ] || continue
        if command -v v4l2-ctl >/dev/null 2>&1; then
            # v4l2-ctl可用：通过list-formats-ext判断是否为真正的采集设备
            if v4l2-ctl --device="$dev" --list-formats-ext 2>/dev/null | grep -q "\["; then
                devices+=("$dev")
            fi
        else
            # 回退方案：通过sysfs设备名称过滤
            local devname
            devname=$(basename "$dev")
            local name_attr
            name_attr=$(cat "/sys/class/video4linux/$devname/name" 2>/dev/null)
            if echo "$name_attr" | grep -qiE "video|capture"; then
                if ! echo "$name_attr" | grep -qi "metadata"; then
                    devices+=("$dev")
                fi
            fi
        fi
    done
    echo "${devices[@]}"
}

# 获取设备对应的USB路径（稳定的硬件标识符）
get_usb_path() {
    local dev="$1"
    udevadm info --query=path --name="$dev" 2>/dev/null
}

# 根据USB路径查找当前对应的/dev/videoN（用于漂移检测）
find_device_by_usb_path() {
    local target_usb_path="$1"
    local devs
    devs=$(get_available_devices)

    for dev in $devs; do
        local usb_path
        usb_path=$(get_usb_path "$dev")
        if [ -n "$usb_path" ] && [ "$usb_path" = "$target_usb_path" ]; then
            echo "$dev"
            return 0
        fi
    done
    return 1
}

# 根据设备名称（v4l2设备名）查找设备
# 用于USB路径漂移后的回退查找（设备换了USB口，路径变了但设备名不变）
find_device_by_name() {
    local target_name="$1"
    local devs
    devs=$(get_available_devices)

    for dev in $devs; do
        local devname
        devname=$(basename "$dev")
        local name_attr
        name_attr=$(cat "/sys/class/video4linux/$devname/name" 2>/dev/null)
        if [ "$name_attr" = "$target_name" ]; then
            echo "$dev"
            return 0
        fi
    done
    return 1
}

# 获取设备的v4l2设备名称（用于回退匹配）
get_v4l2_device_name() {
    local dev="$1"
    local devname
    devname=$(basename "$dev")
    cat "/sys/class/video4linux/$devname/name" 2>/dev/null
}

# 等待指定USB路径的设备上线
# 参数: $1=usb路径(可为空表示任意设备) $2=流标识 $3=已知设备名(可选,用于回退匹配)
# 输出: stdout返回/dev/videoN路径
# 注意: 日志输出到stderr避免污染stdout
wait_for_usb_device() {
    local target_usb_path="$1"
    local stream_tag="$2"
    local known_device_name="$3"  # 可选：上次连接时的v4l2设备名
    local waited=0
    local usb_fallback_after=15  # USB路径搜索超时后启用设备名回退

    while true; do
        if [ -n "$target_usb_path" ]; then
            # 优先通过USB路径精确匹配
            local dev
            dev=$(find_device_by_usb_path "$target_usb_path")
            if [ -n "$dev" ]; then
                echo "$(date '+%Y-%m-%d %H:%M:%S') $LOG_TAG [$stream_tag] [INFO]  USB设备已上线: $dev" >&2
                echo "$dev"
                return 0
            fi

            # 超时后回退：通过设备名查找（处理USB路径漂移）
            if [ "$waited" -ge "$usb_fallback_after" ] && [ -n "$known_device_name" ]; then
                dev=$(find_device_by_name "$known_device_name")
                if [ -n "$dev" ]; then
                    local new_usb_path
                    new_usb_path=$(get_usb_path "$dev")
                    echo "$(date '+%Y-%m-%d %H:%M:%S') $LOG_TAG [$stream_tag] [WARN]  USB路径漂移检测! 设备 $known_device_name 从 $target_usb_path 迁移到 $new_usb_path" >&2
                    echo "$dev"
                    return 0
                fi
            fi
        else
            local devs
            devs=$(get_available_devices)
            local devs_arr=($devs)
            if [ ${#devs_arr[@]} -gt 0 ]; then
                echo "$(date '+%Y-%m-%d %H:%M:%S') $LOG_TAG [$stream_tag] [INFO]  检测到可用设备: ${devs_arr[0]}" >&2
                echo "${devs_arr[0]}"
                return 0
            fi
        fi

        sleep 1
        waited=$((waited + 1))
        if [ $((waited % 10)) -eq 0 ]; then
            if [ -n "$target_usb_path" ]; then
                echo "$(date '+%Y-%m-%d %H:%M:%S') $LOG_TAG [$stream_tag] [INFO]  等待USB设备上线... (已等待 ${waited}s)" >&2
            else
                echo "$(date '+%Y-%m-%d %H:%M:%S') $LOG_TAG [$stream_tag] [INFO]  等待摄像头设备... (已等待 ${waited}s)" >&2
            fi
        fi
    done
}

# ============================================================
# 设备初始化分配
# ============================================================

init_device_assignment() {
    log_info "等待摄像头设备上线..."
    local devs
    devs=$(get_available_devices)
    local devs_arr=($devs)
    local count=${#devs_arr[@]}

    if [ "$count" -ge 1 ]; then
        USB_PATH1=$(get_usb_path "${devs_arr[0]}")
        log_info "设备分配: ${devs_arr[0]} -> video1 (USB路径: $USB_PATH1)"
    else
        log_info "video1: 暂无可用设备，将等待设备上线"
        USB_PATH1=""
    fi

    if [ "$count" -ge 2 ]; then
        USB_PATH2=$(get_usb_path "${devs_arr[1]}")
        log_info "设备分配: ${devs_arr[1]} -> video2 (USB路径: $USB_PATH2)"
    else
        log_info "video2: 暂无可用设备，将等待设备上线"
        USB_PATH2=""
    fi
}

# ============================================================
# Pipeline 构建
# ============================================================

# 根据设备型号配置构建GStreamer pipeline
# 参数: $1=设备路径 $2=RTSP流名称(video1/video2) $3=CPU亲和性
# 注意：不使用sudo，因为脚本本身以root运行，避免sudo包装导致PID追踪失败
build_pipeline() {
    local device="$1"
    local stream_name="$2"
    local cpu_affinity="$3"

    echo "taskset -c $cpu_affinity gst-launch-1.0 v4l2src device=$device ! image/jpeg, width=${DEV_WIDTH}, height=${DEV_HEIGHT}, framerate=${DEV_FPS}/1 ! jpegdec ! videoconvert ! video/x-raw,format=I420 ! mpph264enc $DEV_ENCODER_PARAMS ! h264parse config-interval=-1 ! rtspclientsink location=rtsp://127.0.0.1:8554/$stream_name latency=10"
}

# ============================================================
# 独立流监控（每路推流一个独立后台进程）
# ============================================================

# 单路推流的独立管理函数（在子shell中运行）
# 参数: $1=stream_name $2=usb_path $3=cpu_affinity
# 注意: 设备型号参数通过全局变量 DEV_* 传入（子shell会继承）
stream_monitor() {
    local stream_name="$1"
    local usb_path="$2"
    local cpu_affinity="$3"
    local retry_count=0
    local gst_pid=""
    local current_dev=""        # 当前推流使用的设备路径
    local known_device_name=""  # 记录设备名称，用于漂移回退查找

    # 清理当前推流进程（杀死整个进程树，包括gst-launch子进程）
    _kill_gst() {
        if [ -n "$gst_pid" ]; then
            log_stream "$stream_name" "清理推流进程 (leader PID=$gst_pid)"

            # 1. 先找到所有gst-launch子进程（在杀leader之前）
            local child_pids
            child_pids=$(pgrep -P "$gst_pid" 2>/dev/null)

            # 2. 终止leader进程
            if kill -0 "$gst_pid" 2>/dev/null; then
                kill "$gst_pid" 2>/dev/null
                local wc=0
                while kill -0 "$gst_pid" 2>/dev/null && [ "$wc" -lt 2 ]; do
                    sleep 1
                    wc=$((wc + 1))
                done
                if kill -0 "$gst_pid" 2>/dev/null; then
                    kill -9 "$gst_pid" 2>/dev/null
                    sleep 1
                fi
                wait "$gst_pid" 2>/dev/null
            fi

            # 3. 确保子进程也被杀死（防止孤儿进程占用设备）
            for cpid in $child_pids; do
                if kill -0 "$cpid" 2>/dev/null; then
                    log_stream "$stream_name" "终止子进程 PID=$cpid"
                    kill "$cpid" 2>/dev/null
                fi
            done
            sleep 1
            # 4. 强制杀死残留子进程
            for cpid in $child_pids; do
                if kill -0 "$cpid" 2>/dev/null; then
                    kill -9 "$cpid" 2>/dev/null
                fi
            done

            # 5. 最终清理：杀死本流关联的所有gst-launch进程（按设备匹配）
            if [ -n "$current_dev" ]; then
                local leftover
                leftover=$(pgrep -f "gst-launch.*device=$current_dev" 2>/dev/null)
                for pid in $leftover; do
                    log_stream "$stream_name" "清理残留进程 PID=$pid"
                    kill -9 "$pid" 2>/dev/null
                done
            fi

            gst_pid=""
            current_dev=""
        fi
    }

    # 检查推流进程树是否真正存活（不只是leader，还要检查gst-launch实际进程）
    _is_stream_alive() {
        [ -n "$gst_pid" ] || return 1
        kill -0 "$gst_pid" 2>/dev/null || return 1
        # 额外检查：是否有gst-launch子进程在运行
        pgrep -P "$gst_pid" "gst-launch" >/dev/null 2>&1 && return 0
        # 如果没有子进程但leader还在，也可能是直接运行模式（无taskset包装时）
        # 此时leader本身就是gst-launch
        local cmdline
        cmdline=$(cat /proc/$gst_pid/cmdline 2>/dev/null | tr '\0' ' ')
        echo "$cmdline" | grep -q "gst-launch" && return 0
        return 1
    }

    # 注册退出清理
    trap '_kill_gst; exit 0' TERM INT

    log_stream "$stream_name" "监控进程启动 (USB路径: ${usb_path:-未绑定}, 型号: $DEV_PROFILE_NAME, 分辨率: ${DEV_WIDTH}x${DEV_HEIGHT})"

    while true; do
        # 1. 等待设备上线（USB路径精确匹配 + 设备名回退，自动处理漂移）
        log_stream "$stream_name" "等待设备..."
        local dev
        dev=$(wait_for_usb_device "$usb_path" "$stream_name" "$known_device_name")

        # 2. 记录设备名称（用于下次重连时的回退查找）
        known_device_name=$(get_v4l2_device_name "$dev")
        log_stream "$stream_name" "设备名称: ${known_device_name:-未知}"

        # 3. 检查USB路径漂移并更新绑定
        local current_dev_path
        current_dev_path=$(get_usb_path "$dev")
        if [ -n "$usb_path" ] && [ -n "$current_dev_path" ] && [ "$usb_path" != "$current_dev_path" ]; then
            log_stream "$stream_name" "检测到USB路径漂移! 原: $usb_path -> 新: $current_dev_path"
            log_stream "$stream_name" "更新绑定路径"
            usb_path="$current_dev_path"
        elif [ -z "$usb_path" ] && [ -n "$current_dev_path" ]; then
            log_stream "$stream_name" "首次绑定USB路径: $current_dev_path"
            usb_path="$current_dev_path"
        fi

        # 4. 清理该设备上的残留gst-launch进程（防止旧进程占用设备）
        local leftover
        leftover=$(pgrep -f "gst-launch.*device=$dev" 2>/dev/null)
        if [ -n "$leftover" ]; then
            log_stream "$stream_name" "发现设备 $dev 上有残留进程: $leftover，清理中..."
            for pid in $leftover; do
                kill -9 "$pid" 2>/dev/null
            done
            sleep 1
        fi

        # 5. 构建并启动pipeline
        current_dev="$dev"
        local pipeline
        pipeline=$(build_pipeline "$dev" "$stream_name" "$cpu_affinity")
        log_stream "$stream_name" "启动推流: device=$dev"
        eval "$pipeline" &
        gst_pid=$!
        log_stream "$stream_name" "推流已启动 (PID=$gst_pid, device=$dev)"

        # 6. 健康检查循环：监控推流进程 + 设备存在性
        local stable_count=0
        local dev_missing_count=0
        local DEV_MISSING_THRESHOLD=3  # 设备连续不存在N次后判定为断联

        while _is_stream_alive; do
            sleep "$HEALTH_CHECK_INTERVAL"

            # 关键检查：设备节点是否还存在
            if [ -n "$current_dev" ] && [ ! -e "$current_dev" ]; then
                dev_missing_count=$((dev_missing_count + 1))
                log_stream "$stream_name" "设备 $current_dev 已不存在! ($dev_missing_count/$DEV_MISSING_THRESHOLD)"
                if [ "$dev_missing_count" -ge "$DEV_MISSING_THRESHOLD" ]; then
                    log_stream_error "$stream_name" "设备断联确认，强制终止推流进程"
                    break
                fi
            else
                dev_missing_count=0
            fi

            stable_count=$((stable_count + 1))
            if [ "$stable_count" -eq "$STABLE_THRESHOLD" ]; then
                if [ "$retry_count" -gt 0 ]; then
                    log_stream "$stream_name" "推流运行稳定，重置重试计数"
                    retry_count=0
                fi
            fi
        done

        # 7. 进程退出或设备断联，准备重连
        _kill_gst
        retry_count=$((retry_count + 1))

        if [ "$MAX_RETRY" -gt 0 ] && [ "$retry_count" -gt "$MAX_RETRY" ]; then
            log_stream_error "$stream_name" "已达最大重试次数 ($MAX_RETRY)，停止该路推流"
            exit 1
        fi

        # 指数退避: 2s -> 4s -> 8s -> 16s -> 30s(上限)
        local delay=$((RETRY_BASE_DELAY * (2 ** (retry_count - 1))))
        if [ "$delay" -gt "$RETRY_MAX_DELAY" ]; then
            delay=$RETRY_MAX_DELAY
        fi

        log_stream "$stream_name" "推流中断，第 ${retry_count} 次重连，等待 ${delay}s..."
        sleep "$delay"
    done
}

# ============================================================
# 主逻辑
# ============================================================

log_info "========== 自适应推流服务启动 =========="

# 日志文件初始化
if [ "$LOG_TO_FILE" -eq 1 ]; then
    if touch "$LOG_FILE" 2>/dev/null; then
        log_info "日志记录模式: 文件 ($LOG_FILE)"
    else
        echo "[WARNING] 日志文件无法创建: $LOG_FILE，回退到终端打印" >&2
        LOG_TO_FILE=0
        log_info "日志记录模式: 仅终端打印（文件创建失败）"
    fi
else
    log_info "日志记录模式: 仅终端打印"
fi

sleep 3  # 初始等待设备枚举

# 初始化设备分配（记录USB路径用于漂移检测）
init_device_assignment

# 检测第一个可用设备的型号，设置全局 DEV_* 变量
FIRST_DEV=""
if [ -n "$USB_PATH1" ]; then
    FIRST_DEV=$(find_device_by_usb_path "$USB_PATH1")
elif [ -n "$USB_PATH2" ]; then
    FIRST_DEV=$(find_device_by_usb_path "$USB_PATH2")
fi
detect_device_profile "$FIRST_DEV"

# 启动两路独立的推流监控进程
log_info "启动独立推流监控进程..."
log_info "video1: 型号=$DEV_PROFILE_NAME, 分辨率=${DEV_WIDTH}x${DEV_HEIGHT}, CPU=$DEV_AFFINITY_V1"
log_info "video2: 型号=$DEV_PROFILE_NAME, 分辨率=${DEV_WIDTH}x${DEV_HEIGHT}, CPU=$DEV_AFFINITY_V2"

stream_monitor "video1" "$USB_PATH1" "$DEV_AFFINITY_V1" &
MONITOR_PID1=$!
log_info "video1 监控进程已启动 (PID=$MONITOR_PID1)"

stream_monitor "video2" "$USB_PATH2" "$DEV_AFFINITY_V2" &
MONITOR_PID2=$!
log_info "video2 监控进程已启动 (PID=$MONITOR_PID2)"

# 主循环：监控两个子进程，处理异常退出
cleanup() {
    log_info "收到退出信号，正在清理..."
    # 1. 通知监控进程退出（会触发各自的trap清理）
    kill $MONITOR_PID1 $MONITOR_PID2 2>/dev/null
    sleep 2
    # 2. 检查并强制杀死未退出的监控进程
    for pid in $MONITOR_PID1 $MONITOR_PID2; do
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null
        fi
    done
    wait $MONITOR_PID1 $MONITOR_PID2 2>/dev/null
    # 3. 清理所有残留的gst-launch进程
    local pids
    pids=$(pgrep gst-launch 2>/dev/null)
    if [ -n "$pids" ]; then
        log_info "停止残留推流进程: $pids"
        kill $pids 2>/dev/null
        sleep 1
        # 强制杀死未退出的
        pids=$(pgrep gst-launch 2>/dev/null)
        if [ -n "$pids" ]; then
            kill -9 $pids 2>/dev/null
        fi
    fi
    log_info "推流服务已停止"
    exit 0
}

trap cleanup TERM INT

while true; do
    sleep "$HEALTH_CHECK_INTERVAL"

    # 检查video1监控进程是否存活
    if ! kill -0 "$MONITOR_PID1" 2>/dev/null; then
        log_error "video1 监控进程 (PID=$MONITOR_PID1) 异常退出，重启..."
        wait $MONITOR_PID1 2>/dev/null
        stream_monitor "video1" "$USB_PATH1" "$DEV_AFFINITY_V1" &
        MONITOR_PID1=$!
        log_info "video1 监控进程已重启 (PID=$MONITOR_PID1)"
    fi

    # 检查video2监控进程是否存活
    if ! kill -0 "$MONITOR_PID2" 2>/dev/null; then
        log_error "video2 监控进程 (PID=$MONITOR_PID2) 异常退出，重启..."
        wait $MONITOR_PID2 2>/dev/null
        stream_monitor "video2" "$USB_PATH2" "$DEV_AFFINITY_V2" &
        MONITOR_PID2=$!
        log_info "video2 监控进程已重启 (PID=$MONITOR_PID2)"
    fi
done
