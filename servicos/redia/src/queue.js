const states = new Map();

function key(chatId) {
  return String(chatId || "default");
}

function getQueue(chatId) {
  const k = key(chatId);
  if (!states.has(k)) states.set(k, { processing: false, queue: [] });
  return states.get(k);
}

function enqueue(chatId, item) {
  const state = getQueue(chatId);
  state.queue.push(item);
  return state.queue.length;
}

function drain(chatId) {
  const state = getQueue(chatId);
  const items = state.queue.splice(0, state.queue.length);
  return items;
}

module.exports = { getQueue, enqueue, drain };
