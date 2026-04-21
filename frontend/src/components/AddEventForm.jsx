import { useState } from 'react'

const TODAY = new Date().toISOString().slice(0, 10)

const CATEGORIES = ['school', 'daycare', 'soccer', 'martial arts', 'activities', 'other']

const EMPTY = { title: '', date: '', category: 'school', source: '', notes: '' }

export default function AddEventForm({ onAdd, onClose }) {
  const [form, setForm] = useState(EMPTY)
  const [errors, setErrors] = useState({})

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }))
    if (errors[field]) setErrors((e) => ({ ...e, [field]: null }))
  }

  function validate() {
    const e = {}
    if (!form.title.trim())    e.title    = 'Title is required'
    if (!form.date)            e.date     = 'Date is required'
    if (!form.category)        e.category = 'Category is required'
    return e
  }

  function handleSubmit(ev) {
    ev.preventDefault()
    const e = validate()
    if (Object.keys(e).length) { setErrors(e); return }
    onAdd({
      title:    form.title.trim(),
      date:     form.date,
      category: form.category,
      source:   form.source.trim() || 'Manual',
      notes:    form.notes.trim(),
      priority: 'medium',
      dismissed:      false,
      manually_added: true,
    })
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0,
        background: '#000000aa',
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'center',
        zIndex: 200,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#1a1a24',
          border: '1px solid #26263a',
          borderRadius: '16px 16px 0 0',
          padding: '24px 20px 32px',
          width: '100%',
          maxWidth: 820,
          animation: 'slideUp 0.2s ease-out',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: '#eaeaf4' }}>Add Event</h2>
          <button onClick={onClose} style={closeBtnStyle}>✕</button>
        </div>

        <form onSubmit={handleSubmit} noValidate>
          <Field label="Title *" error={errors.title}>
            <input
              autoFocus
              value={form.title}
              onChange={(e) => set('title', e.target.value)}
              placeholder="e.g. Picture Day"
              style={{ ...inputStyle, borderColor: errors.title ? '#f87171' : '#3a3a52' }}
            />
          </Field>

          <Field label="Date *" error={errors.date}>
            <input
              type="date"
              value={form.date}
              min={TODAY}
              onChange={(e) => set('date', e.target.value)}
              style={{ ...inputStyle, borderColor: errors.date ? '#f87171' : '#3a3a52' }}
            />
          </Field>

          <Field label="Category *" error={errors.category}>
            <select
              value={form.category}
              onChange={(e) => set('category', e.target.value)}
              style={{ ...inputStyle, borderColor: errors.category ? '#f87171' : '#3a3a52' }}
            >
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>

          <Field label="Source">
            <input
              value={form.source}
              onChange={(e) => set('source', e.target.value)}
              placeholder="e.g. Sarah"
              style={inputStyle}
            />
          </Field>

          <Field label="Notes">
            <input
              value={form.notes}
              onChange={(e) => set('notes', e.target.value)}
              placeholder="e.g. Bring insurance card"
              style={inputStyle}
            />
          </Field>

          <div style={{ display: 'flex', gap: 10, marginTop: 24 }}>
            <button type="submit" style={accentBtnStyle}>Add Event</button>
            <button type="button" onClick={onClose} style={ghostBtnStyle}>Cancel</button>
          </div>
        </form>
      </div>

      <style>{`
        @keyframes slideUp {
          from { transform: translateY(100%); opacity: 0; }
          to   { transform: translateY(0);    opacity: 1; }
        }
      `}</style>
    </div>
  )
}

function Field({ label, error, children }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: 'block', fontSize: 12, color: '#9090a8', marginBottom: 5, fontWeight: 600 }}>
        {label}
      </label>
      {children}
      {error && <div style={{ fontSize: 11, color: '#f87171', marginTop: 4 }}>{error}</div>}
    </div>
  )
}

const inputStyle = {
  width: '100%',
  background: '#26263a',
  border: '1px solid #3a3a52',
  borderRadius: 8,
  color: '#eaeaf4',
  fontSize: 15,
  padding: '10px 12px',
  outline: 'none',
  appearance: 'none',
  WebkitAppearance: 'none',
}

const accentBtnStyle = {
  flex: 1,
  background: '#f0c040',
  border: 'none',
  borderRadius: 10,
  color: '#000',
  cursor: 'pointer',
  fontSize: 15,
  fontWeight: 700,
  padding: '12px 0',
  minHeight: 44,
}

const ghostBtnStyle = {
  flex: 1,
  background: '#26263a',
  border: 'none',
  borderRadius: 10,
  color: '#9090a8',
  cursor: 'pointer',
  fontSize: 15,
  padding: '12px 0',
  minHeight: 44,
}

const closeBtnStyle = {
  background: 'none',
  border: 'none',
  color: '#55556a',
  cursor: 'pointer',
  fontSize: 18,
  padding: 4,
  minHeight: 44,
  minWidth: 44,
}