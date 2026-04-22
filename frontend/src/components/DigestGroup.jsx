import { useState } from 'react'

const CATEGORY_META = {
  school:         { color: '#60a5fa', icon: '🏫' },
  daycare:        { color: '#4ade80', icon: '🌻' },
  scouts:         { color: '#f87171', icon: '🎯' },
  soccer:         { color: '#f0c040', icon: '⚽' },
  'GFT':          { color: '#c084fc', icon: '🥋' },
  other:          { color: '#9090a8', icon: '📬' },
}

export default function DigestGroup({ group }) {
  const { source, category, week_of, bullets = [] } = group
  const meta = CATEGORY_META[category] || CATEGORY_META.other
  const [expanded, setExpanded] = useState(() => window.innerWidth > 768)

  return (
    <div style={{
      background: '#1a1a24',
      border: '1px solid #26263a',
      borderLeft: `3px solid ${meta.color}`,
      borderRadius: 12,
      marginBottom: 10,
      overflow: 'hidden',
    }}>
      {/* Header */}
      <button
        onClick={() => setExpanded((v) => !v)}
        style={{
          width: '100%',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '14px 16px',
          textAlign: 'left',
          minHeight: 44,
        }}
      >
        <span style={{ fontSize: 18, lineHeight: 1 }}>{meta.icon}</span>
        <span style={{ fontWeight: 700, fontSize: 15, color: '#eaeaf4', flex: 1 }}>{source}</span>
        <span style={{
          fontSize: 11, fontWeight: 600,
          color: meta.color,
          background: meta.color + '22',
          borderRadius: 4,
          padding: '2px 7px',
        }}>
          {category}
        </span>
        <span style={{
          color: '#55556a',
          fontSize: 13,
          marginLeft: 4,
          display: 'inline-block',
          transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
          transition: 'transform 0.2s',
        }}>▼</span>
      </button>

      {/* Collapsible body */}
      <div style={{
        maxHeight: expanded ? 1000 : 0,
        overflow: 'hidden',
        transition: 'max-height 0.25s ease',
      }}>
        <div style={{ padding: '0 16px 16px' }}>
          {week_of && (
            <div style={{ fontSize: 11, color: '#55556a', marginBottom: 10 }}>
              Week of {new Date(week_of + 'T00:00:00').toLocaleDateString('en-CA', { month: 'long', day: 'numeric', year: 'numeric' })}
            </div>
          )}
          {bullets.map((bullet, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
              <span style={{ color: meta.color, flexShrink: 0, fontSize: 14, lineHeight: 1.6 }}>›</span>
              <span style={{ fontSize: 13, color: '#9090a8', lineHeight: 1.6 }}>{bullet}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}