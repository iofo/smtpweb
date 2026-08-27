const appEl = document.getElementById("app");
const POLL_INTERVAL_MS = 10000;
let currentUsername = null;
let selectedId = null;
let refreshTimer = null;

const ICONS = {
  mail: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg>`,
  mailOpen: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9 6 9-6"/><path d="M3 9v9a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V9l-9-6-9 6Z"/></svg>`,
  refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>`,
  logout: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>`,
  paperclip: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05 12.25 20.24a5 5 0 0 1-7.07-7.07l9.19-9.19a3.5 3.5 0 0 1 4.95 4.95l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>`,
  download: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg>`,
  close: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="M6 6l12 12"/></svg>`,
};

const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp"]);

function isImageFilename(filename) {
  const ext = (filename.split(".").pop() || "").toLowerCase();
  return IMAGE_EXTENSIONS.has(ext);
}

function isPdfFilename(filename) {
  return filename.toLowerCase().endsWith(".pdf");
}

const AVATAR_PALETTE = [
  "#ef4444", "#f97316", "#eab308", "#22c55e",
  "#14b8a6", "#3b82f6", "#6366f1", "#a855f7", "#ec4899",
];

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function avatarColor(seed) {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
}

function avatarInitial(from) {
  const match = String(from || "?").trim();
  return (match[0] || "?").toUpperCase();
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return escapeHtml(iso);
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  return sameDay
    ? d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
    : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatDateLong(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return escapeHtml(iso);
  return d.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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
        <div class="login-icon">${ICONS.mail}</div>
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
        <button type="submit" class="btn btn-primary" id="login-submit">Log in</button>
        ${errorMessage ? `<p class="error">${escapeHtml(errorMessage)}</p>` : ""}
      </form>
    </div>
  `;
  document.getElementById("login-username").focus();
  document.getElementById("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("login-username").value;
    const password = document.getElementById("login-password").value;
    const submitBtn = document.getElementById("login-submit");
    submitBtn.disabled = true;
    submitBtn.textContent = "Logging in…";
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
        <div class="brand">
          ${ICONS.mail}
          <h1>Inbox</h1>
        </div>
        <div class="header-actions">
          <button class="btn btn-icon" id="refresh" title="Refresh">${ICONS.refresh}</button>
          <button class="btn btn-icon" id="logout" title="Log out">${ICONS.logout}</button>
        </div>
      </header>
      <div id="whoami"></div>
      <ul id="email-list"></ul>
    </aside>
    <main id="detail-pane">
      <div class="placeholder-state">
        ${ICONS.mailOpen}
        <p>Select an email to view it.</p>
      </div>
    </main>
    <div id="lightbox" class="lightbox">
      <button id="lightbox-close" class="lightbox-close" title="Close">${ICONS.close}</button>
      <div id="lightbox-body" class="lightbox-body"></div>
    </div>
  `;
  document.getElementById("whoami").textContent = currentUsername;
  document.getElementById("refresh").addEventListener("click", loadList);
  document.getElementById("logout").addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST" });
    currentUsername = null;
    selectedId = null;
    renderLogin();
  });
  document.getElementById("lightbox-close").addEventListener("click", closeLightbox);
  document.getElementById("lightbox").addEventListener("click", (e) => {
    if (e.target.id === "lightbox") closeLightbox();
  });

  loadList();
  refreshTimer = setInterval(loadList, POLL_INTERVAL_MS);
}

function openLightbox(type, url, name) {
  const body = document.getElementById("lightbox-body");
  body.innerHTML =
    type === "pdf"
      ? `<iframe src="${url}" title="${escapeHtml(name)}"></iframe>`
      : `<img src="${url}" alt="${escapeHtml(name)}" />`;
  document.getElementById("lightbox").classList.add("open");
}

function closeLightbox() {
  const lightbox = document.getElementById("lightbox");
  if (!lightbox) return;
  lightbox.classList.remove("open");
  document.getElementById("lightbox-body").innerHTML = "";
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeLightbox();
});

async function loadList() {
  const res = await fetch("/api/emails");
  if (res.status === 401) {
    renderLogin();
    return;
  }
  const emails = await res.json();
  const listEl = document.getElementById("email-list");

  if (emails.length === 0) {
    listEl.innerHTML = `<li class="empty-list" style="cursor:default">No mail yet.</li>`;
    return;
  }

  listEl.innerHTML = "";
  for (const email of emails) {
    const li = document.createElement("li");
    li.dataset.id = email.id;
    if (email.id === selectedId) li.classList.add("selected");
    const from = email.from || "(unknown sender)";
    li.innerHTML = `
      <div class="avatar" style="background:${avatarColor(from)}">${escapeHtml(avatarInitial(from))}</div>
      <div class="email-row-body">
        <div class="email-row-top">
          <span class="from">${escapeHtml(from)}</span>
          <span class="date">${formatDate(email.received_at)}</span>
        </div>
        <div class="subject">${escapeHtml(email.subject || "(no subject)")}</div>
      </div>
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
    detailEl.innerHTML = `<div class="placeholder-state"><p>Failed to load email.</p></div>`;
    return;
  }
  const email = await res.json();

  let bodyHtml;
  if (email.html_body) {
    bodyHtml = `<iframe sandbox srcdoc="${escapeHtml(email.html_body)}"></iframe>`;
  } else if (email.text_body) {
    bodyHtml = `<pre>${escapeHtml(email.text_body)}</pre>`;
  } else {
    bodyHtml = `<p class="placeholder-state"><em>(no body)</em></p>`;
  }

  let attachmentsHtml = "";
  if (email.attachments && email.attachments.length) {
    const media = email.attachments.filter(
      (a) => isImageFilename(a.filename) || (isPdfFilename(a.filename) && a.has_thumbnail)
    );
    const others = email.attachments.filter((a) => !media.includes(a));

    const mediaHtml = media.length
      ? `<div class="image-attachments">${media
          .map((a) => {
            const url = `/api/emails/${id}/attachments/${encodeURIComponent(a.filename)}`;
            const isPdf = isPdfFilename(a.filename);
            const thumbSrc = isPdf ? `${url}/thumbnail` : url;
            return `
              <div class="image-attachment" data-url="${url}" data-type="${isPdf ? "pdf" : "image"}"
                   data-name="${escapeHtml(a.filename)}" role="button" tabindex="0"
                   title="${escapeHtml(a.filename)} (${formatBytes(a.size)})">
                <img src="${thumbSrc}" alt="${escapeHtml(a.filename)}" loading="lazy" />
                ${isPdf ? `<span class="media-badge">PDF</span>` : ""}
                <a class="media-download" href="${url}" download="${escapeHtml(a.filename)}" title="Download">${ICONS.download}</a>
              </div>
            `;
          })
          .join("")}</div>`
      : "";

    const chips = others
      .map(
        (a) => `
          <a class="attachment-chip" href="/api/emails/${id}/attachments/${encodeURIComponent(a.filename)}" target="_blank">
            ${ICONS.paperclip}
            <span class="name">${escapeHtml(a.filename)}</span>
            <span class="size">${formatBytes(a.size)}</span>
          </a>
        `
      )
      .join("");

    attachmentsHtml = `
      <div class="attachments">
        <div class="attachments-title">${email.attachments.length} Attachment${email.attachments.length === 1 ? "" : "s"}</div>
        ${mediaHtml}
        ${chips}
      </div>
    `;
  }

  detailEl.innerHTML = `
    <h2>${escapeHtml(email.subject || "(no subject)")}</h2>
    <div class="meta">
      <span class="label">From</span><span class="value">${escapeHtml(email.from || "")}</span>
      <span class="label">To</span><span class="value">${escapeHtml((email.to || []).join(", "))}</span>
      <span class="label">Date</span><span class="value">${formatDateLong(email.date || email.received_at)}</span>
    </div>
    ${attachmentsHtml}
    ${bodyHtml}
    <a class="raw-link" href="/api/emails/${id}/raw">${ICONS.download} Download raw .eml</a>
  `;

  detailEl.querySelectorAll(".image-attachment").forEach((el) => {
    const open = () => openLightbox(el.dataset.type, el.dataset.url, el.dataset.name);
    el.addEventListener("click", open);
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        open();
      }
    });
  });
  detailEl.querySelectorAll(".media-download").forEach((el) => {
    el.addEventListener("click", (e) => e.stopPropagation());
  });
}

checkAuth();
