const BIN_ID = import.meta.env.VITE_JSONBIN_BIN_ID;
const API_KEY = import.meta.env.VITE_JSONBIN_API_KEY;
const BASE_URL = `https://api.jsonbin.io/v3/b/${BIN_ID}`;

const READ_HEADERS = {
  "X-Master-Key": API_KEY,
};

const WRITE_HEADERS = {
  "Content-Type": "application/json",
  "X-Master-Key": API_KEY,
};

async function checkResponse(resp, context) {
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new Error(`JSONBin ${context} failed (${resp.status}): ${body}`);
  }
  return resp;
}

// ---------------------------------------------------------------------------
// Core read / write
// ---------------------------------------------------------------------------

export async function loadData() {
  const resp = await fetch(`${BASE_URL}/latest`, { headers: READ_HEADERS });
  await checkResponse(resp, "read");
  const json = await resp.json();
  const record = json.record ?? {};
  return {
    events: record.events ?? [],
    digestGroups: record.digestGroups ?? [],
    lastScanned: record.lastScanned ?? null,
  };
}

export async function saveData(data) {
  const resp = await fetch(BASE_URL, {
    method: "PUT",
    headers: WRITE_HEADERS,
    body: JSON.stringify(data),
  });
  await checkResponse(resp, "write");
  return resp.json();
}

// ---------------------------------------------------------------------------
// Mutation helpers — each loads, mutates, saves, returns updated data
// ---------------------------------------------------------------------------

export async function dismissEvent(eventId) {
  const data = await loadData();
  const events = data.events.map((e) =>
    e.id === eventId ? { ...e, dismissed: true } : e
  );
  await saveData({ ...data, events });
  return { ...data, events };
}

export async function deleteEvent(eventId) {
  const data = await loadData();
  const events = data.events.filter((e) => e.id !== eventId);
  await saveData({ ...data, events });
  return { ...data, events };
}

export async function addEvent(eventObj) {
  const data = await loadData();
  const newEvent = {
    ...eventObj,
    id: "manual_" + Date.now(),
    manually_added: true,
    dismissed: false,
  };
  const events = [...data.events, newEvent];
  await saveData({ ...data, events });
  return { ...data, events };
}

export async function updateEvent(eventId, fields) {
  const data = await loadData();
  const events = data.events.map((e) =>
    e.id === eventId ? { ...e, ...fields } : e
  );
  await saveData({ ...data, events });
  return { ...data, events };
}