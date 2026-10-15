"""webconsole — m20-ai-detect 的可视化控制台（零第三方依赖，见 docs/ADR-005）。

模块划分（按职责，不按技术层）：
  envfile     — m20-ai-detect.env 的读取/改写/校验（纯逻辑）
  sysactions  — systemctl / journalctl / root helper 的动作封装（subprocess）
  logfilter   — journal 日志行解析与过滤（纯逻辑）
  server      — HTTP 壳：路由 + JSON API + 静态页（含响应查看/留存/时间轴，见 ADR-006/008；
                受限只读文件浏览，见 ADR-009；采集开关与单位解析，见 ADR-010；
                关注目标与数据清空，见 ADR-011；相机画面快照，见 ADR-012）
"""

__version__ = "0.7.0"
