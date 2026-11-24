# 安全规则

## 危险代码模式（自动拒绝）

以下模式出现在变异文件中将自动拒绝：

```python
DANGEROUS_PATTERNS = [
    # 文件删除
    "rm -rf",
    "os.remove(",
    "shutil.rmtree(",
    "os.unlink(",
    
    # 系统命令执行
    "os.system(",
    "subprocess.call(",
    "subprocess.run(",
    
    # 网络请求（变异过程中禁止）
    "requests.post(",
    "requests.get(",
    "urllib.request",
    "urlopen(",
    
    # 动态代码执行
    "eval(",
    "exec(",
    "__import__(",
    "compile(",
    
    # 敏感路径
    "open('/etc",
    "open('~/.ssh",
    "/root/.ssh",
    "/etc/passwd",
    "/etc/shadow",
    
    # 凭证泄露
    "password",
    "secret",
    "api_key",
    "token",
    "credential",
]
```

## 受保护文件（不可自动修改）

- SOUL.md — 人格定义
- USER.md — 用户信息
- IDENTITY.md — 身份
- ~/.ssh/ — SSH 配置
- /etc/ — 系统配置
- openclaw.json — 系统配置（需 special approval）

## 受保护目录（不可写入）

- /etc/
- ~/.ssh/
- /root/.ssh/
- /tmp/（只能用于临时文件）

## 大小限制

- 单个变异文件：≤ 500KB
- 单次变异总大小：≤ 1MB
- SKILL.md 建议 ≤ 500 行
