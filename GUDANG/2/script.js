const state = {
  tree: null,
  current: null,
  path: []
};

const grid = document.getElementById("grid");
const empty = document.getElementById("empty");
const title = document.getElementById("pageTitle");
const breadcrumb = document.getElementById("breadcrumb");
const reader = document.getElementById("reader");
const readerTitle = document.getElementById("readerTitle");
const readerText = document.getElementById("readerText");

function sortChildren(children) {
  const order = { folder: 0, file: 1, link: 2 };

  return [...children].sort((a, b) => {
    if (order[a.type] !== order[b.type]) return order[a.type] - order[b.type];
    return a.name.localeCompare(b.name, "id", {
      numeric: true,
      sensitivity: "base"
    });
  });
}

function findNode(path) {
  let node = state.tree;

  for (const part of path) {
    node = (node.children || []).find(child => child.name === part);
    if (!node) return null;
  }

  return node;
}

function render(path = []) {
  state.path = [...path];
  state.current = findNode(path);

  if (!state.current) return;

  title.textContent = path.length ? path[path.length - 1] : "Beranda";
  breadcrumb.innerHTML = "";

  const home = document.createElement("button");
  home.type = "button";
  home.textContent = "Beranda";
  home.addEventListener("click", () => render([]));
  breadcrumb.appendChild(home);

  path.forEach((part, index) => {
    breadcrumb.appendChild(document.createTextNode("  /  "));

    const crumb = document.createElement("button");
    crumb.type = "button";
    crumb.textContent = part;
    crumb.addEventListener("click", () => render(path.slice(0, index + 1)));
    breadcrumb.appendChild(crumb);
  });

  grid.innerHTML = "";

  const children = sortChildren(state.current.children || []);
  empty.classList.toggle("hidden", children.length !== 0);

  for (const item of children) {
    const button = document.createElement("button");
    button.type = "button";

    const itemClass = item.type === "file" ? "file" : item.type === "link" ? "link" : "";
    button.className = `item ${itemClass}`;

    const icon = document.createElement("div");
    icon.className = "icon";
    icon.textContent =
      item.type === "folder" ? "📁" :
      item.type === "file" ? "📜" : "🔗";

    const name = document.createElement("div");
    name.className = "name";
    name.textContent = item.name.replace(/\.(txt|link)$/i, "");

    const type = document.createElement("div");
    type.className = "type";
    type.textContent =
      item.type === "folder" ? `${(item.children || []).length} item` :
      item.type === "file" ? "teks" : "tautan";

    button.append(icon, name, type);

    button.addEventListener("click", () => {
      if (item.type === "folder") render([...path, item.name]);
      else if (item.type === "file") openFile(item);
      else openLink(item);
    });

    grid.appendChild(button);
  }
}

async function openFile(item) {
  try {
    const response = await fetch(item.path);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const text = await response.text();

    readerTitle.textContent = item.name.replace(/\.txt$/i, "");
    readerText.textContent = text;
    reader.classList.remove("hidden");
    document.body.style.overflow = "hidden";
  } catch (error) {
    alert(`Tidak bisa membuka ${item.name}. Pastikan file sudah di-deploy.`);
  }
}

function openLink(item) {
  if (!item.url) {
    alert(`Link ${item.name} belum memiliki alamat URL.`);
    return;
  }

  try {
    const url = new URL(item.url);

    if (!["http:", "https:"].includes(url.protocol)) {
      throw new Error("URL tidak aman");
    }

    window.open(url.href, "_blank", "noopener,noreferrer");
  } catch (error) {
    alert(`Alamat link ${item.name} tidak valid.`);
  }
}

function closeReader() {
  reader.classList.add("hidden");
  document.body.style.overflow = "";
}

document.getElementById("homeBtn").addEventListener("click", () => render([]));
document.getElementById("closeReader").addEventListener("click", closeReader);

reader.addEventListener("click", event => {
  if (event.target === reader) closeReader();
});

document.addEventListener("keydown", event => {
  if (event.key === "Escape" && !reader.classList.contains("hidden")) closeReader();
});

async function init() {
  try {
    const response = await fetch("files.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    state.tree = await response.json();
    render([]);
  } catch (error) {
    title.textContent = "Belum siap";
    empty.textContent = "files.json belum tersedia. Jalankan update.py terlebih dahulu.";
    empty.classList.remove("hidden");
  }
}

init();
