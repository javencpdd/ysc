#!/usr/bin/env bash
# P3 L10 时间轴预览真机验收（计划书 §5.5.1，playwright 单进程）
# 覆盖：首屏加载 / 二分吸附 / 密度带 240 槽 / 连拖 100 次只拉 1 次原图 /
#       键盘逐帧 / 删除即时更新 / 还原 / 空态 / 缩略图缓存 / 穿越拒绝。
# 依赖：pic/ 当日已有抓拍（冒烟阶段产物）；无抓拍时交互项自动 SKIP。
set -u
# 计划书 §1248：Chromium 会读 env 代理，PC 上跑必须显式清空，否则打不开 103
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
PCLI=$(command -v playwright-cli)
TOKEN=$(bash "$(dirname "$0")/get-token.sh")
URL=http://192.168.1.103:8090
JAR=/tmp/p3-l10.jar
PASS=0; FAIL=0; SKIP=0
ck() { if [ "$2" = "$3" ]; then echo "PASS  $1 = $3"; PASS=$((PASS+1)); else echo "FAIL  $1  期望 $2 实际 $3"; FAIL=$((FAIL+1)); fi; }
sk() { echo "SKIP  $1（$2）"; SKIP=$((SKIP+1)); }
ev() { "$PCLI" eval "$1" 2>/dev/null | sed -n '/^### Result$/,/^### Ran Playwright code$/p' | sed '1d;$d'; }
evs() { ev "$1" | sed 's/^"//; s/"$//; s/\\"/"/g'; }

# curl 侧会话（playwright 会话与 curl 不共享 cookie，单独登录一次）
rm -f "$JAR"
curl -s --noproxy '*' -c "$JAR" -X POST "$URL/api/auth/login" \
  -H "Content-Type: application/json" -d "{\"token\":\"$TOKEN\"}" >/dev/null

echo "===== 0. 登录（playwright）====="
"$PCLI" open "$URL" >/dev/null 2>&1
sleep 2
"$PCLI" fill e7 "$TOKEN" >/dev/null 2>&1
"$PCLI" click e8 >/dev/null 2>&1
sleep 5

echo "===== L1 首屏加载 ====="
N=$(ev "pics.items.length")
TODAY=$(ev "picsToday()")
ck "L1a 首屏日期=今天" "$TODAY" "$(ev "pics.date")"
ck "L1b 抓拍卡可见" "false" "$(ev "document.getElementById('card-pics').hidden")"
if [ "${N:-0}" -gt 0 ] 2>/dev/null; then
  echo "PASS  L1c items 已加载（$N 张）"; PASS=$((PASS+1))
else
  sk "L1c items 已加载" "当日无抓拍（冒烟未跑？）"
fi
ck "L1d 标题非占位" "true" "$(ev "/^\d\d:\d\d:\d\d\.\d\d\d$/.test(document.getElementById('pics-title').textContent)")"
ck "L1e 计数文本非空" "true" "$(ev "document.getElementById('pics-count').textContent.length>0")"
ck "L1f 默认定位到最后一张" "true" "$(ev "pics.idx===pics.items.length-1")"
ck "L1g 预览图 src 带 thumb=1" "true" "$(ev "document.getElementById('pics-full').src.indexOf('thumb=1')>=0")"

if [ "${N:-0}" -gt 0 ] 2>/dev/null; then

echo "===== L2 二分吸附 ====="
# a) 精确命中每张；b) 相邻中点 → 更近者（等距取前）；c) 首/末端点
R=$(ev "(function(){
  var bad = [];
  function expectNear(t, i){
    var s = picsSnapIndex(t);
    if (s !== i) bad.push('t=' + t + ' want ' + i + ' got ' + s);
  }
  for (var k = 0; k < pics.items.length; k++) {
    expectNear(picsTsToSlider(pics.items[k].ts_ms), k);
  }
  for (var k = 0; k + 1 < pics.items.length; k++) {
    var a = pics.items[k].ts_ms, b = pics.items[k + 1].ts_ms, mid = (a + b) / 2;
    expectNear(picsTsToSlider(mid), (b - mid) < (mid - a) ? k + 1 : k);
  }
  expectNear(0, 0);
  expectNear(86399999, pics.items.length - 1);
  return bad.length ? bad.slice(0, 3).join(';') : 'ok';
})()")
ck "L2 吸附：精确命中+中点+端点全对" "ok" "$R"

echo "===== L3 密度带 240 槽 ====="
ck "L3a 槽数 = 240" "240" "$(ev "document.querySelectorAll('#pics-density .slot').length")"
ck "L3b 有图槽与数据独立复算一致" "true" "$(ev "(function(){
  var slotMs = 86400000 / 240, want = {};
  pics.items.forEach(function(it){
    want[Math.min(239, Math.floor(picsTsToSlider(it.ts_ms) / slotMs))] = true;
  });
  var got = {};
  document.querySelectorAll('#pics-density .slot.has').forEach(function(c){ got[c.dataset.slot] = true; });
  return Object.keys(want).sort().join(',') === Object.keys(got).sort().join(',');
})()")"
ck "L3c 点击密度槽跳到该槽首帧" "true" "$(ev "(function(){
  var slots = document.querySelectorAll('#pics-density .slot.has');
  if (!slots.length) return 'no-slots';
  var cell = slots[Math.floor(slots.length / 2)];
  var lo = Number(cell.dataset.slot) * (86400000 / 240);
  var want = -1;
  for (var i = 0; i < pics.items.length; i++) {
    if (picsTsToSlider(pics.items[i].ts_ms) >= lo) { want = i; break; }
  }
  if (want < 0) return 'no-frame-in-slot';
  picsGotoIdx((want + 1) % pics.items.length, true);   // 先移开到不同索引，防假通过
  cell.click();
  return pics.idx === want;
})()")"

echo "===== L4 连拖 100 次只拉 1 次原图（150ms 防抖）====="
R=$(ev "(function(){
  performance.setResourceTimingBufferSize(4000);      // 防缓冲回绕丢早期条目
  function fullCount(){
    return performance.getEntriesByType('resource').filter(function(r){
      return r.name.indexOf('/api/pics/' + pics.date + '/') >= 0
          && r.name.indexOf('thumb=1') < 0;
    }).length;
  }
  var before = fullCount();
  var s = document.getElementById('pics-slider');
  for (var i = 0; i < 100; i++) {
    s.value = String(Math.floor(Math.random() * 86400000));
    s.dispatchEvent(new Event('input', {bubbles: true}));
  }
  var during = fullCount();
  return new Promise(function(resolve){
    setTimeout(function(){ resolve(before + '|' + during + '|' + fullCount()); }, 500);
  });
})()")
B=$(echo "$R" | cut -d'|' -f1); D=$(echo "$R" | cut -d'|' -f2); A=$(echo "$R" | cut -d'|' -f3)
if [ -n "$A" ] && [ "$A" -gt "$B" ] 2>/dev/null; then
  ck "L4a 拖动 100 次原图请求恰好 +1（防抖生效）" "1" "$((A - B))"
  if [ "$D" = "$B" ]; then echo "PASS  L4b 拖动过程中（防抖未到）不拉原图"; PASS=$((PASS+1));
  else echo "FAIL  L4b 拖动中不拉原图 期望 $B 实际 $D"; FAIL=$((FAIL+1)); fi
else
  echo "FAIL  L4 资源计时采样失败（$R）"; FAIL=$((FAIL+1))
fi

echo "===== L5 键盘逐帧 ====="
ck "L5a ArrowRight +1" "true" "$(ev "(function(){
  picsGotoIdx(Math.max(0, pics.items.length - 2), true);
  var i1 = pics.idx;
  document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true}));
  return pics.idx === i1 + 1;
})()")"
ck "L5b Shift+ArrowRight +10" "true" "$(ev "(function(){
  picsGotoIdx(0, true);
  document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', shiftKey: true, bubbles: true}));
  return pics.idx === 10;
})()")"
ck "L5c ArrowLeft -1" "true" "$(ev "(function(){
  picsGotoIdx(5, true);
  document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowLeft', bubbles: true}));
  return pics.idx === 4;
})()")"
ck "L5d 表单控件内不拦截" "true" "$(ev "(function(){
  picsGotoIdx(5, true);
  document.getElementById('pics-date').dispatchEvent(
    new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true}));
  return pics.idx === 5;
})()")"

echo "===== L6 删除 → 即时更新 ====="
CNT_BEFORE=$(ev "pics.items.length")
DEL_NAME=$(ev "pics.items[pics.idx].name")
ev "document.getElementById('pics-delete').click()" >/dev/null
sleep 1
ck "L6a 删除前有二次确认模态" "确认执行" "$(evs "document.querySelector('#modal-root .modal .actions .danger').textContent")"
ev "document.querySelector('#modal-root .modal .actions .danger').click()" >/dev/null
sleep 3
ck "L6b 删除后 items 减 1" "$((CNT_BEFORE - 1))" "$(ev "pics.items.length")"
ck "L6c 删除后该张不在 items" "false" "$(ev "pics.items.some(function(it){return it.name==='$DEL_NAME'})")"
ev "window.__t=null; fetch('/api/pics/trash').then(function(r){return r.json()}).then(function(d){window.__t=d.items.some(function(it){return it.name==='$DEL_NAME'})}); 0" >/dev/null
sleep 1
ck "L6d 回收站出现该文件" "true" "$(ev "window.__t")"

echo "===== L7 还原 ====="
ev "window.__r=null; fetch('/api/pics/trash/' + encodeURIComponent('$DEL_NAME') + '/restore', {method:'POST'}).then(function(r){return r.json()}).then(function(d){window.__r=d.ok?'ok':(d.error||'fail')}); 0" >/dev/null
sleep 1
ck "L7a 还原 API 返回 ok" "ok" "$(ev "window.__r")"
ev "picsLoad(pics.date)" >/dev/null
sleep 3
ck "L7b 重拉后 items 恢复" "$CNT_BEFORE" "$(ev "pics.items.length")"
ck "L7c 还原的那张回到 items" "true" "$(ev "pics.items.some(function(it){return it.name==='$DEL_NAME'})")"

echo "===== L8 空态 ====="
ev "picsLoad('20260101')" >/dev/null
sleep 3
ck "L8a 空态可见" "false" "$(ev "document.getElementById('pics-empty').hidden")"
ck "L8b 空态文案=当日无抓拍目录" "当日无抓拍目录" "$(evs "document.getElementById('pics-empty-text').textContent")"
ck "L8c 跳转按钮可见" "false" "$(ev "document.getElementById('pics-goto-latest').hidden")"
ck "L8d 时间轴隐藏" "true" "$(ev "document.getElementById('pics-timeline').hidden")"
ev "document.getElementById('pics-goto-latest').click()" >/dev/null
sleep 3
ck "L8e 点击跳转回到有图日期" "true" "$(ev "pics.items.length>0")"

echo "===== L9 缩略图缓存（服务端 .thumbs）====="
PIC_URL="$URL/api/pics/$(ev 'pics.date')/$(ev 'pics.items[pics.idx].name')?thumb=1"
ck "L9a thumb 端点 200" "200" "$(curl -s -o /dev/null -w '%{http_code}' --noproxy '*' -b "$JAR" "$PIC_URL")"
H1=$(curl -s --noproxy '*' -b "$JAR" "$PIC_URL" | md5sum | cut -d' ' -f1)
H2=$(curl -s --noproxy '*' -b "$JAR" "$PIC_URL" | md5sum | cut -d' ' -f1)
ck "L9b 两次 thumb 响应一致（缓存复用）" "$H1" "$H2"

else
  sk "L2-L9 时间轴交互" "当日无抓拍，跳过交互项"
fi

echo "===== L10 API 安全：穿越拒绝 ====="
for P in "..%2F..%2Fetc%2Fpasswd" "..%5C..%5Cetc%5Cpasswd" "photo.jpg" "%2E%2E%2F%2E%2E%2Fetc%2Fpasswd"; do
  CODE=$(curl -s -o /dev/null -w '%{http_code}' --noproxy '*' -b "$JAR" "$URL/api/pics/20261022/$P")
  if [ "$CODE" = "404" ] || [ "$CODE" = "400" ]; then
    echo "PASS  L10 穿越/非法名 [$P] → $CODE"; PASS=$((PASS+1))
  else
    echo "FAIL  L10 穿越/非法名 [$P] → $CODE（期望 404/400）"; FAIL=$((FAIL+1))
  fi
done

echo ""
echo "===== P3 L10 验收: PASS=$PASS FAIL=$FAIL SKIP=$SKIP ====="
[ "$FAIL" -eq 0 ]
