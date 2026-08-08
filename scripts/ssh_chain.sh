#!/usr/bin/env bash
# ============================================================
# scripts/ssh_chain.sh — bash + sshpass 跳板到目标服务器，执行一条远程命令
# ============================================================
# 用法（在 WSL Ubuntu 内调用）：
#   bash scripts/ssh_chain.sh \
#     <bastion_host> <bastion_user> <bastion_pass> \
#     <target_host>  <target_user>  <target_pass>
#
# 远程命令通过 stdin 传入，例如：
#   echo "cd /opt/SmartReview-main && docker ps" | \
#     bash scripts/ssh_chain.sh 10.73.2.80 root 'xxx' 10.73.2.21 root 'yyy'
#
# 从 Windows (Git Bash) 调用：
#   REMOTE_CMD="cd /opt/SmartReview-main && docker ps"
#   echo "$REMOTE_CMD" | wsl bash /mnt/c/Users/Administrator/Desktop/SmartReview/scripts/ssh_chain.sh \
#     "$SSH_BASTION_HOST" "$SSH_BASTION_USER" "$SSH_BASTION_PASSWORD" \
#     "$SSH_TARGET_HOST"  "$SSH_TARGET_USER"  "$SSH_TARGET_PASSWORD"
#
# 前置依赖（仅需装一次）：
#   wsl sudo apt install sshpass
#
# 设计要点：
#   - 远程命令用 stdin 传入 + base64 编码，避免嵌套 SSH 的引号转义地狱
#   - 退出码透传（最内层命令的退出码 = 本脚本退出码）
# ============================================================

set -euo pipefail

if [ $# -ne 6 ]; then
    echo "用法: $0 <bastion_host> <bastion_user> <bastion_pass> <target_host> <target_user> <target_pass>" >&2
    echo "远程命令通过 stdin 传入" >&2
    exit 2
fi

if ! command -v sshpass >/dev/null 2>&1; then
    echo "ERROR: sshpass 未安装。请在 WSL 内执行: sudo apt install sshpass" >&2
    exit 3
fi

BASTION_HOST="$1"
BASTION_USER="$2"
BASTION_PASS="$3"
TARGET_HOST="$4"
TARGET_USER="$5"
TARGET_PASS="$6"

# 从 stdin 读取远程命令，base64 编码后传给内层 SSH（避免嵌套引号问题）
REMOTE_CMD_B64=$(base64 -w0)

# 跳板到目标，base64 解码后用 bash 执行
# 退出码由最内层 bash 透传
sshpass -p "$BASTION_PASS" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    "$BASTION_USER@$BASTION_HOST" \
    "sshpass -p '$TARGET_PASS' ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        $TARGET_USER@$TARGET_HOST \
        'echo $REMOTE_CMD_B64 | base64 -d | bash'"