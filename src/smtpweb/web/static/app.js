const listEl = document.getElementById("email-list");
const detailEl = document.getElementById("detail-pane");
let selectedId = null;

async function loadList() {
  const res = await fetch("/api/emails");
  const emails = await res.json();
  listEl.innerHTML = "";
  for (const email of emails) {
    const li = document.createElement("li");
    li.dataset.id = email.id;
    if (email.id === selectedId) li.classList.add("selected");
    li.innerHTML = `
      <div class="subject">${escapeHtml(email.subject || "(no subject)")}</div>
      <div class="from">${escapeHtml(email.from || "")}</div>
      <div class="date">${escapeHtml(email.received_at || "")}</div>
    `;
    li.addEventListener("click", () => selectEmail(email.id));
    listEl.appendChild(li);
  }
}

async function selectEmail(id) {
  selectedId = id;
  document.querySelectorAll("#email-list li").forEach((li) => {
    li.classList.toggle("selected", li.dataset.id === id);
  });

  const res = await fetch(`/api/emails/${id}`);
  if (!res.ok) {
    detailEl.innerHTML = `<p class="placeholder">Failed to load email.</p>`;
    return;
  }
  const email = await res.json();

  let bodyHtml;
  if (email.html_body) {
    bodyHtml = `<iframe sandbox srcdoc="${escapeHtml(email.html_body)}"></iframe>`;
  } else if (email.text_body) {
    bodyHtml = `<pre>${escapeHtml(email.text_body)}</pre>`;
  } else {
    bodyHtml = `<p class="placeholder">(no body)</p>`;
  }

  let attachmentsHtml = "";
  if (email.attachments && email.attachments.length) {
    const links = email.attachments
      .map(
        (a) =>
          `<a href="/api/emails/${id}/attachments/${encodeURIComponent(a.filename)}" target="_blank">
            ${escapeHtml(a.filename)} (${a.content_type}, ${a.size} bytes)
          </a>`
      )
      .join("");
    attachmentsHtml = `<div class="attachments"><strong>Attachments</strong>${links}</div>`;
  }

  detailEl.innerHTML = `
    <h2>${escapeHtml(email.subject || "(no subject)")}</h2>
    <div class="meta">
      <div><strong>From:</strong> ${escapeHtml(email.from || "")}</div>
      <div><strong>To:</strong> ${escapeHtml((email.to || []).join(", "))}</div>
      <div><strong>Date:</strong> ${escapeHtml(email.date || email.received_at || "")}</div>
    </div>
    ${attachmentsHtml}
    ${bodyHtml}
    <p><a href="/api/emails/${id}/raw">Download raw .eml</a></p>
  `;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

document.getElementById("refresh").addEventListener("click", loadList);

loadList();
setInterval(loadList, 10000);
