const form = document.getElementById("move-form");
const sourceInput = document.getElementById("source-path");
const destinationInput = document.getElementById("destination-path");
const button = document.getElementById("move-button");
const status = document.getElementById("move-status");

// shortcut: paths are entered manually, upgrade when Cockpit Files offers a stable selection API.
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const source = sourceInput.value.trim().replace(/\/+$/, "") || "/";
  const destination = destinationInput.value.trim();
  if (![source, destination].every((path) => path.startsWith("/") && !/[\u0000-\u001f\u007f]/.test(path)) || source === "/") {
    status.textContent = "Enter absolute file paths without control characters.";
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
