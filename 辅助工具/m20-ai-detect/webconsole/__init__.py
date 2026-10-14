"""webconsole — m20-ai-detect 的可视化控制台（零第三方依赖，见 docs/ADR-005）。

模块划分（按职责，不按技术层）：
  envfile     — m20-ai-detect.env 的读取/改写/校验（纯逻辑）
  sysactions  — systemctl / journalctl / root helper 的动作封装（subprocess）
  logfilter   — journal 日志行解析与过滤（纯逻辑）
  server      — HTTP 壳：路由 + JSON API + 静态页（含响应查看/留存，见 docs/ADR-006）
"""

__version__ = "0.2.1"
