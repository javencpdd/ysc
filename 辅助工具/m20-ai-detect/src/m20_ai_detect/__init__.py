"""m20-ai-detect —— M20 Pro 视频流 × 外部 AI 识别服务的采样与落库工具。

设计目标（详见 docs/ 下的 ADR）：
  * 零第三方依赖：只用 Python 标准库，部署 = 拷贝 + systemd，无需 pip/venv/联网安装；
  * 部署位与代码解耦：换主机只改环境变量（见 deploy/m20-ai-detect.env.example）；
  * 可观测：doctor 子命令在上线前跑完所有门禁检查；
  * 不干扰机器人：命令行与命名刻意避开上游 pkill 的关键词（见 capture.FORBIDDEN_TOKENS）。
"""

__version__ = "0.8.12"
