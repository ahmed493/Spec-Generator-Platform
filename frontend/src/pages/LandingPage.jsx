import { useState, useEffect } from 'react'
import {
  Database, GitBranch, Zap, Sun, Moon, ArrowRight, ChevronRight,
} from 'lucide-react'

/* ─────────────────────────────────────────────
   Constants
───────────────────────────────────────────── */
const JEMS_GRADIENT =
  'linear-gradient(105deg, #2a1a4e 0%, #7b1fa2 25%, #e91e8c 55%, #ff6f00 85%, #ffab40 100%)'

const FEATURES = [
  {
    icon: Database,
    title: 'Data Connections',
    desc: 'Connect to GitHub, BigQuery, PostgreSQL, Power BI and Cloud Storage — all in one unified hub.',
    accent: '#e91e8c',
  },
  {
    icon: GitBranch,
    title: 'Project Pipelines',
    desc: 'Automatically detect, map and generate polished technical specs from your data pipelines.',
    accent: '#ff6f00',
  },
]

const KEYFRAMES = `
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@400;500&display=swap');

  @keyframes orb1 {
    0%   { transform: translate(0,    0)   scale(1);    }
    100% { transform: translate(-40px, 60px) scale(1.15); }
  }
  @keyframes orb2 {
    0%   { transform: translate(0,   0)    scale(1);   }
    100% { transform: translate(50px,-40px) scale(1.1); }
  }
  @keyframes orb3 {
    0%   { transform: translate(0,   0)   scale(1);   }
    100% { transform: translate(-30px,30px) scale(1.2); }
  }
  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(20px); }
    to   { opacity: 1; transform: translateY(0);    }
  }
  @keyframes shimmer {
    0%   { background-position: -200% center; }
    100% { background-position:  200% center; }
  }
  @keyframes pulseDot {
    0%, 100% { opacity: 1;   }
    50%       { opacity: 0.4; }
  }
`

/* ─────────────────────────────────────────────
   Component
───────────────────────────────────────────── */
const LandingPage = ({ onEnter, dark, toggleTheme }) => {
  const [mounted, setMounted] = useState(false)
  const [hoveredCard, setHoveredCard] = useState(null)

  useEffect(() => {
    /* Inject keyframes + Google Fonts once */
    const styleId = 'jems-landing-kf'
    if (!document.getElementById(styleId)) {
      const el = document.createElement('style')
      el.id = styleId
      el.textContent = KEYFRAMES
      document.head.appendChild(el)
    }

    /* Enter-key shortcut */
    const handleKey = (e) => { if (e.key === 'Enter') onEnter() }
    window.addEventListener('keydown', handleKey)

    /* Stagger-in */
    const t = setTimeout(() => setMounted(true), 60)

    return () => {
      window.removeEventListener('keydown', handleKey)
      clearTimeout(t)
    }
  }, [onEnter])

  /* ── Theme tokens ── */
  const bg         = dark ? '#0b0b14'                     : '#f4f2f8'
  const textPrimary = dark ? '#ffffff'                    : '#0f0f1a'
  const textMuted   = dark ? 'rgba(255,255,255,0.5)'      : 'rgba(0,0,0,0.5)'
  const cardBg      = dark ? 'rgba(255,255,255,0.04)'     : 'rgba(255,255,255,0.7)'
  const cardBorder  = dark ? 'rgba(255,255,255,0.1)'      : 'rgba(0,0,0,0.08)'
  const navBg       = dark ? 'rgba(11,11,20,0.72)'        : 'rgba(244,242,248,0.72)'
  const navBorder   = dark ? 'rgba(255,255,255,0.07)'     : 'rgba(0,0,0,0.07)'
  const kbdBg       = dark ? 'rgba(255,255,255,0.08)'     : 'rgba(0,0,0,0.07)'
  const kbdBorder   = dark ? 'rgba(255,255,255,0.15)'     : 'rgba(0,0,0,0.15)'
  const secBtnBorder = dark ? 'rgba(255,255,255,0.18)'    : 'rgba(0,0,0,0.18)'

  return (
    <div
      style={{
        position: 'relative',
        minHeight: '100vh',
        background: bg,
        color: textPrimary,
        fontFamily: "'DM Sans', sans-serif",
        overflowX: 'hidden',
        transition: 'background 0.3s ease, color 0.3s ease',
      }}
    >
      {/* ── Top gradient strip ── */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: 4,
        background: JEMS_GRADIENT, zIndex: 10,
      }} />

      {/* ── Noise overlay ── */}
      <svg
        aria-hidden="true"
        style={{
          position: 'absolute', inset: 0, width: '100%', height: '100%',
          opacity: 0.18, mixBlendMode: 'overlay', pointerEvents: 'none', zIndex: 1,
        }}
        xmlns="http://www.w3.org/2000/svg"
      >
        <filter id="jems-noise">
          <feTurbulence type="fractalNoise" baseFrequency="0.75" numOctaves="4" stitchTiles="stitch" />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <rect width="100%" height="100%" filter="url(#jems-noise)" />
      </svg>

      {/* ── Ambient orbs ── */}
      <div style={{
        position: 'absolute', top: '-10%', right: '-5%',
        width: '55vw', height: '55vw', borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(233,30,140,0.18) 0%, transparent 70%)',
        animation: 'orb1 8s ease-in-out alternate infinite',
        zIndex: 0, pointerEvents: 'none',
      }} />
      <div style={{
        position: 'absolute', bottom: '-15%', left: '-10%',
        width: '60vw', height: '60vw', borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(156,39,176,0.16) 0%, transparent 70%)',
        animation: 'orb2 10s ease-in-out alternate infinite',
        zIndex: 0, pointerEvents: 'none',
      }} />
      <div style={{
        position: 'absolute', top: '40%', right: '20%',
        width: '30vw', height: '30vw', borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(255,111,0,0.14) 0%, transparent 70%)',
        animation: 'orb3 12s ease-in-out alternate infinite',
        zIndex: 0, pointerEvents: 'none',
      }} />

      {/* ─────────── Content layer ─────────── */}
      <div style={{ position: 'relative', zIndex: 2 }}>

        {/* ── Navbar ── */}
        <nav style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 32px', height: 64,
          borderBottom: `1px solid ${navBorder}`,
          backdropFilter: 'blur(14px)',
          background: navBg,
          position: 'sticky', top: 4, zIndex: 20,
        }}>
          {/* Logo + wordmark */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: JEMS_GRADIENT,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: "'Syne', sans-serif", fontWeight: 800, fontSize: 18,
              color: '#fff', flexShrink: 0, userSelect: 'none',
            }}>J</div>
            <div>
              <div style={{
                fontFamily: "'Syne', sans-serif", fontWeight: 800,
                fontSize: 16, letterSpacing: '-0.02em', lineHeight: 1.1,
                color: textPrimary,
              }}>
                Jems
              </div>
              <div style={{ fontFamily: 'monospace', fontSize: 10, color: textMuted, letterSpacing: '0.05em' }}>
                Spec Generator
              </div>
            </div>
          </div>

          {/* Version badge + theme toggle */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 7,
              background: dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)',
              border: `1px solid ${dark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'}`,
              borderRadius: 999, padding: '5px 12px',
              fontSize: 12, fontFamily: 'monospace', color: textPrimary,
            }}>
              <div style={{
                width: 7, height: 7, borderRadius: '50%',
                background: '#22c55e', flexShrink: 0,
                animation: 'pulseDot 2s ease-in-out infinite',
              }} />
              v2.4.1 · Live
            </div>
            <button
              onClick={toggleTheme}
              title="Toggle theme"
              style={{
                background: 'none',
                border: `1px solid ${cardBorder}`,
                borderRadius: 8, padding: '6px 8px',
                cursor: 'pointer', color: textMuted,
                display: 'flex', alignItems: 'center',
                transition: 'border-color 0.2s, color 0.2s',
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = '#e91e8c'; e.currentTarget.style.color = '#e91e8c' }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = cardBorder; e.currentTarget.style.color = textMuted }}
            >
              {dark ? <Sun size={15} /> : <Moon size={15} />}
            </button>
          </div>
        </nav>

        {/* ── Hero ── */}
        <section style={{
          maxWidth: 1100, margin: '0 auto',
          padding: '80px 32px 64px',
          textAlign: 'center',
          opacity: mounted ? 1 : 0,
          transform: mounted ? 'translateY(0)' : 'translateY(24px)',
          transition: 'opacity 0.65s ease, transform 0.65s ease',
        }}>
          {/* Pill badge */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            background: 'rgba(233,30,140,0.1)',
            border: '1px solid rgba(233,30,140,0.32)',
            borderRadius: 999, padding: '5px 14px',
            marginBottom: 28,
            fontSize: 13, color: '#e91e8c', fontWeight: 500,
          }}>
            <Zap size={13} style={{ flexShrink: 0 }} />
            We Make Data Ingenious
          </div>

          {/* H1 */}
          <h1 style={{
            fontFamily: "'Syne', sans-serif",
            fontWeight: 800,
            fontSize: 'clamp(2.8rem, 6vw, 5rem)',
            letterSpacing: '-0.04em',
            lineHeight: 1.1,
            margin: '0 0 24px',
          }}>
            <span style={{ color: textPrimary, display: 'block' }}>Your data,</span>
            <span style={{
              display: 'block',
              background: JEMS_GRADIENT,
              backgroundSize: '200% auto',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              animation: 'shimmer 4s linear infinite',
            }}>
              finally ingenious.
            </span>
          </h1>

          {/* Subheadline */}
          <p style={{
            fontSize: 18,
            color: textMuted,
            maxWidth: 560,
            margin: '0 auto 36px',
            lineHeight: 1.65,
            fontFamily: "'DM Sans', sans-serif",
          }}>
            Automatically detect, map and document your data pipelines — from raw sources
            to polished technical specifications, at the speed of thought.
          </p>

          {/* CTA row */}
          <div style={{
            display: 'flex', gap: 12,
            justifyContent: 'center', flexWrap: 'wrap',
            marginBottom: 20,
          }}>
            <button
              onClick={onEnter}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 8,
                background: JEMS_GRADIENT,
                border: 'none', borderRadius: 12, padding: '13px 28px',
                fontSize: 15, fontFamily: "'Syne', sans-serif", fontWeight: 700,
                color: '#fff', cursor: 'pointer',
                boxShadow: '0 4px 24px rgba(233,30,140,0.35)',
                transition: 'transform 0.15s ease, box-shadow 0.15s ease',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.transform = 'translateY(-2px)'
                e.currentTarget.style.boxShadow = '0 8px 36px rgba(233,30,140,0.5)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.transform = 'translateY(0)'
                e.currentTarget.style.boxShadow = '0 4px 24px rgba(233,30,140,0.35)'
              }}
            >
              Enter Platform <ArrowRight size={16} />
            </button>

            <button
              onClick={() => onEnter('connections')}
              style={{
                border: `1px solid ${secBtnBorder}`,
                borderRadius: 12, padding: '13px 24px',
                fontSize: 15, fontFamily: "'DM Sans', sans-serif", fontWeight: 500,
                color: textPrimary, cursor: 'pointer',
                transition: 'border-color 0.2s ease, background 0.2s ease',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = 'rgba(233,30,140,0.5)'
                e.currentTarget.style.background  = 'rgba(233,30,140,0.06)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = secBtnBorder
                e.currentTarget.style.background  = 'transparent'
              }}
            >
              View Connections <ChevronRight size={16} />
            </button>
          </div>

          {/* Keyboard hint */}
          <div style={{
            display: 'flex', alignItems: 'center',
            justifyContent: 'center', gap: 6,
            fontSize: 12, color: textMuted,
          }}>
            Press
            <kbd style={{
              fontFamily: 'monospace', fontSize: 11,
              background: kbdBg,
              border: `1px solid ${kbdBorder}`,
              borderRadius: 5, padding: '2px 8px',
              color: textPrimary,
            }}>
              Enter
            </kbd>
            to access the platform
          </div>
        </section>

        {/* ── Divider ── */}
        <div style={{
          maxWidth: 900, margin: '0 auto 60px',
          height: 1,
          background: 'linear-gradient(90deg, transparent, rgba(233,30,140,0.4), rgba(255,111,0,0.4), transparent)',
        }} />

        {/* ── Feature Grid ── */}
        <section style={{ maxWidth: 1100, margin: '0 auto', padding: '0 32px 88px' }}>
          <p style={{
            fontFamily: 'monospace', fontSize: 11, fontWeight: 700,
            letterSpacing: '0.12em', textTransform: 'uppercase',
            color: textMuted, marginBottom: 24, textAlign: 'center',
          }}>
            Platform Capabilities
          </p>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 16,
          }}>
            {FEATURES.map((feat, i) => {
              const Icon = feat.icon
              const hovered = hoveredCard === i
              return (
                <div
                  key={feat.title}
                  onMouseEnter={() => setHoveredCard(i)}
                  onMouseLeave={() => setHoveredCard(null)}
                  style={{
                    background: hovered
                      ? (dark ? 'rgba(255,255,255,0.07)' : 'rgba(255,255,255,0.88)')
                      : cardBg,
                    border: `1px solid ${hovered ? feat.accent + '88' : cardBorder}`,
                    backdropFilter: 'blur(12px)',
                    borderRadius: 16,
                    padding: '24px 22px',
                    cursor: 'default',
                    transform: hovered ? 'translateY(-4px)' : 'translateY(0)',
                    boxShadow: hovered ? `0 8px 32px ${feat.accent}33` : 'none',
                    transition: 'transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease, background 0.2s ease',
                    animation: mounted ? `fadeUp 0.5s ease ${i * 80}ms both` : 'none',
                  }}
                >
                  <div style={{
                    width: 42, height: 42, borderRadius: 10,
                    background: feat.accent + '22',
                    border: `1px solid ${feat.accent}44`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    marginBottom: 14, flexShrink: 0,
                  }}>
                    <Icon size={20} style={{ color: feat.accent }} />
                  </div>
                  <div style={{
                    fontFamily: "'Syne', sans-serif", fontWeight: 600,
                    fontSize: 15, letterSpacing: '-0.01em',
                    color: textPrimary, marginBottom: 8,
                  }}>
                    {feat.title}
                  </div>
                  <div style={{
                    fontFamily: "'DM Sans', sans-serif",
                    fontSize: 13.5, color: textMuted, lineHeight: 1.6,
                  }}>
                    {feat.desc}
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        {/* ── Footer ── */}
        <footer style={{
          borderTop: `1px solid ${navBorder}`,
          display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', flexWrap: 'wrap', gap: 8,
          padding: '16px 32px',
        }}>
          <span style={{ fontSize: 12, color: textMuted, fontFamily: "'DM Sans', sans-serif" }}>
            ©Jems 2026 · Tous droits réservés
          </span>
          <span style={{ fontSize: 12, color: textMuted, fontFamily: 'monospace' }}>
            www.jems-group.com
          </span>
        </footer>
      </div>
    </div>
  )
}

export default LandingPage
