# Contributing

感谢你改进 Open Digital Mentor。为便于审阅，请让每个 Pull Request 只解决一个明确问题，
并在描述中说明行为变化、验证方式和任何兼容性影响。

## 本地开发

需要 Python 3.11+ 与 Node.js 20.9+：

```bash
make setup
make check
```

只改文档时可省略与改动无关的构建，但请至少检查链接、命令和事实是否仍然准确。

## 提交前

- 不要提交 `.env`、密钥、客户资料、日志或真实业务语料。
- 新增知识条目时，填写 `source` 元数据并同步更新 `KNOWLEDGE_SOURCES.md`。
- 新增或替换非代码资产时，确认可再分发，并同步更新 `ASSETS.md` 的来源、许可、修改记录、
  文件大小和 SHA-256。
- 新增依赖时，说明用途，同步更新 `pyproject.toml` 与对应 lockfile，并检查其许可和安全公告。
- 改动 WebSocket 事件、Provider 接口或配置名时，同步更新中英文 README 与测试。
- 保持 Mock 模式不需要凭据、不会发起出站请求。

## Pull Request

PR 描述应包含：

1. 改了什么，以及为什么；
2. 执行过的验证命令；
3. UI 改动的截图或短视频；
4. 新依赖、外部服务、数据或资产的许可与隐私影响。

提交贡献即表示你有权提交这些内容，并同意原创代码按仓库的
[Apache-2.0](LICENSE) 许可发布。单独登记的第三方资产继续遵循其自身许可。

安全问题不要提交公开 Issue；请按 [SECURITY.md](SECURITY.md) 的非公开渠道报告。
参与社区时请遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。
