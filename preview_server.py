import time
from flask import Flask
from api_server import stats, START_TIME

app = Flask(__name__)

@app.route("/")
def index():
    uptime_sec = int(time.time() - START_TIME)
    m, s = divmod(uptime_sec, 60)
    h, m = divmod(m, 60)
    uptime_str = f"{h}h {m}m {s}s"

    rows = ""
    for e in stats["last_10"]:
        color = {
            "Approved": "#00ff88",
            "Charged":  "#00ccff",
            "Declined": "#ff4444",
            "Error":    "#ffaa00"
        }.get(e["status"], "#ffffff")
        rows += f"""
        <tr>
            <td>{e['cc']}</td>
            <td>{e['site']}</td>
            <td>{e['gateway']}</td>
            <td style='color:{color};font-weight:bold'>{e['status']}</td>
            <td>{e['message']}</td>
            <td>{e['time']}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Shopify Checker API</title>
    <meta http-equiv='refresh' content='5'>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ background:#0d0d0d; color:#e0e0e0; font-family:'Segoe UI',sans-serif; padding:30px; }}
        h1 {{ color:#00ff88; font-size:24px; margin-bottom:20px; }}
        .cards {{ display:flex; gap:15px; margin-bottom:30px; flex-wrap:wrap; }}
        .card {{ background:#1a1a1a; border:1px solid #333; border-radius:10px; padding:20px; min-width:150px; }}
        .card h3 {{ font-size:13px; color:#888; margin-bottom:8px; }}
        .card p {{ font-size:28px; font-weight:bold; }}
        .green {{ color:#00ff88; }}
        .blue  {{ color:#00ccff; }}
        .red   {{ color:#ff4444; }}
        .orange {{ color:#ffaa00; }}
        .white {{ color:#ffffff; }}
        table {{ width:100%; border-collapse:collapse; background:#1a1a1a; border-radius:10px; overflow:hidden; }}
        th {{ background:#222; padding:12px; text-align:left; font-size:12px; color:#888; text-transform:uppercase; }}
        td {{ padding:11px 12px; font-size:13px; border-bottom:1px solid #222; }}
        tr:last-child td {{ border-bottom:none; }}
        .status {{ color:#00ff88; }}
        .badge {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; background:#222; }}
    </style>
</head>
<body>
    <h1>⚡ Shopify Checker API</h1>
    <div class='cards'>
        <div class='card'>
            <h3>STATUS</h3>
            <p class='green'>🟢 Online</p>
        </div>
        <div class='card'>
            <h3>UPTIME</h3>
            <p class='white'>{uptime_str}</p>
        </div>
        <div class='card'>
            <h3>TOTAL</h3>
            <p class='white'>{stats['total']}</p>
        </div>
        <div class='card'>
            <h3>APPROVED</h3>
            <p class='green'>{stats['approved']}</p>
        </div>
        <div class='card'>
            <h3>CHARGED</h3>
            <p class='blue'>{stats['charged']}</p>
        </div>
        <div class='card'>
            <h3>DECLINED</h3>
            <p class='red'>{stats['declined']}</p>
        </div>
        <div class='card'>
            <h3>ERROR</h3>
            <p class='orange'>{stats['error']}</p>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Card</th>
                <th>Site</th>
                <th>Gateway</th>
                <th>Status</th>
                <th>Response</th>
                <th>Time</th>
            </tr>
        </thead>
        <tbody>
            {rows if rows else "<tr><td colspan='6' style='text-align:center;color:#555;padding:30px'>No checks yet</td></tr>"}
        </tbody>
    </table>
</body>
</html>"""
    return html

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)