#!/bin/bash
# 控制权归属（多操作员互斥）真机验收脚本。
# 用法（在 M20 上）：bash verify_ownership.sh
# 模拟两个终端（A / B）争抢控制权，逐条核对后端行为。
# ⚠️ 只在本地安全闸层面操作，不会让机器人运动。

API="http://127.0.0.1:8080/api/v1/control"

post() {
    curl -s -m 8 -X POST "$1" -H "Content-Type: application/json" -d "$2"
    echo
}
state() {
    curl -s -m 8 "$API/status" \
      | python3 -c 'import sys,json;d=json.load(sys.stdin)["control"];print("     enabled=%s  owner=%s"%(d["enabled"],d["owner"]))'
}

echo "① 初始状态（应为 enabled=False / held=False）"
state

echo
echo "② 终端A 申请控制权（应 ok）"
post "$API/acquire" '{"session_id":"aaa11111","label":"操作员A","confirmed":true}'

echo
echo "③ 终端B 申请控制权（应 CONTROL_HELD + 占用者信息）"
post "$API/acquire" '{"session_id":"bbb22222","label":"操作员B","confirmed":true}'

echo
echo "④ 终端B 下发 stand_up（应 NOT_OWNER / 409）"
post "$API/command" '{"name":"stand_up","params":{},"confirmed":true,"session_id":"bbb22222"}'

echo
echo "⑤ 终端A 下发 stand_up（不应是 NOT_OWNER）"
post "$API/command" '{"name":"stand_up","params":{},"confirmed":true,"session_id":"aaa11111"}'

echo
echo "⑥ 非 owner 续约（应 lease_remaining=0）"
post "$API/lease" '{"session_id":"bbb22222"}'

echo
echo "⑦ owner 续约（应 lease_remaining>0）"
post "$API/lease" '{"session_id":"aaa11111"}'

echo
echo "⑧ 当前状态（应为 A 持有）"
state

echo
echo "⑨ 终端B 强制接管（应 ok，owner 变 B）"
post "$API/acquire" '{"session_id":"bbb22222","label":"操作员B","force":true,"confirmed":true}'
state

echo
echo "⑩ 终端A 尝试释放（此时已不是 owner，应 NOT_OWNER）"
post "$API/release" '{"session_id":"aaa11111"}'

echo
echo "⑪ 终端B 释放（应 ok，回到 L0）"
post "$API/release" '{"session_id":"bbb22222"}'
state

echo
echo "验收结束。若⑪后 enabled=False 且 held=False，说明互斥链路正常。"
