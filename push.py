# -*- coding: utf-8 -*-
"""
通过 GitHub API 推送代码（绕过 github.com 直连阻断，走 api.github.com）。

用法：python push.py "提交说明"
依赖：gh CLI 已登录（gh auth status 可验证）。
"""
import base64
import json
import os
import subprocess
import sys

REPO = 'dll315/daily-board'
BRANCH = 'main'
FILES = ['.gitignore', 'README.md', 'push.py', 'server.py', 'start.bat',
         'Dockerfile', 'docker-compose.yml',
         'public/app.js', 'public/index.html', 'public/style.css']


def gh(path, method='GET', payload=None):
    cmd = ['gh', 'api', path]
    if method != 'GET':
        cmd += ['-X', method, '--input', '-']
    r = subprocess.run(cmd, input=(json.dumps(payload).encode() if payload else b''),
                       capture_output=True)
    if r.returncode != 0:
        raise SystemExit('gh api 失败: ' + r.stderr.decode('utf-8', 'replace')[:400])
    return json.loads(r.stdout) if r.stdout.strip() else {}


def main():
    message = sys.argv[1] if len(sys.argv) > 1 else '更新'
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # 1. 读取远端当前状态（空仓库则从零建树）
    base_tree, parents = None, []
    try:
        ref = gh('/repos/%s/git/refs/heads/%s' % (REPO, BRANCH))
        base_commit = gh('/repos/%s/git/commits/%s' % (REPO, ref['object']['sha']))
        base_tree = base_commit['tree']['sha']
        parents = [base_commit['sha']]
        print('远端基准提交:', base_commit['sha'][:8])
    except SystemExit:
        print('远端为空仓库，将创建首次提交')

    # 2. 上传 blob
    tree_items = []
    for f in FILES:
        if not os.path.exists(f):
            print('跳过（本地不存在）:', f)
            continue
        with open(f, 'rb') as fp:
            data = fp.read()
        blob = gh('/repos/%s/git/blobs' % REPO, 'POST',
                  {'content': base64.b64encode(data).decode(), 'encoding': 'base64'})
        tree_items.append({'path': f, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
        print('已上传 blob:', f, '(%d bytes)' % len(data))

    # 3. 建树、建提交
    payload = {'tree': tree_items}
    if base_tree:
        payload['base_tree'] = base_tree
    tree = gh('/repos/%s/git/trees' % REPO, 'POST', payload)
    cp = {'message': message, 'tree': tree['sha']}
    if parents:
        cp['parents'] = parents
    commit = gh('/repos/%s/git/commits' % REPO, 'POST', cp)

    # 4. 移动分支指针
    try:
        gh('/repos/%s/git/refs/heads/%s' % (REPO, BRANCH), 'POST',
           {'ref': 'refs/heads/%s' % BRANCH, 'sha': commit['sha']})
        print('首次推送完成')
    except SystemExit:
        gh('/repos/%s/git/refs/heads/%s' % (REPO, BRANCH), 'PATCH',
           {'sha': commit['sha']})
        print('推送完成:', commit['sha'][:8])
    print('仓库地址: https://github.com/%s' % REPO)


if __name__ == '__main__':
    main()
