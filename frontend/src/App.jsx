const API = 'http://localhost:8000/api/v1';

const form = document.getElementById('chat-form');
const input = document.getElementById('input');
const messages = document.getElementById('messages');

const history = [];

function addBubble(role, text) {
  const div = document.createElement('div');
  div.className = `bubble ${role}`;
  div.textContent = text;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = input.scrollHeight + 'px';
});

input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  input.style.height = 'auto';
  form.querySelector('button').disabled = true;

  addBubble('user', text);
  history.push({ role: 'user', content: text });

  try {
    const res = await fetch(`${API}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: history }),
    });

    if (!res.ok) throw new Error(`Server error: ${res.status}`);

    const data = await res.json();
    addBubble('assistant', data.reply);
    history.push({ role: 'assistant', content: data.reply });
  } catch (err) {
    addBubble('error', err.message);
  } finally {
    form.querySelector('button').disabled = false;
    input.focus();
  }
});