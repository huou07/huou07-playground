const form = document.getElementById("move-form");
const sourceInput = document.getElementById("source-path");
const destinationInput = document.getElementById("destination-path");
const button = document.getElementById("move-button");
const status = document.getElementById("move-status");
const dialog = document.getElementById("browse-dialog");
const title = document.getElementById("browse-title");
const currentPath = document.getElementById("browse-path");
const entries = document.getElementById("browse-entries");
const browseStatus = document.getElementById("browse-status");
const upButton = document.getElementById("browse-up");
const currentButton = document.getElementById("browse-current");
let pickerMode = "source";
let pickerPath = "/";
let browseRequest = 0;

function joinPath(parent, name) {
  return `${parent === "/" ? "" : parent}/${name}`;
}

function parentPath(path) {
  if (path === "/") return "/";
  const parent = path.replace(/\/+$/, "").replace(/\/[^/]*$/, "");
  return parent || "/";
}

function selectPath(path) {
  if (!path.startsWith("/") || /[\u0000-\u001f\u007f]/.test(path)) {
    browseStatus.textContent = "This path contains characters the move tool cannot accept.";
    return;
  }
  (pickerMode === "source" ? sourceInput : destinationInput).value = path;
  dialog.close();
}

function addEntry(item) {
  const row = document.createElement("li");
  const path = joinPath(pickerPath, item.name);
  const name = document.createElement("button");
  name.type = "button";
  name.className = "entry-name";
  name.textContent = `${item.directory ? "▸ " : item.symlink ? "↗ " : ""}${item.name}`;
  name.setAttribute("aria-label", item.directory ? `Open folder ${item.name}` : `Choose ${item.name}`);
  if (item.directory) {
    name.addEventListener("click", () => loadDirectory(path));
  } else if (pickerMode === "source") {
    name.addEventListener("click", () => selectPath(path));
  } else {
    name.disabled = true;
    name.classList.add("file-name");
  }
  row.append(name);

  if (item.directory && pickerMode === "source") {
    const choose = document.createElement("button");
    choose.type = "button";
    choose.className = "secondary entry-action";
    choose.textContent = "Choose folder";
    choose.setAttribute("aria-label", `Choose ${item.name} as the source folder`);
    choose.addEventListener("click", () => selectPath(path));
    row.append(choose);
  }
  entries.append(row);
}

async function loadDirectory(path) {
  const request = ++browseRequest;
  pickerPath = path;
  currentPath.textContent = path;
  upButton.disabled = path === "/";
  currentButton.disabled = true;
  entries.replaceChildren();
  browseStatus.textContent = "Loading folder…";
  try {
    const output = await cockpit.spawn(["/usr/libexec/huou07-list-files", path], { err: "message" });
    if (request !== browseRequest) return;
    const result = JSON.parse(output);
    pickerPath = result.path;
    currentPath.textContent = pickerPath;
    upButton.disabled = pickerPath === "/";
    currentButton.disabled = pickerMode === "source" && pickerPath === "/";
    entries.replaceChildren();
    for (const item of result.entries) addEntry(item);
    browseStatus.textContent = result.entries.length ? "" : "This folder is empty.";
  } catch (error) {
    if (request !== browseRequest) return;
    browseStatus.textContent = error.message || "This folder could not be opened.";
    currentPath.textContent = path;
    upButton.disabled = path === "/";
    currentButton.disabled = true;
  }
}

function openPicker(mode) {
  pickerMode = mode;
  title.textContent = mode === "source" ? "Choose a file or source folder" : "Choose a destination folder";
  currentButton.textContent = mode === "source" ? "Choose this folder as source" : "Use this destination";
  const field = mode === "source" ? sourceInput.value : destinationInput.value;
  const initialPath = field.trim() ? (mode === "source" ? parentPath(field.trim()) : field.trim()) : "/";
  dialog.showModal();
  loadDirectory(initialPath);
}

document.getElementById("browse-source").addEventListener("click", () => openPicker("source"));
document.getElementById("browse-destination").addEventListener("click", () => openPicker("destination"));
document.getElementById("browse-close").addEventListener("click", () => dialog.close());
dialog.addEventListener("close", () => { browseRequest += 1; });
upButton.addEventListener("click", () => loadDirectory(parentPath(pickerPath)));
currentButton.addEventListener("click", () => selectPath(pickerPath));

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const source = sourceInput.value.trim().replace(/\/+$/, "") || "/";
  const destination = destinationInput.value.trim();
  if (![source, destination].every((path) => path.startsWith("/") && !/[\u0000-\u001f\u007f]/.test(path)) || source === "/") {
    status.textContent = "Choose an accessible file or folder and an existing destination.";
    return;
  }
  if (!window.confirm(`Move ${source} into ${destination}? Existing files will not be replaced.`)) return;

  button.disabled = true;
  status.textContent = "Moving…";
  try {
    const result = await cockpit.spawn(["/usr/libexec/huou07-move-files", source, destination], { err: "message" });
    status.textContent = `Moved to ${result.trim()}.`;
  } catch (error) {
    status.textContent = error.message || "The file could not be moved.";
  } finally {
    button.disabled = false;
  }
});
