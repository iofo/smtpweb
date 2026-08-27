const appEl = document.getElementById("app");
let currentUsername = null;
let selectedId = null;
let refreshTimer = null;

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function checkAuth() {
  const res = await fetch("/api/me");
  if (res.ok) {
    const data = await res.json();
    currentUsername = data.username;
    renderInbox();
  } else {
    renderLogin();
  }
}

function renderLogin(errorMessage) {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
  appEl.innerHTML = `
    <div id="login-screen">
      <form id="login-form">
        <h1>smtpweb</h1>
        <p>
          Log in with the email address whose mail you want to view.
          The first time you log in for a given address, the password
          you enter here becomes that mailbox's password.
        </p>
        <label>Email address
          <input type="email" id="login-username" autocomplete="username" required />
        </label>
        <label>Password
          <input type="password" id="login-password" autocomplete="current-password" required />
        </label>
        <button type="submit">Log in</button>
        ${errorMessage ? `<p class="error">${escapeHtml(errorMessage)}</p>` : ""}
      </form>
    </div>
  `;
  document.getElementById("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("login-username").value;
    const password = document.getElementById("login-password").value;
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (res.ok) {
      const data = await res.json();
      currentUsername = data.username;
      renderInbox();
    } else {
      renderLogin("Wrong password for that mailbox.");
    }
  });
}

function renderInbox() {
  appEl.innerHTML = `
    <aside id="list-pane">
      <header>
        <h1>Inbox</h1>
        <div class="header-actions">
          <span id="whoami"></span>
          <button id="refresh">Refresh</button>
          <button id="logout">Log out</button>
        </div>
      </header>
      <ul id="email-list"></ul>
    </aside>
    <main id="detail-pane">
      <p class="placeholder">Select an email to view it.</p>
    </main>
  `;
  document.getElementById("whoami").textContent = currentUsername;
  document.getElementById("refresh").addEventListener("click", loadList);
  document.getElementById("logout").addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST" });
    currentUsername = null;
    selectedId = null;
    renderLogin();
  });

  loadList();
  refreshTimer = setInterval(loadList, 10000);
}

async function loadList() {
  const res = await fetch("/api/emails");
  if (res.status === 401) {
    renderLogin();
    return;
  }
  const emails = await res.json();
  const listEl = document.getElementById("email-list");
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

  const detailEl = document.getElementById("detail-pane");
  const res = await fetch(`/api/emails/${id}`);
  if (res.status === 401) {
    renderLogin();
    return;
  }
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

checkAuth();
