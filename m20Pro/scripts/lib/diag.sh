#!/bin/bash
RPW2="$1"
printf '%s\n' '#!/bin/sh' "printf '%s\\n' \"\$RPW2\"" > /tmp/m20ap.sh
chmod +x /tmp/m20ap.sh
echo "askpass脚本内容:"; cat /tmp/m20ap.sh
echo "askpass直接执行输出: [$(RPW2="$RPW2" /tmp/m20ap.sh)]"
echo "--- ssh -v 诊断(目标10.21.31.106) ---"
export RPW="$RPW2" SSH_ASKPASS=/tmp/m20ap.sh SSH_ASKPASS_REQUIRE=force DISPLAY=:0
ssh -v -F /dev/null -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o PreferredAuthentications=password -o PubkeyAuthentication=no \
    -o NumberOfPasswordPrompts=1 -o ConnectTimeout=8 -o LogLevel=DEBUG1 \
    user@10.21.31.106 true < /dev/null 2>&1 | grep -iE "askpass|authentications that|denied|no such|permission|read_passphrase" | head -10
rm -f /tmp/m20ap.sh
