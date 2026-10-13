#!/bin/bash
# ROS 版本识别与方案切换 —— 一键验证脚本
#
# 用法（103 上）：
#   bash /home/test/monitor/tools/verify_ros_switch.sh
#
# 覆盖 4 项检查：
#   1. 自动识别：ros_env 独立检测（含每条信号轨迹）
#   2. 运行时生效：/api/ros 与 /api/status 的 ROS 字段
#   3. 手动切换：分别用 ros1 / ros2 覆盖自动检测，确认优先级生效
#   4. 失败回退：非法值 → 明确报错 + 回退 sniff（degraded=true）

BACKEND=/home/test/monitor/backend
PY=/home/test/monitor/.venv/bin/python
API=http://127.0.0.1:8000

echo "=============================================="
echo " 1) 自动识别（独立检测，含信号轨迹）"
echo "=============================================="
cd "$BACKEND" || exit 1
"$PY" ros_env.py --verbose
echo "退出码=$? （0=识别成功，1=未能确定）"
echo

echo "=============================================="
echo " 2) 运行时生效（/api/ros）"
echo "=============================================="
curl -s --max-time 6 "$API/api/ros" \
  | "$PY" -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception as exc:
    print('无法解析 /api/ros（监控服务未启动？）:', exc); sys.exit()
print('version   :', d['version'])
print('source    :', d['source'], '(manual-cli/manual-env/auto/fallback)')
print('degraded  :', d['degraded'])
print('error     :', d['error'])
print('生效数据源:', d['effective_data_source_mode'])
if d.get('profile'):
    print('方案      :', d['profile']['label'])
    print('  话题发现:', ' '.join(d['profile']['topic_list_cmd']))
    print('  节点发现:', ' '.join(d['profile']['node_list_cmd']))
    print('  进程采集:', ','.join(d['profile']['process_patterns']))
"
echo
echo "--- /api/status 的 ROS 字段 ---"
curl -s --max-time 6 "$API/api/status" \
  | "$PY" -c "
import sys, json
d = json.load(sys.stdin)
for k in ('connected','udp_mode','ros_version','ros_source','ros_degraded','ros_error'):
    print('  %-14s %s' % (k, d.get(k)))
"
echo

echo "=============================================="
echo " 3) 手动切换优先级（应覆盖自动检测）"
echo "=============================================="
for v in ros1 ros2; do
  echo "--- LITE3_ROS_VERSION=$v ---"
  LITE3_ROS_VERSION=$v "$PY" -c "
import ros_switch as s
p = s.resolve()
print('  version=%s source=%s degraded=%s 生效数据源=%s' % (
    p.version.value, p.source, p.degraded, p.effective_data_source_mode))
print('  方案=%s' % (p.profile.label if p.profile else '(无)'))
"
done
echo

echo "=============================================="
echo " 4) 失败回退（非法值应报错且 sniff 兜底）"
echo "=============================================="
LITE3_ROS_VERSION=bogus "$PY" -c "
import ros_switch as s
p = s.resolve()
print('  version=%s source=%s degraded=%s 生效数据源=%s' % (
    p.version.value, p.source, p.degraded, p.effective_data_source_mode))
print('  error=%s' % p.error)
assert p.degraded and p.effective_data_source_mode == 'sniff', '回退策略不符合预期'
print('  -> 已按预期回退到安全默认 sniff')
"
echo

echo "验证结束。"
