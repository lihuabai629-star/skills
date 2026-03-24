# Agent Skills Repository

这个仓库用于存放可直接分发给各种 agent 的本地 skills。

## 一条命令安装

安装单个 skill：

```bash
curl -fsSL https://raw.githubusercontent.com/lihuabai629-star/skills/main/install.sh | bash -s -- ima
```

如果机器上没有 `curl`，可以用：

```bash
wget -qO- https://raw.githubusercontent.com/lihuabai629-star/skills/main/install.sh | bash -s -- ima
```

一次安装多个 skill：

```bash
curl -fsSL https://raw.githubusercontent.com/lihuabai629-star/skills/main/install.sh | bash -s -- ima ima-note
```

默认安装到：

```bash
${CODEX_HOME:-$HOME/.codex}/skills/<skill-name>
```

如果目标位置已经存在旧版本，安装脚本会自动备份成：

```bash
<skill-name>.backup.<timestamp>
```

安装完成后重启 Codex 或对应 agent，让它重新扫描 skills。

## 本地安装

如果你已经把仓库拉到本地，也可以直接执行：

```bash
bash install.sh ima
```

## 指定其他仓库或分支

如果你后面想从别的仓库、别的分支安装，可以这样：

```bash
curl -fsSL https://raw.githubusercontent.com/lihuabai629-star/skills/main/install.sh | \
  bash -s -- --repo lihuabai629-star/skills --ref main ima
```

## IMA 额外初始化

`ima` 安装后，每个使用者都还需要完成一次自己的认证初始化：

```bash
python3 ~/.codex/skills/ima/scripts/run.py auth_manager.py setup
python3 ~/.codex/skills/ima/scripts/run.py knowledge_manager.py list --refresh
```
