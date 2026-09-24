import glob
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_DIR = os.path.join(BASE_DIR, "cases")
STATIC_HTML = os.path.join(BASE_DIR, "ui", "static", "index.html")
ROOT_HTML = os.path.join(BASE_DIR, "index.html")

cases = {}
for cp in sorted(glob.glob(os.path.join(CASES_DIR, "HHG-*.json"))):
    cid = os.path.basename(cp).replace(".json", "")
    with open(cp, "r", encoding="utf-8") as f:
        cases[cid] = json.load(f)

print(f"Loaded {len(cases)} cases.")

# Read static html
with open(STATIC_HTML, "r", encoding="utf-8") as f:
    content = f.read()

# Make sure EMBEDDED_CASES is injected
embedded_json = json.dumps(cases)
embedded_block = f"""
    // Embedded benchmark case data for zero-latency standalone / GitHub Pages execution
    const EMBEDDED_CASES = {embedded_json};
"""

# Replace init and selectCase logic to be dual-mode (REST API + Standalone Fallback)
dual_mode_script = f"""
<script>
{embedded_block}
    let allCases = [];
    let currentCase = null;
    let topologyData = null;

    // Canvas elements
    const canvas = document.getElementById('topologyCanvas');
    const ctx = canvas.getContext('2d');
    let nodes = [];
    let links = [];
    let draggedNode = null;

    async function init() {{
      resizeCanvas();
      window.addEventListener('resize', resizeCanvas);
      setupCanvasInteractions();

      // Load Stats
      try {{
        const statsRes = await fetch('/api/stats');
        if (statsRes.ok) {{
          const stats = await statsRes.json();
          updateStatsBar(stats);
        }} else {{
          loadEmbeddedStats();
        }}
      }} catch (e) {{
        loadEmbeddedStats();
      }}

      // Load Case List
      try {{
        const res = await fetch('/api/cases');
        if (res.ok) {{
          const data = await res.json();
          allCases = data.cases;
        }} else {{
          loadEmbeddedCases();
        }}
      }} catch (e) {{
        loadEmbeddedCases();
      }}

      renderCaseQueue(allCases);
      if (allCases.length > 0) {{
        selectCase(allCases[0].case_id);
      }}

      requestAnimationFrame(renderLoop);
    }}

    function loadEmbeddedStats() {{
      const caseList = Object.values(EMBEDDED_CASES);
      const total = caseList.length;
      const fraud = caseList.filter(c => c.case.verdict === 'fraud').length;
      const legit = caseList.filter(c => c.case.verdict === 'legitimate').length;
      const sars = caseList.filter(c => c.sar && c.sar.file).length;
      const exposure = caseList.reduce((acc, c) => acc + (c.case.exposure_usd || 0), 0);
      updateStatsBar({{
        total_cases: total,
        fraud_cases: fraud,
        legitimate_cases: legit,
        sars_filed: sars,
        total_exposure_usd: exposure
      }});
    }}

    function loadEmbeddedCases() {{
      allCases = Object.values(EMBEDDED_CASES).map(d => ({{
        case_id: d.case_id,
        status: d.case.status,
        verdict: d.case.verdict,
        fraud_probability: d.case.fraud_probability,
        pattern: d.case.pattern,
        exposure_usd: d.case.exposure_usd,
        sar_filed: d.sar ? d.sar.file : false,
        latency_s: d.latency_s
      }}));
    }}

    function updateStatsBar(stats) {{
      document.getElementById('stat-total').innerText = `${{stats.total_cases}} / ${{stats.total_cases}}`;
      document.getElementById('stat-fraud').innerText = stats.fraud_cases;
      document.getElementById('stat-legit').innerText = stats.legitimate_cases;
      document.getElementById('stat-sar').innerText = stats.sars_filed;
      document.getElementById('stat-exposure').innerText = `$${{stats.total_exposure_usd.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}`;
    }}

    function renderCaseQueue(casesToRender) {{
      const container = document.getElementById('case-queue-list');
      container.innerHTML = '';

      casesToRender.forEach(c => {{
        const div = document.createElement('div');
        div.className = `p-2.5 rounded-lg border cursor-pointer transition flex items-center justify-between text-xs ${{
          currentCase && currentCase.case_id === c.case_id
            ? 'bg-orange-500/10 border-orange-500/50 shadow-md'
            : 'bg-slate-900/60 hover:bg-slate-800/80 border-slate-800'
        }}`;
        div.onclick = () => selectCase(c.case_id);

        const isFraud = c.verdict === 'fraud';
        const verdictColor = isFraud ? 'bg-rose-500/20 text-rose-400 border-rose-500/30' : 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';

        div.innerHTML = `
          <div>
            <div class="flex items-center gap-2">
              <span class="font-bold text-white">${{c.case_id}}</span>
              <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold border ${{verdictColor}}">${{c.verdict.toUpperCase()}}</span>
              ${{c.sar_filed ? '<span class="text-[9px] bg-amber-500/20 text-amber-300 px-1 rounded border border-amber-500/30">SAR</span>' : ''}}
            </div>
            <div class="text-[11px] text-slate-400 mt-0.5">${{c.pattern !== 'none' ? c.pattern.replace(/_/g, ' ') : 'cleared'}}</div>
          </div>
          <div class="text-right">
            <div class="font-bold text-slate-200">$${{c.exposure_usd.toFixed(2)}}</div>
            <div class="text-[10px] text-slate-500">Prob: ${{c.fraud_probability.toFixed(2)}}</div>
          </div>
        `;
        container.appendChild(div);
      }});
    }}

    function filterQueue(type) {{
      document.querySelectorAll('#btn-filter-all, #btn-filter-fraud, #btn-filter-legit, #btn-filter-sar').forEach(b => {{
        b.className = "px-2.5 py-1 rounded font-medium text-slate-400 hover:text-slate-200";
      }});
      if (type === 'all') {{
        document.getElementById('btn-filter-all').className = "px-2.5 py-1 rounded font-medium bg-slate-800 text-orange-400 border border-slate-700";
        renderCaseQueue(allCases);
      }} else if (type === 'fraud') {{
        document.getElementById('btn-filter-fraud').className = "px-2.5 py-1 rounded font-medium bg-slate-800 text-orange-400 border border-slate-700";
        renderCaseQueue(allCases.filter(c => c.verdict === 'fraud'));
      }} else if (type === 'legitimate') {{
        document.getElementById('btn-filter-legit').className = "px-2.5 py-1 rounded font-medium bg-slate-800 text-orange-400 border border-slate-700";
        renderCaseQueue(allCases.filter(c => c.verdict === 'legitimate'));
      }} else if (type === 'sar') {{
        document.getElementById('btn-filter-sar').className = "px-2.5 py-1 rounded font-medium bg-slate-800 text-orange-400 border border-slate-700";
        renderCaseQueue(allCases.filter(c => c.sar_filed));
      }}
    }}

    async function selectCase(caseId) {{
      try {{
        const res = await fetch('/api/case/' + caseId);
        if (res.ok) {{
          currentCase = await res.json();
        }} else {{
          currentCase = EMBEDDED_CASES[caseId];
        }}
      }} catch (e) {{
        currentCase = EMBEDDED_CASES[caseId];
      }}

      if (!currentCase) return;
      updateCaseView(currentCase);

      // Load Topology
      try {{
        const topRes = await fetch('/api/topology/' + caseId);
        if (topRes.ok) {{
          topologyData = await topRes.json();
        }} else {{
          topologyData = generateLocalTopology(currentCase);
        }}
      }} catch (e) {{
        topologyData = generateLocalTopology(currentCase);
      }}

      buildGraphNodes(topologyData);
      renderCaseQueue(allCases);
    }}

    function generateLocalTopology(data) {{
      const c = data.case || {{}};
      const caseId = data.case_id;
      const affected = c.affected_txn_ids || [];
      const connected_cards = c.connected_card_ids || [];
      const dev_profs = c.connected_device_profiles || [];

      const nodes = [
        {{ id: caseId, label: 'Case: ' + caseId, type: 'case', status: c.status }}
      ];
      const links = [];

      let cardId = 'CARD-001';
      for (let e of (c.evidence || [])) {{
        for (let eid of (e.entity_ids || [])) {{
          if (eid.includes('-K')) {{ cardId = eid; break; }}
        }}
      }}
      nodes.push({{ id: cardId, label: 'Card: ' + cardId, type: 'card' }});
      links.push({{ source: caseId, target: cardId, rel: 'ON_CARD' }});

      const custId = cardId.includes('-') ? cardId.split('-')[0] : 'CUST';
      nodes.push({{ id: custId, label: 'Customer: ' + custId, type: 'customer' }});
      links.push({{ source: custId, target: cardId, rel: 'OWNS' }});

      for (let tid of affected.slice(0, 4)) {{
        nodes.push({{ id: String(tid), label: 'Txn: ' + tid, type: 'transaction' }});
        links.push({{ source: cardId, target: String(tid), rel: 'MADE' }});
      }}

      for (let cc of connected_cards.slice(0, 3)) {{
        nodes.push({{ id: cc, label: 'Linked: ' + cc, type: 'connected_card' }});
        links.push({{ source: caseId, target: cc, rel: 'CONNECTED_TO' }});
      }}

      if (dev_profs && dev_profs.length > 0) {{
        const dLabel = dev_profs[0].includes('|') ? dev_profs[0].split('|')[0].trim() : dev_profs[0].slice(0, 20);
        nodes.push({{ id: 'DEV-01', label: 'Device: ' + dLabel, type: 'device' }});
        links.push({{ source: cardId, target: 'DEV-01', rel: 'FROM_DEVICE' }});
        for (let cc of connected_cards.slice(0, 3)) {{
          links.push({{ source: cc, target: 'DEV-01', rel: 'SHARED_DEVICE' }});
        }}
      }}

      for (let sc of (c.similar_prior_cases || []).slice(0, 2)) {{
        nodes.push({{ id: sc, label: 'Prior: ' + sc, type: 'closed_case' }});
        links.push({{ source: caseId, target: sc, rel: 'CASE_MEMORY' }});
      }}

      return {{ nodes: nodes, links: links }};
    }}

    function updateCaseView(data) {{
      const c = data.case;
      document.getElementById('active-case-id').innerText = data.case_id;

      // Status Badge
      const statusBadge = document.getElementById('active-status-badge');
      statusBadge.innerText = c.status.toUpperCase();
      statusBadge.className = `px-2.5 py-0.5 rounded-full text-xs font-semibold ${{
        c.status === 'closed_fraud' ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40' :
        c.status === 'closed_legitimate' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' :
        'bg-amber-500/20 text-amber-300 border border-amber-500/40'
      }}`;

      // Verdict Badge
      const verdictBadge = document.getElementById('active-verdict-badge');
      verdictBadge.innerText = c.verdict.toUpperCase();
      verdictBadge.className = `px-2.5 py-0.5 rounded-full text-xs font-semibold ${{
        c.verdict === 'fraud' ? 'bg-rose-600/30 text-rose-300' : 'bg-emerald-600/30 text-emerald-300'
      }}`;

      document.getElementById('active-pattern-badge').innerText = c.pattern !== 'none' ? c.pattern.replace(/_/g, ' ') : 'Legitimate / Baseline Verified';
      document.getElementById('active-exposure').innerText = `$${{c.exposure_usd.toFixed(2)}}`;
      document.getElementById('active-fraud-prob').innerText = c.fraud_probability.toFixed(2);
      document.getElementById('graph-vertex-id').innerText = c.graph_case_id || 'PERSISTED_TO_GRAPH';

      // Card & Cust from evidence
      let cardId = "C01234-K1", custId = "C01234", txnId = c.affected_txn_ids[0] || "TXN";
      for (let e of c.evidence) {{
        for (let eid of e.entity_ids) {{
          if (eid.includes('-K')) {{ cardId = eid; custId = eid.split('-')[0]; break; }}
        }}
      }}
      document.getElementById('active-card-id').innerText = cardId;
      document.getElementById('active-cust-id').innerText = custId;
      document.getElementById('active-txn-id').innerText = txnId;

      // Model Score
      document.getElementById('active-model-score').innerText = (c.evidence[0] && c.evidence[0].claim.match(/score ([0-9\.]+)/)) ? RegExp.$1 : '0.65';

      // Actions Render
      renderActionList('initial-actions-list', data.next_best_actions.initial);
      renderActionList('final-actions-list', data.next_best_actions.final);
      document.getElementById('what-changed-text').innerText = data.next_best_actions.what_changed;

      // SAR Render
      const sar = data.sar;
      const sarBadge = document.getElementById('sar-filing-badge');
      if (sar.file) {{
        sarBadge.innerText = "REQUIRED (L2 APPROVAL)";
        sarBadge.className = "text-[10px] bg-rose-500/20 text-rose-400 border border-rose-500/30 px-2 py-0.5 rounded font-bold";
        document.getElementById('sar-content-block').classList.remove('hidden');
        document.getElementById('sar-not-required-block').classList.add('hidden');
        document.getElementById('sar-reason').innerText = sar.reason;
        document.getElementById('sar-narrative').innerText = sar.narrative;
        document.getElementById('sar-subjects').innerText = sar.subjects.slice(0, 3).join(', ');
      }} else {{
        sarBadge.innerText = "NOT REQUIRED";
        sarBadge.className = "text-[10px] bg-slate-800 text-slate-400 border border-slate-700 px-2 py-0.5 rounded font-bold";
        document.getElementById('sar-content-block').classList.add('hidden');
        document.getElementById('sar-not-required-block').classList.remove('hidden');
      }}

      // Memory render
      const memContainer = document.getElementById('case-memory-list');
      memContainer.innerHTML = '';
      (c.similar_prior_cases || []).forEach(sc => {{
        const item = document.createElement('div');
        item.className = "p-2 rounded bg-slate-900 border border-slate-800 text-xs flex items-center justify-between";
        item.innerHTML = `<span class="font-mono text-purple-300">${{sc}}</span><span class="text-[10px] text-slate-500">Historical Precedent</span>`;
        memContainer.appendChild(item);
      }});

      // Stepper Render
      renderStepper(data);
    }}

    function renderActionList(containerId, actions) {{
      const container = document.getElementById(containerId);
      container.innerHTML = '';
      (actions || []).forEach(a => {{
        const div = document.createElement('div');
        const routeColor = a.route === 'L2' ? 'bg-rose-500/20 text-rose-300 border-rose-500/30' :
                           a.route === 'L1' ? 'bg-amber-500/20 text-amber-300 border-amber-500/30' :
                           'bg-emerald-500/20 text-emerald-300 border-emerald-500/30';
        div.className = "p-2 rounded bg-slate-900/90 border border-slate-800 flex items-start justify-between gap-2 text-xs";
        div.innerHTML = `
          <div>
            <div class="font-bold text-slate-200">${{a.action}}</div>
            <div class="text-[11px] text-slate-400 mt-0.5">${{a.reason}}</div>
          </div>
          <span class="px-2 py-0.5 rounded text-[10px] font-bold border shrink-0 ${{routeColor}}">${{a.route}}</span>
        `;
        container.appendChild(div);
      }});
    }}

    function renderStepper(data) {{
      const c = data.case;
      const container = document.getElementById('stepper-container');
      container.innerHTML = '';

      const steps = [
        {{ num: 1, title: "Trigger Ingestion", icon: "fa-bell", desc: "Alert received & ingested" }},
        {{ num: 2, title: "Graph Traversal", icon: "fa-diagram-project", desc: "Card window & 2-hop device neighbors" }},
        {{ num: 3, title: "Evidence Synthesis", icon: "fa-microscope", desc: `${{c.evidence.length}} defensible claims assembled` }},
        {{ num: 4, title: "Uncertainty & Typology", icon: "fa-gauge-high", desc: `Prob: ${{c.fraud_probability.toFixed(2)}} | ${{c.pattern}}` }},
        {{ num: 5, title: "Initial Routing", icon: "fa-shield", desc: "Policy R1-R10 evaluated" }},
        {{ num: 6, title: "Controlled Action", icon: "fa-user-check", desc: data.evidence_requests.length > 0 ? "Customer validation simulated" : "Direct baseline closure" }},
        {{ num: 7, title: "SAR Decision", icon: "fa-file-lines", desc: data.sar.file ? "SAR formulated" : "Internal case only" }},
        {{ num: 8, title: "Graph Memory Write", icon: "fa-floppy-disk", desc: "Case written to TigerGraph" }}
      ];

      steps.forEach(s => {{
        const stepEl = document.createElement('div');
        stepEl.className = "min-w-[150px] p-2.5 rounded-lg bg-slate-900 border border-slate-800 shrink-0 text-xs";
        stepEl.innerHTML = `
          <div class="flex items-center gap-1.5 text-orange-400 font-bold mb-1">
            <span class="w-5 h-5 rounded-full bg-orange-500/20 border border-orange-500/30 flex items-center justify-center text-[10px]">${{s.num}}</span>
            <span class="text-[11px]">${{s.title}}</span>
          </div>
          <p class="text-[10px] text-slate-400 leading-tight">${{s.desc}}</p>
        `;
        container.appendChild(stepEl);
      }});

      document.getElementById('stepper-stop-reason').innerText = data.stop_reason;
    }}

    async function simulateApproval(route) {{
      if (!currentCase) return;
      try {{
        await fetch(`/api/approve/${{currentCase.case_id}}`, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ route: route, action: "APPROVED_CONFIRMED" }})
        }});
      }} catch (e) {{
        console.log("Local approval simulation");
      }}
      const toast = document.getElementById('approval-toast');
      toast.innerText = `${{route}} Authorization Confirmed & Appended to Case Memory Audit Trail!`;
      toast.classList.remove('hidden');
      setTimeout(() => toast.classList.add('hidden'), 3000);
    }}

    function copySARNarrative() {{
      const text = document.getElementById('sar-narrative').innerText;
      navigator.clipboard.writeText(text);
      alert("SAR Narrative copied to clipboard for FinCEN regulatory filing!");
    }}

    // -------------------------------------------------------------------------
    // Canvas Graph Simulation (Force-directed layout)
    // -------------------------------------------------------------------------
    function resizeCanvas() {{
      const rect = canvas.parentElement.getBoundingClientRect();
      canvas.width = rect.width;
      canvas.height = rect.height;
    }}

    function buildGraphNodes(data) {{
      const width = canvas.width;
      const height = canvas.height;
      const centerX = width / 2;
      const centerY = height / 2;

      nodes = (data.nodes || []).map((n, i) => {{
        const angle = (i / data.nodes.length) * Math.PI * 2;
        const radius = n.type === 'case' ? 0 : n.type === 'card' ? 90 : 180;
        return {{
          ...n,
          x: centerX + Math.cos(angle) * radius + (Math.random() - 0.5) * 30,
          y: centerY + Math.sin(angle) * radius + (Math.random() - 0.5) * 30,
          vx: 0,
          vy: 0,
          radius: n.type === 'case' ? 24 : n.type === 'card' ? 18 : 14
        }};
      }});

      const nodeMap = new Map(nodes.map(n => [n.id, n]));
      links = (data.links || []).map(l => ({{
        source: nodeMap.get(l.source),
        target: nodeMap.get(l.target),
        rel: l.rel
      }})).filter(l => l.source && l.target);
    }}

    function resetGraphView() {{
      if (topologyData) buildGraphNodes(topologyData);
    }}

    function renderGraph() {{
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const k = 0.05;
      const rep = 800;

      // Link spring
      links.forEach(l => {{
        const dx = l.target.x - l.source.x;
        const dy = l.target.y - l.source.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (dist - 120) * k;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        if (l.source !== draggedNode) {{ l.source.x += fx * 0.2; l.source.y += fy * 0.2; }}
        if (l.target !== draggedNode) {{ l.target.x -= fx * 0.2; l.target.y -= fy * 0.2; }}
      }});

      // Node repulsion
      for (let i = 0; i < nodes.length; i++) {{
        for (let j = i + 1; j < nodes.length; j++) {{
          const dx = nodes[j].x - nodes[i].x;
          const dy = nodes[j].y - nodes[i].y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          if (dist < 200) {{
            const force = rep / (dist * dist);
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            if (nodes[i] !== draggedNode) {{ nodes[i].x -= fx; nodes[i].y -= fy; }}
            if (nodes[j] !== draggedNode) {{ nodes[j].x += fx; nodes[j].y += fy; }}
          }}
        }}
      }}

      // Boundary clamp
      nodes.forEach(n => {{
        if (n !== draggedNode) {{
          n.x = Math.max(n.radius + 10, Math.min(canvas.width - n.radius - 10, n.x));
          n.y = Math.max(n.radius + 10, Math.min(canvas.height - n.radius - 10, n.y));
        }}
      }});

      // Draw links
      ctx.lineWidth = 1.5;
      links.forEach(l => {{
        ctx.strokeStyle = '#243247';
        ctx.beginPath();
        ctx.moveTo(l.source.x, l.source.y);
        ctx.lineTo(l.target.x, l.target.y);
        ctx.stroke();

        if (l.rel) {{
          const midX = (l.source.x + l.target.x) / 2;
          const midY = (l.source.y + l.target.y) / 2;
          ctx.fillStyle = '#64748B';
          ctx.font = '9px monospace';
          ctx.fillText(l.rel, midX - 15, midY - 4);
        }}
      }});

      // Draw nodes
      nodes.forEach(n => {{
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);

        let color = '#3B82F6';
        if (n.type === 'case') color = '#F97316';
        else if (n.type === 'customer') color = '#A855F7';
        else if (n.type === 'transaction') color = '#F43F5E';
        else if (n.type === 'device') color = '#FBBF24';
        else if (n.type === 'connected_card') color = '#06B6D4';
        else if (n.type === 'closed_case') color = '#6B7280';

        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.fillStyle = '#FFFFFF';
        ctx.font = 'bold 10px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(n.label || n.id, n.x, n.y + n.radius + 14);
      }});
    }}

    function renderLoop() {{
      renderGraph();
      requestAnimationFrame(renderLoop);
    }}

    function setupCanvasInteractions() {{
      let isDragging = false;

      canvas.addEventListener('mousedown', e => {{
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        for (let n of nodes) {{
          const dx = mx - n.x;
          const dy = my - n.y;
          if (Math.sqrt(dx * dx + dy * dy) < n.radius + 5) {{
            draggedNode = n;
            isDragging = true;
            break;
          }}
        }}
      }});

      canvas.addEventListener('mousemove', e => {{
        if (isDragging && draggedNode) {{
          const rect = canvas.getBoundingClientRect();
          draggedNode.x = e.clientX - rect.left;
          draggedNode.y = e.clientY - rect.top;
        }}
      }});

      window.addEventListener('mouseup', () => {{
        isDragging = false;
        draggedNode = null;
      }});
    }}

    window.onload = init;
</script>
"""

# Extract the HTML up to the first <script> tag (not tailwind)
split_marker = "<script>\n    let allCases = [];"
if split_marker not in content:
    # Alternative split on standard script block
    parts = re.split(r'<script>\s+let allCases', content)
    html_header = parts[0]
else:
    html_header = content.split(split_marker)[0]

full_page = html_header + dual_mode_script + "\n</body>\n</html>"

with open(ROOT_HTML, "w", encoding="utf-8") as f:
    f.write(full_page)

with open(STATIC_HTML, "w", encoding="utf-8") as f:
    f.write(full_page)

print("Generated standalone dual-mode index.html successfully at repo root and in static folder!")
