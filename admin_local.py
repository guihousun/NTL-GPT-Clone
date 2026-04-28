from __future__ import annotations

import html
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv(override=True)

try:
    from flask import Flask, flash, redirect, render_template_string, request, url_for
except Exception as exc:  # noqa: BLE001
    raise RuntimeError(
        "Flask is not installed in the active environment. "
        "Install dependencies from environment.yml or run `pip install flask`."
    ) from exc

import admin_local_service as admin_service
import history_store


APP_TITLE = "NTL-Claw 本地管理后台"
HOST = str(os.getenv("NTL_LOCAL_ADMIN_HOST", "127.0.0.1") or "127.0.0.1").strip() or "127.0.0.1"
PORT = int(str(os.getenv("NTL_LOCAL_ADMIN_PORT", "8502") or "8502").strip() or "8502")

app = Flask(__name__)
app.secret_key = str(os.getenv("NTL_LOCAL_ADMIN_SECRET_KEY", "") or "").strip() or "ntl-local-admin-dev"


BASE_TEMPLATE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <style>
    :root {
      --bg: #0b1020;
      --panel: #111a33;
      --panel-2: #162340;
      --line: rgba(128, 160, 220, 0.26);
      --text: #ecf3ff;
      --muted: #98a9c7;
      --accent: #5fa8ff;
      --danger: #ff7f7f;
      --success: #7dd3a6;
      --warning: #f3c66b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: linear-gradient(180deg, #09101d 0%, #0b1224 100%);
      color: var(--text);
    }
    a { color: #b8d4ff; text-decoration: none; }
    .wrap { max-width: 1380px; margin: 0 auto; padding: 24px; }
    .topbar {
      display: flex; justify-content: space-between; align-items: center; gap: 16px;
      margin-bottom: 18px;
    }
    .panel {
      background: linear-gradient(180deg, rgba(17,26,51,0.96), rgba(12,20,39,0.98));
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 16px 18px;
      box-shadow: 0 12px 36px rgba(0,0,0,0.24);
    }
    .grid { display: grid; gap: 16px; }
    .grid.summary { grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin-bottom: 18px; }
    .stat-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    .stat-value { font-size: 24px; font-weight: 700; margin-top: 6px; }
    .small { color: var(--muted); font-size: 13px; }
    .flash { margin-bottom: 12px; padding: 12px 14px; border-radius: 12px; border: 1px solid var(--line); }
    .flash.success { background: rgba(23, 53, 38, 0.7); color: #d9ffe8; }
    .flash.error { background: rgba(70, 24, 24, 0.7); color: #ffd7d7; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 10px 12px; border-top: 1px solid rgba(128,160,220,0.16); vertical-align: top; }
    th { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; text-align: left; }
    .pill {
      display: inline-block; padding: 3px 10px; border-radius: 999px;
      border: 1px solid rgba(144, 182, 255, 0.25); font-size: 12px; color: #dce9ff;
      background: rgba(26, 42, 75, 0.7); margin-right: 6px;
    }
    .pill.bad { border-color: rgba(255,127,127,0.35); color: #ffd1d1; background: rgba(76, 22, 22, 0.55); }
    .pill.good { border-color: rgba(125,211,166,0.35); color: #ddffe9; background: rgba(24, 62, 41, 0.55); }
    .row-actions, .inline-form { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    input[type=text] {
      width: 100%; background: rgba(10, 17, 34, 0.9); color: var(--text);
      border: 1px solid rgba(128,160,220,0.22); border-radius: 10px; padding: 9px 10px;
    }
    button {
      border: 1px solid rgba(95,168,255,0.35); border-radius: 10px; padding: 8px 12px;
      background: rgba(23, 38, 70, 0.95); color: var(--text); cursor: pointer;
    }
    button.danger { border-color: rgba(255,127,127,0.4); color: #ffd1d1; }
    button:hover { filter: brightness(1.08); }
    .thread-grid { display: grid; gap: 14px; margin-top: 14px; }
    .thread-card { border: 1px solid rgba(128,160,220,0.18); border-radius: 14px; padding: 14px; background: rgba(12, 19, 36, 0.74); }
    .thread-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
    .section-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin-top: 12px; }
    .section-box { border: 1px solid rgba(128,160,220,0.16); border-radius: 12px; padding: 10px 12px; background: rgba(17,26,51,0.56); }
    .section-title { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; }
    .mono { font-family: Consolas, "SFMono-Regular", monospace; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <h1 style="margin:0 0 6px 0;">{{ title }}</h1>
        <div class="small">仅本机访问的管理页面，监听 {{ host }}:{{ port }}</div>
      </div>
      <div class="small"><a href="{{ url_for('dashboard') }}">总览</a></div>
    </div>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="flash {{ category }}">{{ message }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    {{ body|safe }}
  </div>
</body>
</html>
"""


def _render_page(title: str, body: str):
    return render_template_string(BASE_TEMPLATE, title=title, body=body, host=HOST, port=PORT)


def _html_escape(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


@app.get("/")
def dashboard():
    platform = admin_service.get_platform_workspace_snapshot()
    users = admin_service.list_dashboard_users(limit=200)
    no_users_html = '<tr><td colspan="10">暂无已注册用户。</td></tr>'
    summary = f"""
    <div class="grid summary">
      <div class="panel"><div class="stat-label">工作区根目录</div><div class="small mono">{_html_escape(platform['base_dir'])}</div></div>
      <div class="panel"><div class="stat-label">共享数据目录</div><div class="small mono">{_html_escape(platform['shared_dir'])}</div></div>
      <div class="panel"><div class="stat-label">线程工作区数量</div><div class="stat-value">{platform['thread_workspace_count']}</div><div class="small">{platform['thread_workspaces_bytes_label']}</div></div>
      <div class="panel"><div class="stat-label">用户元数据占用</div><div class="stat-value">{platform['users_meta_bytes_label']}</div><div class="small">_users / 认证元数据</div></div>
    </div>
    """
    rows = []
    for row in users:
        state_badge = '<span class="pill good">启用</span>' if row.get("is_active") else '<span class="pill bad">禁用</span>'
        gee_badge = _html_escape(row.get("gee_status") or "unvalidated")
        rows.append(
            f"""
            <tr>
              <td><a href="{url_for('user_detail', user_id=row['user_id'])}">{_html_escape(row.get('username') or row['user_id'])}</a><div class="small mono">{_html_escape(row['user_id'])}</div></td>
              <td>{_html_escape(row.get('role') or 'user')}</td>
              <td>{state_badge}</td>
              <td>{int(row.get('thread_count') or 0)}</td>
              <td>{_html_escape(row.get('workspace_usage_label') or '-')} / {_html_escape(row.get('workspace_limit_label') or '-')}</td>
              <td>{_html_escape(row.get('gee_mode') or 'default')}</td>
              <td>{_html_escape(row.get('gee_project_id') or 'default')}</td>
              <td>{_html_escape(row.get('google_email') or '未连接')}</td>
              <td>{gee_badge}</td>
              <td>{_html_escape(row.get('last_login_at_label') or '-')}</td>
            </tr>
            """
        )
    table = f"""
    <div class="panel">
      <h2 style="margin-top:0;">用户列表</h2>
      <table>
        <thead>
          <tr>
            <th>用户</th><th>角色</th><th>状态</th><th>线程数</th><th>工作区</th>
            <th>GEE 模式</th><th>项目</th><th>Google 账号</th><th>GEE 状态</th><th>最后登录</th>
          </tr>
        </thead>
        <tbody>{''.join(rows) if rows else no_users_html}</tbody>
      </table>
    </div>
    """
    return _render_page(APP_TITLE, summary + table)


@app.get("/users/<user_id>")
def user_detail(user_id: str):
    detail = admin_service.get_user_detail(user_id)
    user = detail["user"]
    threads = detail["threads"]
    disabled = not bool(user.get("is_active"))
    last_error_html = ""
    if user.get("gee_last_error"):
        last_error_html = (
            '<div class="small" style="margin-top:10px;color:#ffcccc;">'
            f"GEE 最近错误：{_html_escape(user.get('gee_last_error'))}</div>"
        )
    header = f"""
    <div class="panel" style="margin-bottom:16px;">
      <div class="thread-head">
        <div>
          <h2 style="margin:0;">{_html_escape(user.get('username') or user['user_id'])}</h2>
          <div class="small mono">{_html_escape(user['user_id'])}</div>
        </div>
        <div class="small">{_html_escape(user.get('workspace_usage_label') or '-')} / {_html_escape(user.get('workspace_limit_label') or '-')}</div>
      </div>
      <div style="margin-top:10px;">
        <span class="pill">{_html_escape(user.get('role') or 'user')}</span>
        {'<span class="pill good">启用</span>' if user.get('is_active') else '<span class="pill bad">禁用</span>'}
        <span class="pill">线程 {int(user.get('thread_count') or 0)}</span>
        <span class="pill">GEE { _html_escape(user.get('gee_mode') or 'default') }</span>
      </div>
      <div class="grid summary" style="margin-top:14px;">
        <div><div class="stat-label">GEE 项目</div><div class="small mono">{_html_escape(user.get('gee_project_id') or 'default')}</div></div>
        <div><div class="stat-label">Google 账号</div><div class="small">{_html_escape(user.get('google_email') or '未连接')}</div></div>
        <div><div class="stat-label">OAuth</div><div class="small">{'已连接' if user.get('oauth_connected') else '未连接'}</div></div>
        <div><div class="stat-label">GEE 状态</div><div class="small">{_html_escape(user.get('gee_status') or 'unvalidated')}</div></div>
      </div>
      <div style="margin-top:14px;" class="row-actions">
        <form class="inline-form" method="post" action="{url_for('toggle_user', user_id=user['user_id'])}">
          <input type="text" name="reason" placeholder="填写启用/禁用原因">
          <button class="{'danger' if not disabled else ''}" type="submit">{'启用用户' if disabled else '禁用用户'}</button>
        </form>
        <form class="inline-form" method="post" action="{url_for('reset_user_gee', user_id=user['user_id'])}">
          <input type="text" name="reason" placeholder="填写重置 GEE 原因">
          <button type="submit">重置 GEE</button>
        </form>
      </div>
      {last_error_html}
    </div>
    """
    thread_cards = []
    for row in threads:
        snap = row["workspace_snapshot"]
        sections_html = []
        for name, item in snap["sections"].items():
            actions = ""
            if name in ("inputs", "outputs", "memory"):
                actions = f"""
                <form method="post" action="{url_for('clear_thread_section_route', user_id=user['user_id'], thread_id=row['thread_id'], section=name)}" style="margin-top:8px;">
                  <input type="text" name="reason" placeholder="填写清空 {name} 原因">
                  <button type="submit" class="{'danger' if name == 'outputs' else ''}">清空 {name}</button>
                </form>
                """
            sections_html.append(
                f"""
                <div class="section-box">
                  <div class="section-title">{_html_escape(name)}</div>
                  <div style="font-weight:700; margin-top:6px;">{_html_escape(item['bytes_label'])}</div>
                  <div class="small">{int(item['file_count'])} 个文件</div>
                  <div class="small mono">{_html_escape(item['path'])}</div>
                  {actions}
                </div>
                """
            )
        thread_cards.append(
            f"""
            <div class="thread-card">
              <div class="thread-head">
                <div>
                  <div style="font-weight:700;">{_html_escape(row.get('thread_title') or row['thread_id'])}</div>
                  <div class="small mono">{_html_escape(row['thread_id'])}</div>
                </div>
                <div class="small">{_html_escape(snap['total_bytes_label'])} / {_html_escape(snap['thread_quota_label'])}</div>
              </div>
              <div class="small" style="margin-top:6px;">更新时间：{ _html_escape(row.get('updated_at_label') or '-') }</div>
              <div class="small" style="margin-top:4px;">工作区：<span class="mono">{_html_escape(snap['workspace_path'])}</span></div>
              <div class="small" style="margin-top:4px;">最近问题：{_html_escape(row.get('last_question') or '-')}</div>
              <div class="section-grid">{''.join(sections_html)}</div>
              <form method="post" action="{url_for('delete_thread_route', user_id=user['user_id'], thread_id=row['thread_id'])}" style="margin-top:12px;" class="inline-form">
                <input type="text" name="reason" placeholder="填写删除线程原因">
                <button type="submit" class="danger">删除线程</button>
              </form>
            </div>
            """
        )
    body = header + (
        f"<div class='panel'><h2 style='margin-top:0;'>线程列表</h2><div class='thread-grid'>{''.join(thread_cards)}</div></div>"
        if thread_cards
        else "<div class='panel'><h2 style='margin-top:0;'>线程列表</h2><div class='small'>暂无线程。</div></div>"
    )
    return _render_page(f"{APP_TITLE} | {_html_escape(user.get('username') or user['user_id'])}", body)


@app.post("/users/<user_id>/toggle")
def toggle_user(user_id: str):
    detail = admin_service.get_user_detail(user_id)
    user = detail["user"]
    disabled = bool(user.get("is_active"))
    reason = str(request.form.get("reason", "") or "").strip()
    history_store.set_user_disabled(
        user_id,
        disabled=disabled,
        reason=reason,
        admin_user_id=admin_service.LOCAL_ADMIN_ACTOR,
    )
    flash(f"{user.get('username') or user_id} 已{'禁用' if disabled else '启用'}。", "success")
    return redirect(url_for("user_detail", user_id=user_id))


@app.post("/users/<user_id>/reset-gee")
def reset_user_gee(user_id: str):
    reason = str(request.form.get("reason", "") or "").strip()
    history_store.reset_user_gee_pipeline(
        user_id,
        admin_user_id=admin_service.LOCAL_ADMIN_ACTOR,
        reason=reason,
    )
    flash("用户 GEE pipeline 已重置为默认配置。", "success")
    return redirect(url_for("user_detail", user_id=user_id))


@app.post("/users/<user_id>/threads/<thread_id>/clear/<section>")
def clear_thread_section_route(user_id: str, thread_id: str, section: str):
    reason = str(request.form.get("reason", "") or "").strip()
    result = admin_service.clear_thread_section(
        user_id,
        thread_id,
        section,
        admin_user_id=admin_service.LOCAL_ADMIN_ACTOR,
        reason=reason,
    )
    flash(f"已清空 {thread_id} 的 {section}，释放 {result['deleted_bytes_label']}。", "success")
    return redirect(url_for("user_detail", user_id=user_id))


@app.post("/users/<user_id>/threads/<thread_id>/delete")
def delete_thread_route(user_id: str, thread_id: str):
    reason = str(request.form.get("reason", "") or "").strip()
    admin_service.delete_thread_as_admin(
        user_id,
        thread_id,
        admin_user_id=admin_service.LOCAL_ADMIN_ACTOR,
        reason=reason,
    )
    flash(f"线程 {thread_id} 已删除。", "success")
    return redirect(url_for("user_detail", user_id=user_id))


@app.errorhandler(Exception)
def handle_error(exc: Exception):
    message = _html_escape(str(exc))
    return _render_page(APP_TITLE, f"<div class='panel'><h2>错误</h2><div class='small'>{message}</div></div>"), 500


def main() -> None:
    print(f"{APP_TITLE} 已启动：http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
