SHELL := /bin/bash
.DEFAULT_GOAL := help

PY      := backend/.venv/bin/python
PIP     := backend/.venv/bin/pip
PYTHON  ?= python3
PY_DEPS_STAMP := backend/.venv/.odm-deps-ready
FRONTEND_DEPS_STAMP := frontend/node_modules/.odm-deps-ready

.PHONY: help setup init-env dev dev-backend dev-frontend test lint build security check verify-vrm clean

help: ## 显示可用命令
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## 安装缺失的前后端依赖（不创建 .env）
	@if ! test -x $(PY); then $(PYTHON) -m venv backend/.venv; fi
	@if ! test -f $(PY_DEPS_STAMP) || \
		! $(PY) -c 'import fastapi, pytest, ruff, websockets' >/dev/null 2>&1 || \
		test backend/requirements.lock -nt $(PY_DEPS_STAMP) || \
		test backend/requirements-dev.lock -nt $(PY_DEPS_STAMP); then \
		$(PIP) install -q -r backend/requirements-dev.lock && \
		touch $(PY_DEPS_STAMP); \
	fi
	@if ! test -f $(FRONTEND_DEPS_STAMP) || \
		! npm --prefix frontend ls --silent >/dev/null 2>&1 || \
		test frontend/package.json -nt $(FRONTEND_DEPS_STAMP) || \
		test frontend/package-lock.json -nt $(FRONTEND_DEPS_STAMP) || \
		test frontend/.npmrc -nt $(FRONTEND_DEPS_STAMP); then \
		npm --prefix frontend ci && \
		touch $(FRONTEND_DEPS_STAMP); \
	fi
	@echo ""
	@echo "  ready. run 'make dev' — 无需任何 API Key。"

init-env: ## 可选：从模板创建 .env（接入真实 Provider 时使用）
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example")

dev: setup ## 一条命令安装缺失依赖并启动前后端（Mock，无需 .env/Key）
	@trap 'kill 0' EXIT INT TERM; \
	$(MAKE) dev-backend & \
	$(MAKE) dev-frontend & \
	wait

dev-backend: ## 只启动后端
	@cd backend && ../$(PY) -m app.main

dev-frontend: ## 只启动前端
	@cd frontend && npm run dev

test: ## 运行后端测试
	@cd backend && ../$(PY) -m pytest -q
	@cd frontend && npm test

lint: ## 代码检查（ruff + tsc）
	@cd backend && ../$(PY) -m ruff check app tests
	@cd frontend && npm run typecheck

build: ## 构建前端生产包
	@cd frontend && npm run build

verify-vrm: ## 校验当前 VRM 与渲染器 API 兼容
	@cd frontend && npm run verify:vrm

security: ## 检查危险能力、依赖、忽略规则与资产台账
	@./scripts/security-check.sh

check: lint test verify-vrm build security ## 全部检查

clean: ## 清理构建产物
	@rm -rf backend/.venv backend/.pytest_cache backend/.ruff_cache
	@rm -rf frontend/node_modules frontend/.next frontend/.next-dev
	@find . -name __pycache__ -type d -prune -exec rm -rf {} +
