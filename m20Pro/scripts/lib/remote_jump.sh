#!/bin/bash
# 在 AOS 上执行：$1=SSH密码 $2=base64编码的巡检脚本 $3=目标主机IP
RPW2="$1"
echo "$2" | base64 -d > /tmp/m20hw.sh
printf '%s\n' '#!/bin/sh' "printf '%s\\n' \"\$RPW2\"" > /tmp/m20ap.sh
chmod +x /tmp/m20ap.sh
export RPW="$RPW2"
export SSH_ASKPASS=/tmp/m20ap.sh
export SSH_ASKPASS_REQUIRE=force
export DISPLAY=:0
ssh -F /dev/null -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o PreferredAuthentications=password -o PubkeyAuthentication=no \
    -o NumberOfPasswordPrompts=1 -o ConnectTimeout=10 -o LogLevel=ERROR \
    "user@$3" bash -s < /tmp/m20hw.sh
RC=$?
rm -f /tmp/m20ap.sh /tmp/m20hw.sh
exit $RC
