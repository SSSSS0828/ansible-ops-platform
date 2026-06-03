from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import subprocess
import threading
import sqlite3
import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ops-secret'
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins='*')

DB_PATH = '/app/history.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS history
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     time TEXT,
                     playbook TEXT,
                     hosts TEXT,
                     status TEXT,
                     duration INTEGER)''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        'SELECT * FROM history ORDER BY id DESC LIMIT 20'
    ).fetchall()
    conn.close()
    return render_template('index.html', history=rows)

@socketio.on('run_playbook')
def handle_run(data):
    playbook = data.get('playbook')
    hosts    = data.get('hosts')
    start    = datetime.datetime.now()

    playbook_path = f'/app/playbooks/{playbook}.yml'
    inventory_path = '/app/inventory/hosts.ini'

    if not os.path.exists(playbook_path):
        emit('log', {'data': f'[错误] Playbook 不存在: {playbook_path}\n'})
        emit('done', {'status': 'failed', 'duration': 0})
        return

    cmd = [
        'ansible-playbook',
        playbook_path,
        '-i', inventory_path,
        '--limit', hosts,
    ]

    emit('log', {'data': f'执行命令: {" ".join(cmd)}\n'})

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env={**os.environ, 'ANSIBLE_HOST_KEY_CHECKING': 'False'}
    )

    for line in iter(proc.stdout.readline, ''):
        emit('log', {'data': line})

    proc.stdout.close()
    proc.wait()

    status = 'success' if proc.returncode == 0 else 'failed'
    duration = (datetime.datetime.now() - start).seconds

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'INSERT INTO history (time, playbook, hosts, status, duration) VALUES (?,?,?,?,?)',
        (start.strftime('%Y-%m-%d %H:%M:%S'), playbook, hosts, status, duration)
    )
    conn.commit()
    conn.close()

    emit('done', {'status': status, 'duration': duration})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
