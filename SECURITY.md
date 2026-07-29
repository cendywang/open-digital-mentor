# 安全说明 / Security Policy

## 部署边界

**Open Digital Mentor 是一个可扩展的 Starter，不是可以直接暴露到公网的生产服务。**

项目没有内置用户认证、会话鉴权、租户隔离、审计日志或 WAF。默认开发服务仅监听
`127.0.0.1`，Docker Compose 也只向宿主机回环地址发布端口。

如需对外提供服务，请至少在前面部署带 TLS、身份认证、速率限制和请求日志策略的反向代理，
并确保后端端口不被绕过代理直接访问。

## 设计约束

| 约束 | 实现方式 |
|---|---|
| 无代码执行、Agent 或工具调用 | 后端只有 Retriever → LLM → TTS 管线 |
| 无浏览器和任意文件工具 | 运行时依赖中不包含浏览器自动化或代码执行框架 |
| API Key 不进入浏览器 | 外部 Provider 只由 Python 后端调用；前端只读取 `NEXT_PUBLIC_*` 配置 |
| Mock 模式无出站请求 | `backend/tests/test_mock_offline.py` 会阻断并检测网络连接 |
| WebSocket Origin 白名单 | `ODM_ALLOWED_ORIGINS`，默认仅本机前端 |
| 默认绑定回环地址 | `ODM_HOST=127.0.0.1` |
| 输入与并发有上限 | 消息长度、单 IP 连接数和单会话 TTS 并发均可配置 |
| 默认不记录问题正文 | `ODM_LOG_MESSAGE_BODY=false` |

本地检查：

```bash
make security
gitleaks git --config .gitleaks.toml
```

## 密钥管理

- 本地凭据只放在仓库根目录 `.env`，该文件已被 `.gitignore` 和 Docker 构建上下文排除。
- 仓库只分发不含真实值的 `.env.example`。
- 不要通过 ZIP、网盘或直接复制整个开发工作区来发布源码；应发布 Git 中明确跟踪的文件。
- CI 和 pre-commit 使用 [gitleaks](https://github.com/gitleaks/gitleaks) 扫描提交历史。

一旦凭据曾进入提交、构建日志、Issue 或发布附件，应立即在服务商处撤销并重新签发；仅从
Git 中删除字符串并不能恢复凭据安全性。

## 报告漏洞

请不要在公开 Issue 中披露漏洞细节。

在 GitHub 仓库页面使用：

`Security` → `Advisories` → `Report a vulnerability`

公开仓库的管理员必须在首次发布时启用 **Private vulnerability reporting**。如果入口暂不可用，
可以创建一个不含技术细节的公开 Issue，请维护者提供非公开联系渠道。

报告中建议包含：

- 受影响的版本与组件
- 复现步骤或最小 PoC
- 可能的影响范围
- 可行的缓解或修复建议

维护者会尽力尽快确认和处理，但本项目不承诺固定响应 SLA。

## 当前限制

- 无请求级用户认证或授权。
- 无持久化会话隔离；同一进程的连接共享只读 Provider 实例。
- 无按用户或 API Key 维度的速率限制。
- LLM 输出未经内容安全分类；接入真实模型时应按部署场景增加策略。
- 本地知识目录由部署者管理，不应向不可信用户开放写入或上传能力。
