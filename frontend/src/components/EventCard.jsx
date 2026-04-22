import { useState } from 'react'

const TODAY = new Date().toLocaleDateString('en-CA')

function daysUntil(dateStr) {
  const diff = new Date(dateStr) - new Date(TODAY)
  return Math.ceil(diff / (1000 * 60 * 60 * 24))
}

function urgencyStyle(dateStr) {
  if (!dateStr) return { bg: 'rgba(240,192,64,0.12)', color: '#f0c040', label: 'NO DATE' }
  const d = daysUntil(dateStr)
  if (d < -2)  return { bg: '#26263a', color: '#55556a', label: 'PAST' }
  if (d === -2) return { bg: '#26263a', color: '#55556a', label: 'DUE 2d AGO' }
  if (d === -1) return { bg: '#26263a', color: '#55556a', label: 'DUE YESTERDAY' }
  if (d === 0)  return { bg: '#3d1a1a', color: '#f87171', label: 'TODAY' }
  if (d === 1)  return { bg: '#3d1a1a', color: '#f87171', label: 'IN 1d' }
  if (d === 2)  return { bg: '#3d2510', color: '#fb923c', label: 'IN 2d' }
  if (d <= 7)   return { bg: '#2e2510', color: '#f0c040', label: 'THIS WEEK' }
  return { bg: '#122310', color: '#4ade80', label: 'UPCOMING' }
}

const CATEGORIES = ['school', 'daycare', 'scouts', 'soccer', 'GFT', 'other']

const categoryColors = {
  school:         '#60a5fa',
  daycare:        '#4ade80',
  scouts:         '#f87171',
  soccer:         '#f0c040',
  'GFT':          '#c084fc',
  other:          '#9090a8',
}

export default function EventCard({ event, onDismiss, onDelete, onEdit, isEditing, onEditStart, onEditCancel, requirePin }) {
  const [form, setForm] = useState({
    title:    event.title    || '',
    date:     event.date     || '',
    category: event.category || 'other',
    notes:    event.notes    || '',
  })
  const [confirming, setConfirming] = useState(null) // null | 'dismiss' | 'delete'

  const urgency  = urgencyStyle(event.date)
  const tagColor = categoryColors[event.category] || '#9090a8'
  const dismissed = event.dismissed === true

  function handleSave() {
    onEdit(event.id, form)
  }

  function handleConfirmYes() {
    if (confirming === 'dismiss') onDismiss(event.id)
    else if (confirming === 'delete') onDelete(event.id)
    setConfirming(null)
  }

  if (isEditing) {
    return (
      <div style={cardStyle}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1 }}>
          <input
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="Title"
            style={inputStyle}
          />
          <input
            type="date"
            value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })}
            style={inputStyle}
          />
          <select
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
            style={inputStyle}
          >
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <input
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            placeholder="Notes"
            style={inputStyle}
          />
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={handleSave} style={accentBtnStyle}>Save</button>
            <button onClick={onEditCancel} style={ghostBtnStyle}>Cancel</button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ ...cardStyle, opacity: dismissed ? 0.5 : 1 }} className="event-card">
      {/* Date badge */}
      <div style={{
        width: 60, flexShrink: 0,
        background: dismissed ? '#1e1e2e' : urgency.bg,
        borderRadius: 8,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        padding: '8px 4px', minHeight: 60,
      }}>
        {dismissed ? (
          <span style={{ fontSize: 10, fontWeight: 700, color: '#55556a', textAlign: 'center', letterSpacing: '0.03em' }}>
            ✓ DONE
          </span>
        ) : (
          <>
            <span style={{ fontSize: 10, fontWeight: 700, color: urgency.color, textAlign: 'center', letterSpacing: '0.03em' }}>
              {urgency.label}
            </span>
            {event.date && (
              <span style={{ fontSize: 9, color: '#55556a', marginTop: 2, textAlign: 'center' }}>
                {new Date(event.date + 'T00:00:00').toLocaleDateString('en-CA', { month: 'short', day: 'numeric' })}
              </span>
            )}
          </>
        )}
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{
            fontWeight: 700, fontSize: 15,
            color: dismissed ? '#55556a' : '#eaeaf4',
            textDecoration: dismissed ? 'line-through' : 'none',
          }}>
            {event.title}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: tagColor, background: tagColor + '22', borderRadius: 4, padding: '2px 7px' }}>
            {event.category}
          </span>
          <span style={{ fontSize: 12, color: '#55556a' }}>via {event.source}</span>
        </div>
        {event.notes && (
          <p style={{ fontSize: 13, color: '#9090a8', margin: '6px 0 0', lineHeight: 1.5 }}>{event.notes}</p>
        )}
      </div>

      {/* Action buttons / inline confirm */}
      {confirming ? (
        <div style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end', minWidth: 90 }}>
          <span style={{ fontSize: 11, color: confirming === 'delete' ? '#f87171' : '#9090a8', textAlign: 'right', lineHeight: 1.4 }}>
            {confirming === 'dismiss' ? 'Mark as done?' : 'Delete event?'}
          </span>
          <span style={{ fontSize: 10, color: '#55556a', textAlign: 'right', lineHeight: 1.3 }}>
            {confirming === 'dismiss' ? 'Stays crossed out' : "Can't be undone"}
          </span>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={handleConfirmYes} style={confirming === 'delete' ? confirmDeleteBtnStyle : confirmYesBtnStyle}>Yes</button>
            <button onClick={() => setConfirming(null)} style={confirmNoBtnStyle}>No</button>
          </div>
        </div>
      ) : (
        <div className="event-actions" style={{ display: 'flex', flexDirection: 'column', gap: 6, flexShrink: 0 }}>
          {!dismissed && <button title="Edit" onClick={() => requirePin(() => onEditStart(event.id))} style={iconBtnStyle}>✎</button>}
          {!dismissed && (
            <button title="Mark as done" onClick={() => requirePin(() => setConfirming('dismiss'))} style={iconBtnStyle}>✓</button>
          )}
          <button
            title="Delete"
            onClick={() => requirePin(() => setConfirming('delete'))}
            style={{ ...iconBtnStyle, color: '#f87171' }}
          >✕</button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const cardStyle = {
  display: 'flex',
  gap: 14,
  background: '#1a1a24',
  border: '1px solid #26263a',
  borderRadius: 12,
  padding: '14px 16px',
  marginBottom: 10,
  alignItems: 'flex-start',
}

const iconBtnStyle = {
  background: '#26263a',
  border: 'none',
  borderRadius: 6,
  color: '#9090a8',
  cursor: 'pointer',
  fontSize: 14,
  width: 32,
  height: 32,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  minHeight: 32,
}

const confirmYesBtnStyle = {
  background: '#f0c040',
  border: 'none',
  borderRadius: 6,
  color: '#000',
  cursor: 'pointer',
  fontSize: 12,
  fontWeight: 700,
  padding: '6px 10px',
  minHeight: 44,
}

const confirmDeleteBtnStyle = {
  background: '#f87171',
  border: 'none',
  borderRadius: 6,
  color: '#000',
  cursor: 'pointer',
  fontSize: 12,
  fontWeight: 700,
  padding: '6px 10px',
  minHeight: 44,
}

const confirmNoBtnStyle = {
  background: '#26263a',
  border: 'none',
  borderRadius: 6,
  color: '#9090a8',
  cursor: 'pointer',
  fontSize: 12,
  padding: '6px 10px',
  minHeight: 44,
}

const inputStyle = {
  background: '#26263a',
  border: '1px solid #3a3a52',
  borderRadius: 6,
  color: '#eaeaf4',
  fontSize: 14,
  padding: '8px 10px',
  width: '100%',
  boxSizing: 'border-box',
}

const accentBtnStyle = {
  background: '#f0c040',
  border: 'none',
  borderRadius: 8,
  color: '#000',
  cursor: 'pointer',
  fontWeight: 700,
  padding: '8px 18px',
  minHeight: 44,
}

const ghostBtnStyle = {
  background: '#26263a',
  border: 'none',
  borderRadius: 8,
  color: '#9090a8',
  cursor: 'pointer',
  padding: '8px 18px',
  minHeight: 44,
}