import React, { useEffect, useRef, useState, useCallback } from 'react'

// speed (m/s) -> ramp, deepened for legibility on the white plate
function speedColor(s) {
  const t = Math.max(0, Math.min(1, s / 14))
  if (t < 0.5) {
    const k = t / 0.5
    return `rgb(${222 + (198 - 222) * k},${42 + (122 - 42) * k},${34 + (18 - 34) * k})`
  }
  const k = (t - 0.5) / 0.5
  return `rgb(${198 + (18 - 198) * k},${122 + (146 - 122) * k},${18 + (90 - 18) * k})`
}

function meanSpeed(frame) {
  if (!frame || frame.length === 0) return 0
  let sum = 0
  for (let i = 2; i < frame.length; i += 3) sum += frame[i]
  return frame.length ? sum / (frame.length / 3) : 0
}

const FINDINGS = [
  { i: '01', k: 'Trip travel time', from: '348 s', to: '325 s', d: '−6.5%' },
  { i: '02', k: 'Delay per trip', from: '275 s', to: '244 s', d: '−11.1%' },
  { i: '03', k: 'Time waiting', from: '220 s', to: '182 s', d: '−17.2%' },
  { i: '04', k: 'Mean network speed', from: '11.9 mph', to: '15.1 mph', d: '+26.0%' },
]

export default function SimViewer() {
  const canvasRef = useRef(null)
  const rafRef = useRef(0)
  const frameRef = useRef(0)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [scenario, setScenario] = useState('v2x')
  const [playing, setPlaying] = useState(true)
  const [speed, setSpeed] = useState(2)
  const [frame, setFrame] = useState(0)

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}sim.json`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(setData)
      .catch((e) => setErr(String(e)))
  }, [])

  const frames = data?.scenarios?.[scenario]?.frames ?? []
  const nFrames = frames.length

  const draw = useCallback((idx) => {
    const cv = canvasRef.current
    if (!cv || !data) return
    const ctx = cv.getContext('2d')
    const [w, h] = data.size
    const dpr = window.devicePixelRatio || 1
    const cw = cv.clientWidth, ch = cv.clientHeight
    if (cv.width !== Math.round(cw * dpr)) { cv.width = Math.round(cw * dpr); cv.height = Math.round(ch * dpr) }
    const scale = Math.min(cw / w, ch / h)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, cw, ch)
    const ox = (cw - w * scale) / 2, oy = (ch - h * scale) / 2
    const X = (x) => ox + x * scale
    const Y = (y) => oy + (h - y) * scale

    // coordinate grid, every 500 m
    ctx.strokeStyle = 'rgba(20,24,40,0.05)'
    ctx.lineWidth = 1
    ctx.beginPath()
    for (let gx = 0; gx <= w; gx += 500) { ctx.moveTo(X(gx), Y(0)); ctx.lineTo(X(gx), Y(h)) }
    for (let gy = 0; gy <= h; gy += 500) { ctx.moveTo(X(0), Y(gy)); ctx.lineTo(X(w), Y(gy)) }
    ctx.stroke()

    // road network
    ctx.strokeStyle = 'rgba(24,28,42,0.30)'
    ctx.lineWidth = 1
    ctx.beginPath()
    for (const e of data.network) {
      ctx.moveTo(X(e[0]), Y(e[1]))
      for (let i = 2; i < e.length; i += 2) ctx.lineTo(X(e[i]), Y(e[i + 1]))
    }
    ctx.stroke()

    // vehicles
    const fr = frames[idx] || []
    const r = Math.max(1.4, scale * 3)
    for (let i = 0; i < fr.length; i += 3) {
      ctx.fillStyle = speedColor(fr[i + 2])
      ctx.beginPath()
      ctx.arc(X(fr[i]), Y(fr[i + 1]), r, 0, 6.283)
      ctx.fill()
    }

    // scale bar (500 m) bottom-left
    const bx = ox + 14, by = oy + h * scale - 16, len = 500 * scale
    ctx.strokeStyle = 'rgba(24,28,42,0.65)'; ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(bx, by - 4); ctx.lineTo(bx, by); ctx.lineTo(bx + len, by); ctx.lineTo(bx + len, by - 4)
    ctx.stroke()
    ctx.fillStyle = 'rgba(24,28,42,0.65)'
    ctx.font = '9px "Geist Mono Variable", monospace'
    ctx.fillText('500 M', bx + 4, by - 6)
  }, [data, frames])

  useEffect(() => {
    if (!data) return
    let last = performance.now()
    const tick = (now) => {
      rafRef.current = requestAnimationFrame(tick)
      if (playing && now - last > 90 / speed) {
        last = now
        frameRef.current = (frameRef.current + 1) % (nFrames || 1)
        setFrame(frameRef.current)
      }
      draw(frameRef.current)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [data, playing, speed, nFrames, draw])

  const onScrub = (e) => {
    const v = Number(e.target.value)
    frameRef.current = v; setFrame(v); draw(v)
  }

  if (err) return <div className="boot">FAULT — could not load <code>sim.json</code> ({err}).<br />Run <code>python scripts/11_export_replay.py</code>.</div>
  if (!data) return <div className="boot">INITIALISING…</div>

  const fr = frames[frame] || []
  const onScreen = Math.round(fr.length / 3)
  const ms = meanSpeed(fr)
  const other = scenario === 'v2x' ? 'baseline' : 'v2x'
  const otherCount = Math.round((data.scenarios[other]?.frames?.[frame]?.length || 0) / 3)
  const delta = onScreen - otherCount
  const t0 = data.window[0]
  const clock = new Date((t0 + frame) * 1000).toISOString().substr(11, 8)

  return (
    <div className="doc">
      <header className="topbar">
        <div className="sysid"><span className="dot" />MOBILITY-SYSTEMS-LAB</div>
        <div className="rev">38.9047°N&nbsp;·&nbsp;77.0369°W&nbsp;/&nbsp;SIM-2026.07</div>
      </header>

      <main className="sheet">
        <div className="ix">FIG.01 — VEHICLE-TO-EVERYTHING · SIGNAL COORDINATION</div>
        <h1 className="statement">
          Adaptive signals drain the morning peak <em>11% faster</em> than fixed timing.
        </h1>
        <p className="abstract">
          Microscopic simulation of downtown Washington, DC — demand calibrated to real
          DDOT counts (GEH&lt;5&nbsp;=&nbsp;83%). The same 07:00 peak, replayed under today’s
          fixed-time signals and under vehicle-to-everything coordination.
        </p>

        <section className="fig">
          <div className="fig-head">
            <div className="scen" role="tablist">
              {[['baseline', '0'], ['v2x', '1']].map(([s, n]) => (
                <button key={s} role="tab" aria-selected={scenario === s}
                  className={scenario === s ? 'on' : ''} onClick={() => setScenario(s)}>
                  <span className="br">[</span>{n}<span className="br">]</span>&nbsp;
                  {s === 'v2x' ? 'V2X-COORDINATED' : 'FIXED-BASELINE'}
                </button>
              ))}
            </div>
            <div className="lamp"><span className="rec" />LIVE · 1&nbsp;Hz · SUMO-FCD</div>
          </div>

          <div className="stage">
            <canvas ref={canvasRef} />
            <span className="crop tl" /><span className="crop tr" />
            <span className="crop bl" /><span className="crop br" />
            <div className="ovl tl">
              T {clock}<br />N {onScreen.toString().padStart(3, '0')} VEH<br />
              V {ms.toFixed(1)} M/S
            </div>
            <div className="ovl tr">{scenario === 'v2x' ? 'V2X' : 'BASE'}·{frame.toString().padStart(3, '0')}</div>
            <div className="ovl br">Δ {delta === 0 ? '±0' : (delta < 0 ? '−' : '+') + Math.abs(delta)} VS {other === 'v2x' ? 'V2X' : 'BASE'}</div>
          </div>

          <div className="rail">
            <button className="play" onClick={() => setPlaying((p) => !p)}
              aria-label={playing ? 'pause' : 'play'}>{playing ? '❚❚' : '▶'}</button>
            <div className="track">
              <input className="scrub" type="range" min={0} max={Math.max(0, nFrames - 1)}
                value={frame} onChange={onScrub} aria-label="timeline" />
              <div className="ticks" aria-hidden="true" />
            </div>
            <div className="fcount">{String(frame + 1).padStart(3, '0')}/{nFrames}</div>
            <div className="rate">
              {[1, 2, 4, 8].map((x) => (
                <button key={x} className={speed === x ? 'on' : ''} onClick={() => setSpeed(x)}>{x}×</button>
              ))}
            </div>
          </div>

          <p className="cap">
            Each mark is one vehicle, coloured by instantaneous speed. Reds pool at
            saturated intersections; greens run the arterials. {data.network.length.toLocaleString()} road
            segments · window {data.window[0]}–{data.window[1]}s · 1&nbsp;Hz from SUMO floating-car data.
          </p>
        </section>

        <section className="spec">
          <div className="spec-h">RESULTS — FULL-V2X vs FIXED CONTROL, AM PEAK</div>
          <table>
            <tbody>
              {FINDINGS.map((f) => (
                <tr key={f.i}>
                  <td className="i">{f.i}</td>
                  <td className="k">{f.k}</td>
                  <td className="fromto">{f.from}<span>→</span>{f.to}</td>
                  <td className="dl">{f.d}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="fine">
            Gains from adaptive signal coordination (V2I) + cooperative rerouting (V2V),
            identical demand. Trade-off: the adaptive controller teleports ~⅓ more stranded
            vehicles than fixed timing — the next parameter to tighten.
          </p>
        </section>

        <footer className="colo">
          <span>SUMO 1.27.1 / TraCI MAX-PRESSURE / SCIKIT-LEARN + TENSORFLOW</span>
          <span>DDOT AADT · GEH&lt;5 = 83%</span>
        </footer>
      </main>
    </div>
  )
}
