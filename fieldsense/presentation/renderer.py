"""Local UI HTML/SVG renderer for presentation layer."""

import json
import http.server
import socketserver
import threading
from typing import Optional

from .models import UIFieldView


class LocalUIRenderer:
    """Renders UIFieldView to a lightweight, self-contained offline HTML/CSS/SVG dashboard.

    Runs 100% locally with zero internet dependencies or external JS/CSS frameworks.
    Suitable for execution on desktop or target Debian environment (Arduino UNO Q).
    """

    def render_html(self, view: UIFieldView) -> str:
        """Generate standalone HTML/CSS/JS document from UIFieldView.

        Args:
            view: Target UIFieldView model.

        Returns:
            Complete HTML string document.
        """
        view_json = json.dumps(view.to_dict(), indent=2)

        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FieldSense AI — Offline Field Intelligence</title>
  <style>
    :root {{
      --bg-dark: #0f172a;
      --panel-bg: #1e293b;
      --accent-green: #10b981;
      --accent-yellow: #f59e0b;
      --accent-red: #ef4444;
      --accent-blue: #3b82f6;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --border-color: #334155;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: system-ui, -apple-system, sans-serif; }}
    body {{ background-color: var(--bg-dark); color: var(--text-main); padding: 20px; line-height: 1.5; }}
    header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid var(--border-color); padding-bottom: 15px; margin-bottom: 20px; }}
    .logo {{ font-size: 1.5rem; font-weight: bold; letter-spacing: 1px; color: var(--accent-green); }}
    .status-badge {{ background: var(--panel-bg); border: 1px solid var(--border-color); padding: 6px 12px; border-radius: 20px; font-size: 0.85rem; font-weight: 600; display: inline-flex; align-items: center; gap: 8px; }}
    .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
    .dot-green {{ background: var(--accent-green); }}
    .dot-blue {{ background: var(--accent-blue); }}
    
    .grid-container {{ display: grid; grid-template-columns: 1fr 2fr 1fr; gap: 20px; margin-bottom: 20px; }}
    @media (max-width: 1024px) {{ .grid-container {{ grid-template-columns: 1fr; }} }}

    .card {{ background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; }}
    .card-title {{ font-size: 1rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; font-weight: 600; }}
    
    .metric-value {{ font-size: 2.5rem; font-weight: bold; margin-bottom: 4px; }}
    .status-tag {{ display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 0.85rem; font-weight: bold; text-transform: uppercase; }}
    .status-HEALTHY {{ background: rgba(16, 185, 129, 0.2); color: var(--accent-green); border: 1px solid var(--accent-green); }}
    .status-MODERATE {{ background: rgba(245, 158, 11, 0.2); color: var(--accent-yellow); border: 1px solid var(--accent-yellow); }}
    .status-POOR {{ background: rgba(239, 68, 68, 0.2); color: var(--accent-red); border: 1px solid var(--accent-red); }}

    .map-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
    select {{ background: var(--bg-dark); color: var(--text-main); border: 1px solid var(--border-color); padding: 8px 12px; border-radius: 6px; font-size: 0.9rem; cursor: pointer; }}
    
    .map-svg-container {{ width: 100%; height: 350px; background: #090d16; border-radius: 8px; border: 1px solid var(--border-color); display: flex; justify-content: center; align-items: center; overflow: hidden; }}

    .list-item {{ border-bottom: 1px solid var(--border-color); padding: 12px 0; }}
    .list-item:last-child {{ border-bottom: none; }}
    .rec-priority {{ display: inline-block; font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; font-weight: bold; margin-right: 6px; }}
    .prio-HIGH, .prio-CRITICAL {{ background: var(--accent-red); color: #fff; }}
    .prio-MEDIUM {{ background: var(--accent-yellow); color: #000; }}
    .prio-LOW {{ background: var(--accent-blue); color: #fff; }}

    .progress-bar {{ width: 100%; height: 8px; background: var(--border-color); border-radius: 4px; overflow: hidden; margin-top: 8px; }}
    .progress-fill {{ height: 100%; background: var(--accent-blue); width: 0%; transition: width 0.3s ease; }}
  </style>
</head>
<body>

  <header>
    <div>
      <div class="logo">FIELDSENSE AI</div>
      <div style="font-size: 0.85rem; color: var(--text-muted);">Offline Portable Edge-Intelligence Platform</div>
    </div>
    <div style="display: flex; gap: 10px;">
      <span class="status-badge"><span class="dot dot-green"></span> OFFLINE MODE</span>
      <span class="status-badge"><span class="dot dot-blue"></span> Data Source: <strong id="dataSource">VIRTUAL</strong></span>
    </div>
  </header>

  <div class="grid-container">
    <!-- Left Column: Summary & Status -->
    <div style="display: flex; flex-direction: column; gap: 20px;">
      <div class="card">
        <div class="card-title">GPS & Sampling Status</div>
        <div>GPS Fix: <strong id="gpsStatus">FIXED</strong></div>
        <div style="margin-top: 10px;">
          Sampling Progress: <strong id="sampleProgress">24 / 25</strong>
          <div class="progress-bar"><div id="progressFill" class="progress-fill"></div></div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Overall Field Health</div>
        <div id="healthScore" class="metric-value">72%</div>
        <span id="healthStatusTag" class="status-tag status-MODERATE">MODERATE</span>
        <div style="margin-top: 15px; font-size: 0.85rem; color: var(--text-muted);">
          Evidence Level: <strong id="evidenceLevel">LIMITED</strong>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Diagnostics & Audit</div>
        <div style="font-size: 0.9rem;">
          <div>Total Samples: <strong id="diagTotal">25</strong></div>
          <div>Valid Samples: <strong id="diagValid">24</strong></div>
          <div>Rejected Samples: <strong id="diagRejected" style="color: var(--accent-red);">1</strong></div>
          <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 6px;">Reason: UNSTABLE_MEASUREMENT</div>
        </div>
      </div>
    </div>

    <!-- Middle Column: Map View -->
    <div class="card" style="display: flex; flex-direction: column;">
      <div class="map-header">
        <div class="card-title" style="margin-bottom: 0;">Field Intelligence Map</div>
        <select id="layerSelect">
          <option value="soil_health">Soil Health</option>
          <option value="nitrogen">Nitrogen Index</option>
          <option value="moisture">Moisture Index</option>
          <option value="carbon_readiness">Carbon Readiness</option>
        </select>
      </div>

      <div class="map-svg-container" id="mapSvgContainer">
        <svg id="fieldMapSvg" width="100%" height="100%" viewBox="0 0 400 300"></svg>
      </div>

      <div id="pointDetails" style="margin-top: 12px; font-size: 0.85rem; color: var(--text-muted);">
        Click any grid cell on the map to inspect spatial intelligence details.
      </div>
    </div>

    <!-- Right Column: Zones & Recommendations -->
    <div style="display: flex; flex-direction: column; gap: 20px;">
      <div class="card">
        <div class="card-title">Management Zones</div>
        <div id="zonesList"></div>
      </div>

      <div class="card">
        <div class="card-title">What Needs Attention</div>
        <div id="recsList"></div>
      </div>
    </div>
  </div>

  <script>
    const FIELD_DATA = {view_json};

    function initUI() {{
      // System & Field Summaries
      document.getElementById('dataSource').innerText = FIELD_DATA.system_status.data_source;
      document.getElementById('gpsStatus').innerText = FIELD_DATA.gps_status.status;
      
      const samp = FIELD_DATA.sampling_status;
      document.getElementById('sampleProgress').innerText = `${{samp.valid_samples}} / ${{samp.expected_samples}}`;
      document.getElementById('progressFill').style.width = `${{Math.min(100, (samp.valid_samples / samp.expected_samples) * 100)}}%`;

      const health = FIELD_DATA.health_summary;
      document.getElementById('healthScore').innerText = `${{Math.round(health.score * 100)}}%`;
      
      const statusTag = document.getElementById('healthStatusTag');
      statusTag.innerText = health.status;
      statusTag.className = `status-tag status-${{health.status}}`;

      document.getElementById('diagTotal').innerText = samp.total_samples;
      document.getElementById('diagValid').innerText = samp.valid_samples;
      document.getElementById('diagRejected').innerText = samp.rejected_samples;

      // Render Layer Map
      renderMap(FIELD_DATA.map.active_layer);

      // Layer dropdown listener
      document.getElementById('layerSelect').addEventListener('change', (e) => {{
        renderMap(e.target.value);
      }});

      // Render Zones
      renderZones();

      // Render Recommendations
      renderRecommendations();
    }}

    function renderMap(layerId) {{
      const svg = document.getElementById('fieldMapSvg');
      svg.innerHTML = '';

      const gridPoints = FIELD_DATA.map.grid_by_layer[layerId] || [];
      if (gridPoints.length === 0) return;

      const bounds = FIELD_DATA.map.bounds;
      const minLat = bounds.min_latitude, maxLat = bounds.max_latitude;
      const minLon = bounds.min_longitude, maxLon = bounds.max_longitude;

      const width = 360, height = 260;
      const margin = 20;

      gridPoints.forEach(pt => {{
        if (pt.value === null) return;

        // Map lat/lon to SVG canvas x, y
        const x = margin + ((pt.longitude - minLon) / (maxLon - minLon || 1)) * (width - 2 * margin);
        const y = height - margin - ((pt.latitude - minLat) / (maxLat - minLat || 1)) * (height - 2 * margin);

        // Color mapping based on score
        let color = '#ef4444'; // POOR (red)
        if (pt.value >= 0.70) color = '#10b981'; // HEALTHY (green)
        else if (pt.value >= 0.40) color = '#f59e0b'; // MODERATE (yellow)

        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', x - 12);
        rect.setAttribute('y', y - 12);
        rect.setAttribute('width', 24);
        rect.setAttribute('height', 24);
        rect.setAttribute('fill', color);
        rect.setAttribute('opacity', '0.85');
        rect.setAttribute('rx', '4');
        rect.style.cursor = 'pointer';

        rect.addEventListener('click', () => {{
          document.getElementById('pointDetails').innerHTML = 
            `<strong>Selected Point:</strong> Lat: ${{pt.latitude.toFixed(5)}}, Lon: ${{pt.longitude.toFixed(5)}} | 
             <strong>Value:</strong> ${{pt.value.toFixed(2)}} | <strong>Status:</strong> ${{pt.status}} | 
             <strong>Nearest Sample:</strong> ${{pt.support_distance}}m`;
        }});

        svg.appendChild(rect);
      }});
    }}

    function renderZones() {{
      const container = document.getElementById('zonesList');
      container.innerHTML = '';

      FIELD_DATA.zones.forEach(z => {{
        const div = document.createElement('div');
        div.className = 'list-item';
        div.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <strong>${{z.zone_id}}</strong>
            <span class="status-tag status-${{z.status}}">${{z.status}}</span>
          </div>
          <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 4px;">
            Primary Issue: <strong>${{z.primary_issue || 'None'}}</strong> | Area: ${{z.area_estimate}}m²
          </div>
        `;
        container.appendChild(div);
      }});
    }}

    function renderRecommendations() {{
      const container = document.getElementById('recsList');
      container.innerHTML = '';

      if (FIELD_DATA.recommendations.length === 0) {{
        container.innerHTML = '<div style="font-size: 0.85rem; color: var(--text-muted);">No urgent actions required.</div>';
        return;
      }}

      FIELD_DATA.recommendations.forEach(r => {{
        const div = document.createElement('div');
        div.className = 'list-item';
        div.innerHTML = `
          <div>
            <span class="rec-priority prio-${{r.priority}}">${{r.priority}}</span>
            <strong style="font-size: 0.9rem;">${{r.category}} — ${{r.zone_id}}</strong>
          </div>
          <div style="font-size: 0.85rem; margin-top: 4px;">${{r.action}}</div>
        `;
        container.appendChild(div);
      }});
    }}

    window.onload = initUI;
  </script>
</body>
</html>"""
        return html_template

    def serve_local(self, view: UIFieldView, port: int = 8080) -> socketserver.TCPServer:
        """Launch local lightweight HTTP server serving rendered HTML UI.

        Args:
            view: Target UIFieldView model.
            port: Preferred TCP port.

        Returns:
            Running TCPServer instance.
        """
        html_content = self.render_html(view).encode("utf-8")

        class SimpleHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_content)))
                self.end_headers()
                self.wfile.write(html_content)

            def log_message(self, format, *args):
                pass  # Suppress console logging for quiet embedded operation

        server = socketserver.TCPServer(("127.0.0.1", port), SimpleHandler)
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()

        return server
