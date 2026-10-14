# M20 AI 检测工作空间 —— Makefile
# 用法：make help
# 设计原则：开发机上零依赖即可跑测试；部署只依赖 ffmpeg + python3（见 docs/ADR-002）

PYTHON ?= python3
SRC := src
HOST ?= m20pro-GOS.104
REMOTE_DIR ?= /home/djw/m20-ai-detect

.PHONY: help test test-v lint doctor run paths stats clean deploy deploy-doctor deploy-console logs stop

deploy-console: ## 部署可视化控制台（同步代码 + 远端 bootstrap 一键装好并启动）
	./deploy/install.sh
	ssh $(HOST) "cd $(REMOTE_DIR) && bash deploy/console-bootstrap.sh"

help: ## 显示本帮助
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

test: ## 跑全部单元 + 集成测试（标准库 unittest，无需 pytest）
	PYTHONPATH=$(SRC) $(PYTHON) -m unittest discover -s tests -v

test-v: ## 同上，简洁输出
	PYTHONPATH=$(SRC) $(PYTHON) -m unittest discover -s tests

lint: ## 静态检查（无第三方 linter 时退化为编译 + 关键字自检）
	$(PYTHON) -m compileall -q $(SRC) tests
	@if grep -rnIE "push_video|v4l2|gst-launch" --exclude-dir=__pycache__ $(SRC) deploy/*.service 2>/dev/null | grep -v "FORBIDDEN_TOKENS = "; then \
		echo "!! 发现上游 pkill 关键词，必须改名" && exit 1; else echo "keyword check ok"; fi

doctor: ## 上线前门禁检查（V0″）：ffmpeg/AI 服务/时钟/每路源/磁盘
	M20AI_BASE_DIR=$${M20AI_BASE_DIR:-.runtime} PYTHONPATH=$(SRC) $(PYTHON) -m m20_ai_detect doctor

run: ## 前台运行采样器（调试用）
	PYTHONPATH=$(SRC) $(PYTHON) -m m20_ai_detect run

paths: ## 打印实际使用的目录
	PYTHONPATH=$(SRC) $(PYTHON) -m m20_ai_detect paths

stats: ## 查看各目录占用与结果文件
	PYTHONPATH=$(SRC) $(PYTHON) -m m20_ai_detect stats

clean: ## 清理本地运行产物
	rm -rf .runtime $(SRC)/m20_ai_detect/__pycache__ tests/__pycache__ .pytest_cache

deploy: ## 推送代码到 $(HOST):$(REMOTE_DIR) 并重启服务
	rsync -avz --delete \
		--exclude '.git' --exclude '__pycache__' --exclude '.runtime' \
		--exclude '*.pyc' \
		./ $(HOST):$(REMOTE_DIR)/
	ssh $(HOST) "cd $(REMOTE_DIR) && mkdir -p spool raw results alerts log tmp && \
		sudo systemctl restart m20-ai-detect && sleep 2 && systemctl status m20-ai-detect --no-pager -l | head -12"

deploy-doctor: ## 只在远端跑 doctor，不部署代码
	ssh $(HOST) "cd $(REMOTE_DIR) && set -a; . ./m20-ai-detect.env; set +a; \
		PYTHONPATH=src python3 -m m20_ai_detect doctor"

logs: ## 看远端最近日志
	ssh $(HOST) "journalctl -u m20-ai-detect -n 80 --no-pager"

stop: ## 停止远端服务（不影响机器人推流）
	ssh $(HOST) "sudo systemctl stop m20-ai-detect"
