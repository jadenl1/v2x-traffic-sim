import React, { useEffect, useRef, useState, useCallback } from 'react'

// speed (m/s) -> ramp, bright for the dark plate
function speedColor(s) {
  const t = Math.max(0, Math.min(1, s / 14))
  if (t < 0.5) {
    const k = t / 0.5
    return `rgb(${224 + (232 - 224) * k},${72 + (163 - 72) * k},${61 + (58 - 61) * k})`
  }
  const k = (t - 0.5) / 0.5
  return `rgb(${232 + (74 - 232) * k},${163 + (207 - 163) * k},${58 + (140 - 58) * k})`
}

function meanSpeed(frame) {
  if (!frame || frame.length === 0) return 0
  let sum = 0
  for (let i = 2; i < frame.length; i += 3) sum += frame[i]
  return frame.length ? sum / (frame.length / 3) : 0
}

const METRICS = [
  { k: 'Trip travel time', d: '−6.5%' },
  { k: 'Delay per trip', d: '−11.1%' },
  { k: 'Time waiting', d: '−17.2%' },
  { k: 'Mean network speed', d: '+26.0%' },
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
    if (cv.width !== Math.round(cw * dpr) || cv.height !== Math.round(ch * dpr)) {
      cv.width = Math.round(cw * dpr); cv.height = Math.round(ch * dpr)
    }
    const scale = Math.min(cw / w, ch / h)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, cw, ch)
    const ox = (cw - w * scale) / 2, oy = (ch - h * scale) / 2
    const X = (x) => ox + x * scale
    const Y = (y) => oy + (h - y) * scale

    ctx.strokeStyle = 'rgba(255,255,255,0.045)'
    ctx.lineWidth = 1
    ctx.beginPath()
    for (let gx = 0; gx <= w; gx += 500) { ctx.moveTo(X(gx), Y(0)); ctx.lineTo(X(gx), Y(h)) }
    for (let gy = 0; gy <= h; gy += 500) { ctx.moveTo(X(0), Y(gy)); ctx.lineTo(X(w), Y(gy)) }
    ctx.stroke()

    ctx.strokeStyle = 'rgba(255,255,255,0.17)'
    ctx.lineWidth = 1
    ctx.beginPath()
    for (const e of data.network) {
      ctx.moveTo(X(e[0]), Y(e[1]))
      for (let i = 2; i < e.length; i += 2) ctx.lineTo(X(e[i]), Y(e[i + 1]))
    }
    ctx.stroke()

    const fr = frames[idx] || []
    const r = Math.max(1.3, scale * 3)
    for (let i = 0; i < fr.length; i += 3) {
      ctx.fillStyle = speedColor(fr[i + 2])
      ctx.beginPath()
      ctx.arc(X(fr[i]), Y(fr[i + 1]), r, 0, 6.283)
      ctx.fill()
    }

    // scale bar (500 m)
    const bx = ox + 14, by = oy + h * scale - 14, len = 500 * scale
    ctx.strokeStyle = 'rgba(255,255,255,0.4)'; ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(bx, by - 4); ctx.lineTo(bx, by); ctx.lineTo(bx + len, by); ctx.lineTo(bx + len, by - 4)
    ctx.stroke()
    ctx.fillStyle = 'rgba(255,255,255,0.4)'
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
    const v = Number(e.target.value); frameRef.current = v; setFrame(v); draw(v)
  }

  if (err) return <div className="boot">Couldn’t load <code>sim.json</code> — {err}</div>
  if (!data) return <div className="boot">Loading…</div>

  const fr = frames[frame] || []
  const onScreen = Math.round(fr.length / 3)
  const ms = meanSpeed(fr)
  const other = scenario === 'v2x' ? 'baseline' : 'v2x'
  const otherCount = Math.round((data.scenarios[other]?.frames?.[frame]?.length || 0) / 3)
  const delta = onScreen - otherCount
  const clock = new Date((data.window[0] + frame) * 1000).toISOString().substr(11, 8)

  return (
    <div className="app">
      <header className="bar">
        <div className="wm">leonardjaden.development<span>/ v2x-traffic-sim</span></div>
        <a className="src" href="https://github.com/jadenl1/v2x-traffic-sim" target="_blank" rel="noreferrer">source ↗</a>
      </header>

      <main className="grid">
        <aside className="info">
          <div className="eyebrow"><span className="ico" />V2X Traffic Simulation</div>
          <h1>Adaptive signals clear the morning peak <em>11% faster</em>.</h1>
          <p className="desc">A microscopic simulation of downtown Washington, DC — demand
          calibrated to real DDOT counts (GEH&lt;5&nbsp;=&nbsp;83%). The same 7&nbsp;a.m. rush,
          under today’s fixed signals and under vehicle-to-everything coordination.</p>

          <div className="seg" role="tablist">
            {[['baseline', 'Baseline'], ['v2x', 'V2X']].map(([s, lab]) => (
              <button key={s} role="tab" aria-selected={scenario === s}
                className={scenario === s ? 'on' : ''} onClick={() => setScenario(s)}>{lab}</button>
            ))}
          </div>

          <div className="metrics">
            <div className="mh">Full V2X vs fixed control · AM peak</div>
            {METRICS.map((m) => (
              <div className="row" key={m.k}>
                <span className="mk">{m.k}</span>
                <span className="md">{m.d}</span>
              </div>
            ))}
          </div>

          <div className="foot">SUMO 1.27.1 · TraCI max-pressure · scikit-learn / TensorFlow</div>
        </aside>

        <section className="viz">
          <div className="stage">
            <canvas ref={canvasRef} />
            <span className="crop tl" /><span className="crop tr" />
            <span className="crop bl" /><span className="crop br" />
            <div className="ovl tl">T {clock}<br />N {onScreen.toString().padStart(3, '0')} VEH<br />V {ms.toFixed(1)} M/S</div>
            <div className="ovl tr">{scenario === 'v2x' ? 'V2X' : 'BASE'}·{frame.toString().padStart(3, '0')}</div>
            <div className="ovl br">Δ {delta === 0 ? '±0' : (delta < 0 ? '−' : '+') + Math.abs(delta)} VS {other === 'v2x' ? 'V2X' : 'BASE'}</div>
          </div>
          <div className="rail">
            <button className="play" onClick={() => setPlaying((p) => !p)}
              aria-label={playing ? 'pause' : 'play'}>{playing ? '❚❚' : '▶'}</button>
            <input className="scrub" type="range" min={0} max={Math.max(0, nFrames - 1)}
              value={frame} onChange={onScrub} aria-label="timeline" />
            <div className="fc">{String(frame + 1).padStart(3, '0')}/{nFrames}</div>
            <div className="rate">
              {[1, 2, 4, 8].map((x) => (
                <button key={x} className={speed === x ? 'on' : ''} onClick={() => setSpeed(x)}>{x}×</button>
              ))}
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}
