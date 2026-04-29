// Shared components for openGRIS Scaler Launcher
// Exports to window.SC

const { useState, useEffect, useRef, useCallback } = React;

/* ── SecretInput ── */
function SecretInput({ value, onChange, placeholder, style }) {
  const [visible, setVisible] = useState(false);
  return (
    <div style={{ position: "relative", display: "flex", ...style }}>
      <input
        type={visible ? "text" : "password"}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        spellCheck={false}
        autoComplete="off"
        style={{
          flex: 1,
          background: "transparent",
          border: "none",
          outline: "none",
          color: "inherit",
          font: "inherit",
          padding: 0,
          letterSpacing: visible ? "normal" : "0.12em",
        }}
      />
      <button
        onClick={() => setVisible(v => !v)}
        title={visible ? "Hide" : "Show"}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: "0 0 0 8px",
          color: visible ? "oklch(0.75 0.18 200)" : "oklch(0.5 0.05 220)",
          fontSize: "11px",
          fontFamily: "inherit",
          flexShrink: 0,
          letterSpacing: "normal",
        }}
      >
        {visible ? "HIDE" : "SHOW"}
      </button>
    </div>
  );
}

/* ── RegionSelect ── */
function RegionSelect({ value, onChange }) {
  const regions = window.SCALER_REGIONS || [];
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const triggerRef = useRef(null);
  const dropdownRef = useRef(null);
  const [dropdownStyle, setDropdownStyle] = useState({});

  const filtered = regions.filter(r =>
    r.value.toLowerCase().includes(search.toLowerCase()) ||
    r.label.toLowerCase().includes(search.toLowerCase())
  );

  useEffect(() => {
    function handleClick(e) {
      if (
        triggerRef.current && !triggerRef.current.contains(e.target) &&
        dropdownRef.current && !dropdownRef.current.contains(e.target)
      ) { setOpen(false); setSearch(""); }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const openDropdown = () => {
    if (!triggerRef.current) return;
    const r = triggerRef.current.getBoundingClientRect();
    setDropdownStyle({ position: "fixed", top: r.bottom + 4, left: r.left, width: r.width });
    setSearch("");
    setOpen(true);
  };

  const selected = regions.find(r => r.value === value);

  return (
    <div ref={triggerRef} style={{ position: "relative" }}>
      <button
        onClick={() => open ? setOpen(false) : openDropdown()}
        style={{
          width: "100%",
          background: "rgba(255,255,255,0.04)",
          border: "1px solid rgba(0,200,224,0.15)",
          borderRadius: 3,
          padding: "8px 10px",
          color: "oklch(0.85 0.06 200)",
          fontFamily: "inherit",
          fontSize: 12,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          textAlign: "left",
          outline: "none",
        }}
      >
        <span style={{ flex: 1 }}>
          <span style={{ color: "oklch(0.85 0.12 200)", fontWeight: 600 }}>{value}</span>
          {selected && <span style={{ color: "oklch(0.5 0.04 220)", marginLeft: 10, fontSize: 11 }}>{selected.label}</span>}
        </span>
        <span style={{ color: "oklch(0.5 0.04 220)", fontSize: 10, flexShrink: 0 }}>{open ? "▲" : "▼"}</span>
      </button>
      {open && ReactDOM.createPortal(
        <div ref={dropdownRef} style={{
          ...dropdownStyle,
          background: "#0c1219",
          border: "1px solid rgba(0,200,224,0.25)",
          borderRadius: 4,
          zIndex: 9999,
          boxShadow: "0 16px 48px rgba(0,0,0,0.7)",
          overflow: "hidden",
        }}>
          <div style={{ padding: "8px 10px", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
            <input
              autoFocus
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search regions…"
              style={{
                width: "100%",
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: 3,
                padding: "6px 9px",
                color: "oklch(0.88 0.06 200)",
                fontFamily: "inherit",
                fontSize: 12,
                outline: "none",
              }}
            />
          </div>
          <div style={{ maxHeight: 260, overflowY: "auto" }}>
            {filtered.map(r => (
              <div
                key={r.value}
                onClick={() => { onChange(r.value); setOpen(false); setSearch(""); }}
                style={{
                  padding: "8px 12px",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "baseline",
                  gap: 10,
                  background: r.value === value ? "rgba(0,200,224,0.08)" : "transparent",
                  borderBottom: "1px solid rgba(255,255,255,0.03)",
                }}
                onMouseEnter={e => { if (r.value !== value) e.currentTarget.style.background = "rgba(255,255,255,0.04)"; }}
                onMouseLeave={e => { if (r.value !== value) e.currentTarget.style.background = "transparent"; }}
              >
                <span style={{ fontSize: 12, fontWeight: 600, color: r.value === value ? "oklch(0.85 0.15 155)" : "oklch(0.82 0.06 200)", flexShrink: 0 }}>{r.value}</span>
                <span style={{ fontSize: 11, color: "oklch(0.5 0.04 220)" }}>{r.label}</span>
              </div>
            ))}
            {filtered.length === 0 && (
              <div style={{ padding: 20, textAlign: "center", color: "oklch(0.4 0.03 220)", fontSize: 12 }}>No regions match</div>
            )}
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}

/* ── InstancePicker ── */
const CAT_LABELS = { general:"General", compute:"Compute", memory:"Memory", gpu:"GPU", hpc:"HPC" };
const CAT_COLORS = {
  general: "oklch(0.65 0.12 200)",
  compute: "oklch(0.65 0.14 150)",
  memory:  "oklch(0.65 0.14 280)",
  gpu:     "oklch(0.65 0.16 60)",
  hpc:     "oklch(0.65 0.14 30)",
};

function InstancePicker({ value, onChange, label }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [filterCat, setFilterCat] = useState("gpu");
  const [filterGpu, setFilterGpu] = useState(false);
  const [minVcpu, setMinVcpu] = useState("");
  const [minMem, setMinMem] = useState("");
  const triggerRef = useRef(null);
  const dropdownRef = useRef(null);
  const [dropdownStyle, setDropdownStyle] = useState({});
  const instances = window.SCALER_INSTANCES || [];

  const filtered = instances.filter(i => {
    if (search && !i.type.toLowerCase().includes(search.toLowerCase())) return false;
    if (filterCat !== "all" && i.cat !== filterCat) return false;
    if (filterGpu && i.gpu === 0) return false;
    if (minVcpu && i.vcpu < parseInt(minVcpu)) return false;
    if (minMem && i.mem < parseFloat(minMem)) return false;
    return true;
  });

  useEffect(() => {
    function handleClick(e) {
      if (
        triggerRef.current && !triggerRef.current.contains(e.target) &&
        dropdownRef.current && !dropdownRef.current.contains(e.target)
      ) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const openDropdown = () => {
    if (!triggerRef.current) return;
    const r = triggerRef.current.getBoundingClientRect();
    setDropdownStyle({
      position: "fixed",
      top: r.bottom + 4,
      left: r.left,
      minWidth: Math.max(540, r.width),
    });
    setOpen(true);
  };

  const selected = instances.find(i => i.type === value);

  const dropdown = (
    <div ref={dropdownRef} style={{
      ...dropdownStyle,
      background: "#0c1219",
      border: "1px solid rgba(0,200,224,0.25)",
      borderRadius: "4px",
      zIndex: 9999,
      boxShadow: "0 16px 48px rgba(0,0,0,0.7)",
    }}>
          {/* Filters */}
          <div style={{ padding: "12px 14px 10px", borderBottom: "1px solid rgba(255,255,255,0.06)", display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center" }}>
            <input
              autoFocus
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search instance type…"
              style={{
                flex: "1 1 140px",
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: "3px",
                padding: "6px 9px",
                color: "oklch(0.88 0.06 200)",
                fontFamily: "inherit",
                fontSize: "12px",
                outline: "none",
              }}
            />
            <input
              value={minVcpu}
              onChange={e => setMinVcpu(e.target.value)}
              placeholder="Min vCPU"
              type="number" min={0}
              style={{ width: 80, background:"rgba(255,255,255,0.04)", border:"1px solid rgba(255,255,255,0.1)", borderRadius:"3px", padding:"6px 8px", color:"oklch(0.88 0.06 200)", fontFamily:"inherit", fontSize:"12px", outline:"none" }}
            />
            <input
              value={minMem}
              onChange={e => setMinMem(e.target.value)}
              placeholder="Min mem"
              type="number" min={0}
              style={{ width: 80, background:"rgba(255,255,255,0.04)", border:"1px solid rgba(255,255,255,0.1)", borderRadius:"3px", padding:"6px 8px", color:"oklch(0.88 0.06 200)", fontFamily:"inherit", fontSize:"12px", outline:"none" }}
            />
            <label style={{ display:"flex", alignItems:"center", gap:5, fontSize:11, color:"oklch(0.6 0.12 60)", cursor:"pointer", userSelect:"none" }}>
              <input type="checkbox" checked={filterGpu} onChange={e => setFilterGpu(e.target.checked)} style={{ accentColor:"oklch(0.75 0.18 60)" }} />
              GPU only
            </label>
          </div>

          {/* Category tabs */}
          <div style={{ display:"flex", gap:0, borderBottom:"1px solid rgba(255,255,255,0.06)" }}>
            {["all","general","compute","memory","gpu","hpc"].map(cat => (
              <button key={cat} onClick={() => setFilterCat(cat)} style={{
                flex: 1,
                background: filterCat===cat ? "rgba(0,200,224,0.1)" : "transparent",
                border: "none",
                borderBottom: filterCat===cat ? "2px solid oklch(0.75 0.18 200)" : "2px solid transparent",
                color: filterCat===cat ? "oklch(0.75 0.18 200)" : "oklch(0.45 0.04 220)",
                fontFamily: "inherit",
                fontSize: "10px",
                padding: "7px 4px",
                cursor: "pointer",
                letterSpacing: "0.05em",
                textTransform: "uppercase",
              }}>
                {cat === "all" ? "All" : CAT_LABELS[cat]}
              </button>
            ))}
          </div>

          {/* Results */}
          <div style={{ maxHeight: 280, overflowY: "auto" }}>
            {filtered.length === 0 && (
              <div style={{ padding:"20px", textAlign:"center", color:"oklch(0.4 0.03 220)", fontSize:12 }}>No instances match</div>
            )}
            <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
              <thead>
                <tr style={{ borderBottom:"1px solid rgba(255,255,255,0.06)" }}>
                  {["Instance","vCPU","Mem (GB)","GPU","Network","$/h"].map(h => (
                    <th key={h} style={{ padding:"6px 10px", color:"oklch(0.4 0.03 220)", fontWeight:500, textAlign:"left", fontSize:10, letterSpacing:"0.05em" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(i => (
                  <tr
                    key={i.type}
                    onClick={() => { onChange(i.type); setOpen(false); }}
                    style={{
                      borderBottom: "1px solid rgba(255,255,255,0.03)",
                      cursor: "pointer",
                      background: i.type === value ? "rgba(0,200,224,0.08)" : (i.featured ? "rgba(255,255,255,0.06)" : "transparent"),
                      transition: "background 0.1s",
                    }}
                    onMouseEnter={e => { if(i.type !== value) e.currentTarget.style.background="rgba(255,255,255,0.08)"; }}
                    onMouseLeave={e => { if(i.type !== value) e.currentTarget.style.background = i.featured ? "rgba(255,255,255,0.06)" : "transparent"; }}
                  >
                    <td style={{ padding:"7px 10px", fontWeight:600, color: i.type===value ? "oklch(0.85 0.15 155)" : "oklch(0.82 0.06 200)" }}>
                      <span style={{ fontSize:10, marginRight:5, color:CAT_COLORS[i.cat] }}>●</span>
                      {i.type}
                    </td>
                    <td style={{ padding:"7px 10px", color:"oklch(0.7 0.05 200)", textAlign:"right" }}>{i.vcpu}</td>
                    <td style={{ padding:"7px 10px", color:"oklch(0.7 0.05 200)", textAlign:"right" }}>{i.mem}</td>
                    <td style={{ padding:"7px 10px", color: i.gpu>0 ? "oklch(0.7 0.16 60)" : "oklch(0.35 0.02 220)" }}>
                      {i.gpu > 0 ? `${i.gpu}× ${i.gpuType} (${i.gpuMem}GB)` : "—"}
                    </td>
                    <td style={{ padding:"7px 10px", color:"oklch(0.55 0.04 220)", fontSize:11 }}>{i.net}</td>
                    <td style={{ padding:"7px 10px", color:"oklch(0.6 0.12 150)", textAlign:"right" }}>${i.price.toFixed(2)}/h</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
  );

  return (
    <div ref={triggerRef} style={{ position: "relative" }}>
      <button
        onClick={() => open ? setOpen(false) : openDropdown()}
        style={{
          width: "100%",
          background: "rgba(0,200,224,0.05)",
          border: "1px solid rgba(0,200,224,0.2)",
          borderRadius: "3px",
          padding: "9px 12px",
          color: value ? "oklch(0.88 0.06 200)" : "oklch(0.45 0.04 220)",
          fontFamily: "inherit",
          fontSize: "13px",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "8px",
          textAlign: "left",
        }}
      >
        <span style={{ flex: 1 }}>
          {value ? (
            <span>
              <span style={{ color: "oklch(0.85 0.15 155)", fontWeight: 600 }}>{value}</span>
              {selected && (
                <span style={{ color: "oklch(0.5 0.04 220)", marginLeft: 10, fontSize: 11 }}>
                  {selected.vcpu} vCPU · {selected.mem} GB{selected.gpu > 0 ? ` · ${selected.gpu}× ${selected.gpuType}` : ""}
                </span>
              )}
            </span>
          ) : (
            <span>Select instance type…</span>
          )}
        </span>
        {selected && <span style={{ color: "oklch(0.6 0.12 150)", fontSize: 11, flexShrink: 0 }}>${selected.price.toFixed(2)}/h</span>}
        <span style={{ color: "oklch(0.5 0.04 220)", fontSize: 10 }}>{open ? "▲" : "▼"}</span>
      </button>
      {open && ReactDOM.createPortal(dropdown, document.body)}
    </div>
  );
}

/* ── TerminalWindow ── */
function TerminalWindow({ lines, config, style }) {
  const [displayed, setDisplayed] = useState([]);
  const endRef = useRef(null);

  useEffect(() => {
    if (!lines || lines.length === 0) return;
    setDisplayed([]);
    const timers = lines.map((line, i) => {
      const text = line.text
        .replace("{schedulerType}", config.schedulerType || "c5.xlarge")
        .replace("{workerType}", config.workerType || "c5.2xlarge")
        .replace("{region}", config.region || "us-east-1");
      return setTimeout(() => {
        setDisplayed(d => [...d, { ...line, text }]);
      }, line.t);
    });
    return () => timers.forEach(clearTimeout);
  }, [lines]);

  useEffect(() => {
    if (endRef.current) endRef.current.scrollTop = endRef.current.scrollHeight;
  }, [displayed]);

  const clsColor = {
    dim:  "oklch(0.38 0.04 220)",
    cmd:  "oklch(0.82 0.16 155)",
    ok:   "oklch(0.72 0.18 150)",
    info: "oklch(0.65 0.06 220)",
    done: "oklch(0.85 0.2 155)",
    addr: "oklch(0.75 0.18 200)",
  };

  return (
    <div style={{
      background: "#050810",
      border: "1px solid rgba(0,255,136,0.15)",
      borderRadius: "4px",
      overflow: "hidden",
      ...style,
    }}>
      {/* Title bar */}
      <div style={{ background:"rgba(0,255,136,0.06)", borderBottom:"1px solid rgba(0,255,136,0.1)", padding:"7px 14px", display:"flex", alignItems:"center", gap:8 }}>
        <span style={{ width:8,height:8,borderRadius:"50%",background:"#ff5f57",display:"inline-block" }}></span>
        <span style={{ width:8,height:8,borderRadius:"50%",background:"#febc2e",display:"inline-block" }}></span>
        <span style={{ width:8,height:8,borderRadius:"50%",background:"#28c840",display:"inline-block" }}></span>
        <span style={{ marginLeft:8, fontSize:11, color:"oklch(0.45 0.05 155)", letterSpacing:"0.08em" }}>openGRIS Scaler — deploy log</span>
      </div>
      {/* Output */}
      <div ref={endRef} style={{
        padding: "14px 16px",
        fontFamily: "inherit",
        fontSize: "12px",
        lineHeight: "1.7",
        minHeight: 400,
        maxHeight: 600,
        overflowY: "auto",
        color: "oklch(0.65 0.06 220)",
      }}>
        {displayed.map((line, i) => (
          <div key={i} style={{
            color: clsColor[line.cls] || "oklch(0.65 0.06 220)",
            fontWeight: line.cls === "done" ? 700 : 400,
            letterSpacing: line.cls === "done" ? "0.08em" : "normal",
          }}>
            {line.text}
          </div>
        ))}
        {displayed.length > 0 && displayed.length < (lines||[]).length && (
          <span style={{ color:"oklch(0.72 0.18 150)", animation:"blink 1s step-end infinite" }}>▌</span>
        )}
      </div>
    </div>
  );
}

/* ── DeployDetails ── */
function CopyButton({ value }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button onClick={copy} title="Copy" style={{
      background: "none", border: "1px solid rgba(0,200,224,0.2)", borderRadius: 3,
      color: copied ? "oklch(0.72 0.18 150)" : "oklch(0.5 0.08 200)",
      fontFamily: "inherit", fontSize: 10, padding: "2px 7px", cursor: "pointer",
      letterSpacing: "0.06em", transition: "color 0.15s, border-color 0.15s",
      flexShrink: 0,
    }}>
      {copied ? "COPIED" : "COPY"}
    </button>
  );
}

function DeployDetails({ visible, style }) {
  if (!visible) return null;
  const fields = [
    { label: "Scheduler Address", value: "54.211.148.92:8080",       href: null },
    { label: "GUI Address",       value: "http://54.211.148.92:3000", href: "http://54.211.148.92:3000" },
  ];
  return (
    <div style={{
      background: "rgba(0,255,136,0.03)",
      border: "1px solid rgba(0,255,136,0.15)",
      borderRadius: "4px",
      padding: "20px 24px",
      ...style,
    }}>
      <div style={{ fontSize:11, letterSpacing:"0.1em", color:"oklch(0.72 0.18 150)", marginBottom:14, textTransform:"uppercase" }}>Deployment Details</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {fields.map(({ label, value, href }) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize:11, color:"oklch(0.42 0.04 220)", letterSpacing:"0.05em", width: 140, flexShrink: 0 }}>{label}</span>
            {href ? (
              <a href={href} target="_blank" rel="noopener noreferrer" style={{
                fontSize: 13, color: "oklch(0.72 0.18 200)", fontWeight: 500,
                fontFamily: "inherit", textDecoration: "none", borderBottom: "1px solid rgba(0,200,224,0.3)",
              }}
                onMouseEnter={e => e.currentTarget.style.color = "oklch(0.85 0.18 200)"}
                onMouseLeave={e => e.currentTarget.style.color = "oklch(0.72 0.18 200)"}
              >{value}</a>
            ) : (
              <span style={{ fontSize: 13, color: "oklch(0.82 0.08 200)", fontWeight: 500, fontFamily: "inherit" }}>{value}</span>
            )}
            <CopyButton value={value} />
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── HelpTip ── */
function HelpTip({ text }) {
  const [btnRect, setBtnRect] = useState(null);
  const [placement, setPlacement] = useState(null); // null = measuring, true = above, false = below
  const btnRef = useRef(null);
  const popupRef = useRef(null);
  const POPUP_WIDTH = 220;

  const open = btnRect !== null;

  useEffect(() => {
    if (!open) return;
    function handleClick(e) {
      if (btnRef.current && !btnRef.current.contains(e.target)) setBtnRect(null);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  // After popup renders invisibly, measure it and decide above/below
  useEffect(() => {
    if (!open || !popupRef.current || placement !== null) return;
    const h = popupRef.current.offsetHeight;
    setPlacement(btnRect.top >= h + 16);
  }, [open, btnRect, placement]);

  const handleOpen = () => {
    if (!btnRef.current) return;
    setBtnRect(btnRef.current.getBoundingClientRect());
    setPlacement(null);
  };

  const sections = text.split(/\n?---\n?/);
  const content = sections.map((section, si) => (
    <React.Fragment key={si}>
      {si > 0 && <hr style={{ border: "none", borderTop: "1px solid rgba(0,200,224,0.15)", margin: "8px 0" }} />}
      {section.split(/\n\n+/).map((para, pi) => (
        <p key={pi} style={{ margin: pi > 0 ? "6px 0 0" : 0 }}>{para}</p>
      ))}
    </React.Fragment>
  ));

  const popup = open && (() => {
    const left = Math.min(
      Math.max(8, btnRect.left + btnRect.width / 2 - POPUP_WIDTH / 2),
      window.innerWidth - POPUP_WIDTH - 8,
    );
    const above = placement === true;
    const posStyle = placement === null
      ? { top: 0, visibility: "hidden" }
      : above
        ? { bottom: window.innerHeight - btnRect.top + 7 }
        : { top: btnRect.bottom + 7 };
    const arrowBorders = above
      ? { borderTop: "none", borderLeft: "none", bottom: -5 }
      : { borderBottom: "none", borderRight: "none", top: -5 };
    const arrowLeft = btnRect.left + btnRect.width / 2 - left - 4;

    return ReactDOM.createPortal(
      <div ref={popupRef} style={{
        position: "fixed",
        left,
        ...posStyle,
        width: POPUP_WIDTH,
        background: "#0c1624",
        border: "1px solid rgba(0,200,224,0.25)",
        borderRadius: 4,
        padding: "10px 12px",
        fontSize: 11,
        lineHeight: 1.65,
        color: "oklch(0.7 0.06 220)",
        zIndex: 2000,
        boxShadow: "0 8px 32px rgba(0,0,0,0.6)",
        pointerEvents: "none",
        textTransform: "none",
        letterSpacing: "normal",
        fontWeight: 400,
      }}>
        {content}
        {placement !== null && (
          <div style={{
            position: "absolute",
            left: arrowLeft,
            transform: "rotate(45deg)",
            width: 8, height: 8,
            background: "#0c1624",
            border: "1px solid rgba(0,200,224,0.25)",
            ...arrowBorders,
          }} />
        )}
      </div>,
      document.body,
    );
  })();

  return (
    <span style={{ display: "inline-flex", alignItems: "center" }}>
      <button
        ref={btnRef}
        onMouseEnter={handleOpen}
        onMouseLeave={() => setBtnRect(null)}
        onClick={() => open ? setBtnRect(null) : handleOpen()}
        style={{
          width: 15, height: 15,
          borderRadius: "50%",
          border: "1px solid rgba(0,200,224,0.35)",
          background: open ? "rgba(0,200,224,0.15)" : "rgba(0,200,224,0.05)",
          color: "oklch(0.62 0.14 200)",
          fontFamily: "inherit",
          fontSize: 9,
          fontWeight: 700,
          cursor: "pointer",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          transition: "background 0.15s, border-color 0.15s",
          lineHeight: 1,
        }}
      >?</button>
      {popup}
    </span>
  );
}

Object.assign(window, { SecretInput, RegionSelect, InstancePicker, TerminalWindow, DeployDetails, HelpTip });
