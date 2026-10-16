(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  // getRandomValues also works on VPN HTTP origins; randomUUID requires HTTPS
  // or a trusted localhost origin. These IDs identify UI dialogs/rules only.
  const uniqueId = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), value => value.toString(16).padStart(2, '0')).join('');
  const el = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const button = (text, action, className) => {
    const node = el('button', text, className);
    node.type = 'button';
    node.addEventListener('click', action);
    return node;
  };
  const label = (text, input) => {
    const node = el('label', text); node.append(input); return node;
  };
  const input = (name, value = '', type = 'text') => {
    const node = document.createElement('input'); node.name = name; node.value = value; node.type = type; return node;
  };
  const select = (values, value) => {
    const node = document.createElement('select');
    for (const [key, text] of values) { const option = el('option', text); option.value = key; node.append(option); }
    node.value = value; return node;
  };
  const message = (node, text, error = false) => {
    node.textContent = text; node.classList.toggle('product-error', error);
  };
  let session = null, csrf = '', loginDialog = null;
  const account = $('owner-account');
  const browsers = [];
  let policy = null, draft = null, dirty = false, policyScope='*';
  function dialog(title) {
    const previous = document.activeElement;
    const node = el('dialog', undefined, 'product-dialog');
    const heading = el('h2', title); heading.id = 'dialog-' + uniqueId();
    node.setAttribute('aria-labelledby', heading.id);
    node.append(heading);
    const status = el('p', '', 'product-status'); status.setAttribute('role', 'status');
    const actions = el('div', undefined, 'dialog-actions');
    const close = () => node.close();
    actions.append(button('Cancel', close));
    node.append(status, actions);
    node.addEventListener('close', () => { node.remove(); if (previous?.isConnected) previous.focus(); else document.querySelector('[data-view]:not([hidden]) button')?.focus(); });
    document.body.append(node);
    node.showModal();
    return { node, status, actions, close, add: (...nodes) => status.before(...nodes) };
  }
  async function ownerFetch(path, options = {}) {
    const publicEndpoint = ['/api/owner/session', '/api/owner/login'].includes(path);
    if (!publicEndpoint && !session) {
      await window.h07pSessionReady;
      if (!session) { signIn(); throw new Error('Owner sign in required. Sign in, then retry.'); }
    }
    const headers = new Headers(options.headers);
    if (csrf && path.startsWith('/api/')) headers.set('X-H07P-CSRF', csrf);
    const requestSession = session;
    const response = await fetch(path, { credentials: 'same-origin', cache: 'no-store', ...options, headers });
    if (!publicEndpoint && requestSession !== session) throw new Error('Owner session changed. Retry after signing in.');
    if (response.status === 401 && !publicEndpoint) {
      session = null; csrf = ''; account.textContent = 'Owner sign in';
      policy = draft = null; dirty = false; permissions.replaceChildren();
      for (const browser of browsers) browser.clear();
      for (const open of document.querySelectorAll('.product-dialog')) open.close();
      window.dispatchEvent(new CustomEvent('h07p-owner-session', { detail: false }));
      signIn(); throw new Error('Owner session expired. Sign in, then retry.');
    }
    return response;
  }
  window.h07pFetch = ownerFetch;
  async function api(path, options = {}) {
    const headers = { ...options.headers };
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    const response = await ownerFetch(path, { ...options, headers, body: options.body === undefined ? undefined : JSON.stringify(options.body) });
    if (!response.ok) {
      let detail;
      try { const body = await response.json(); detail = body.error || body.message; } catch {}
      throw new Error(typeof detail === 'string' ? detail : 'Request failed (' + response.status + '). Retry after checking access and server status.');
    }
    return response.status === 204 ? {} : response.json();
  }
  async function loadSession(notify = true) {
    const data = await api('/api/owner/session');
    session = data.authenticated ? data : null;
    csrf = session ? (data.csrf || csrf) : '';
    account.textContent = session ? session.username + ' · Sign out' : 'Owner sign in';
    if(notify) window.dispatchEvent(new CustomEvent('h07p-owner-session', { detail: !!session }));
    return session;
  }
  function signIn() {
    if (loginDialog?.node.isConnected) return loginDialog;
    const d = dialog('Owner sign in'); loginDialog = d;
    const form = el('form'), username = input('username'), password = input('password', '', 'password');
    username.autocomplete = 'username'; password.autocomplete = 'current-password'; username.required = password.required = true;
    const submit = el('button', 'Sign in', 'primary'); submit.type = 'submit';
    form.append(label('Username', username), label('Password', password), submit);
    d.add(el('p', 'Use the owner account configured on this server. Workers cannot administer this dashboard.', 'panel-note'), form);
    form.addEventListener('submit', async (event) => {
      event.preventDefault(); submit.disabled = true; message(d.status, 'Signing in…');
      try {
        const login = await api('/api/owner/login', { method: 'POST', body: { username: username.value, password: password.value } });
        csrf = typeof login.csrf === 'string' ? login.csrf : '';
        if (!csrf) throw new Error('Owner sign-in proof is unavailable. Retry signing in.');
        password.value = ''; if (!await loadSession()) throw new Error('Owner session could not be confirmed. Retry signing in.'); d.close(); loginDialog = null; await route();
      } catch (error) { password.value = ''; message(d.status, error.message, true); }
      finally { submit.disabled = false; }
    });
    d.node.addEventListener('close', () => { password.value = ''; loginDialog = null; });
    username.focus(); return d;
  }
  account.addEventListener('click', async () => {
    if (!session) { signIn(); return; }
    try {
      await api('/api/owner/logout', { method: 'POST', body: {} });
      session = null; csrf = ''; policy = draft = null; dirty = false;
      account.textContent = 'Owner sign in'; $('permissions-panel').replaceChildren();
      window.dispatchEvent(new CustomEvent('h07p-owner-session', { detail: false }));
      for (const browser of browsers) browser.clear();
      for (const open of document.querySelectorAll('.product-dialog')) open.close();
    } catch (error) { const d = dialog('Sign out'); message(d.status, error.message, true); }
  });
  const join = (path, name) => (path === '/' ? '' : path.replace(/\/$/, '')) + '/' + name;
  const fsUrl = (endpoint, area, path) => '/api/fs/' + endpoint + '?' + new URLSearchParams({ area, path });
  const dateMs = value => typeof value === 'number' ? value * 1000 : Date.parse(value);
  const displayDate = value => Number.isFinite(dateMs(value)) ? new Date(dateMs(value)).toLocaleString() : 'Unavailable';
  const units = (bytes) => Number.isFinite(Number(bytes)) ? (Number(bytes) / 1073741824).toFixed(2) + ' GiB' : 'Unavailable';
  const fileSize = (bytes) => bytes == null ? '—' : bytes < 1024 ? bytes + ' B' : bytes < 1048576 ? (bytes / 1024).toFixed(1) + ' KiB' : (bytes / 1048576).toFixed(1) + ' MiB';
  async function fileTicket(kind, area, path, signal) {
    const data = await api('/api/fs/ticket', { method: 'POST', body: { area, path, kind }, signal });
    const url = new URL(data.url, location.origin);
    if (url.origin !== location.origin || url.pathname !== '/api/fs/' + kind || url.searchParams.get('area') !== area || url.searchParams.get('path') !== path || !url.searchParams.get('ticket')) {
      throw new Error('File access link is unavailable. Retry after signing in.');
    }
    return url.href;
  }
  async function download(area, path) {
    const url = await fileTicket('download', area, path);
    const link = el('a'); link.href = url; link.download = ''; document.body.append(link); link.click(); link.remove();
  }
  async function preview(area, entry) {
    const d = dialog(entry.name), controller = new AbortController();
    d.node.addEventListener('close', () => controller.abort());
    const link = el('a', 'Download file'); link.download = ''; d.add(link);
    const extension = entry.name.split('.').at(-1).toLowerCase();
    message(d.status, 'Preparing private file access…');
    try {
      link.href = await fileTicket('download', area, entry.path, controller.signal);
      if (!d.node.isConnected) return;
      if (['png', 'jpg', 'jpeg', 'webp', 'gif', 'avif', 'bmp'].includes(extension)) {
        const url = await fileTicket('preview', area, entry.path, controller.signal);
        if (!d.node.isConnected) return;
        const image = el('img'); image.alt = entry.name; image.loading = 'lazy'; image.src = url;
        image.addEventListener('error', () => message(d.status, 'Image preview unavailable. Download the file to inspect it.', true)); d.add(image);
        message(d.status, 'Image preview · the private access link expires after 15 minutes. Reopen to refresh.');
      } else if (['mp4', 'webm', 'ogg', 'mov', 'm4v'].includes(extension)) {
        const url = await fileTicket('preview', area, entry.path, controller.signal);
        if (!d.node.isConnected) return;
        const video = el('video'); video.controls = true; video.preload = 'metadata'; video.src = url;
        video.addEventListener('error', () => message(d.status, 'This browser cannot play this video. Download the original file.', true));
        d.add(video); d.node.addEventListener('close', () => { video.pause(); video.removeAttribute('src'); video.load(); });
        message(d.status, 'Video preview · reopen after 15 minutes to refresh private access.');
      } else if (['txt','md','json','csv','log','toml','yaml','yml','rs','py','js','css','sh','conf','ini'].includes(extension)) {
        message(d.status, 'Loading bounded text preview…');
        const response = await ownerFetch(fsUrl('preview', area, entry.path), { signal: controller.signal });
        if (!response.ok) throw new Error('Preview unavailable (' + response.status + ').');
        const reader = response.body.getReader(); const decoder = new TextDecoder(); let text = '', bytes = 0, truncated = false;
        while (true) {
          const part = await reader.read(); if (part.done) break;
          const remaining = 262144 - bytes; text += decoder.decode(part.value.subarray(0, remaining), { stream: true }); bytes += part.value.length;
          if (bytes >= 262144) { truncated = true; await reader.cancel(); break; }
        }
        text += decoder.decode(); if (!d.node.isConnected) return; d.add(el('pre', text));
        message(d.status, truncated ? 'Preview limited to 256 KiB. Download for the complete file.' : 'Text preview · content is displayed as text.');
      } else message(d.status, 'Preview unavailable for this format. HTML, SVG, and active documents are download only.');
    } catch (error) { if (error.name !== 'AbortError' && d.node.isConnected) message(d.status, error.message, true); }
  }
  function fileBrowser(root, area) {
    root.classList.add('product');
    const panel = el('section', undefined, 'panel');
    const heading = el('div', undefined, 'panel-heading');
    const privacy = el('span', area === 'nas' ? 'Private · confirmation pending' : 'Owner OS rights', 'badge');
    heading.append(el('h2', area === 'nas' ? 'Private NAS' : 'Host browser'), privacy);
    const status = el('p', 'Sign in to browse files.', 'product-status'); status.setAttribute('role', 'status');
    const capacity = el('div'), crumbs = el('nav', undefined, 'product-breadcrumbs'); crumbs.setAttribute('aria-label', area === 'nas' ? 'NAS folders' : 'Host folders');
    const pathbar = el('div', undefined, 'product-path'), pathForm = el('form'), pathInput = input('path', '/');
    pathInput.setAttribute('aria-label', area === 'nas' ? 'NAS path' : 'Host path');
    const go = el('button', 'Go'); go.type = 'submit'; pathForm.append(pathInput, go);
    const up = button('Up', () => load(parent || '/'));
    pathbar.append(up, pathForm, button('Copy path', async () => {
      try { await navigator.clipboard.writeText(path); message(status, 'Path copied.'); }
      catch { pathInput.select(); message(status, 'Clipboard unavailable. Copy the selected path.'); }
    }));
    const toolbar = el('div', undefined, 'product-toolbar'), table = el('table', undefined, 'product-list'), thead = el('thead'), header = el('tr');
    const all = input('select-all', '', 'checkbox'); all.setAttribute('aria-label', 'Select all visible files');
    const selectCell = el('th'); selectCell.append(all); header.append(selectCell);
    const sort = select([['name','Name'],['size','Size'],['modified','Modified']], 'name'); sort.setAttribute('aria-label', 'Sort files');
    const nameCell = el('th'); nameCell.append(sort); header.append(nameCell, el('th','Size'),el('th','Modified')); thead.append(header);
    const body = el('tbody'); table.append(thead, body);
    const footer = el('div', undefined, 'product-toolbar'), count = el('span', '0 selected', 'product-status');
    const previous = button('Previous page', () => load(path, Math.max(0, offset - pageSize)));
    const next = button('Next page', () => load(path, offset + entries.length));
    footer.append(count, previous, next);
    let path = '/', parent = null, offset = 0, pageSize = 100, entries = [], selected = new Set(), clipboard = null, busy = false, total = 0, searching=false, searchController=null, requestEpoch=0;
    const searchForm=el('form',undefined,'product-path'),searchInput=input('query'),recursiveSearch=input('recursive','','checkbox');
    searchInput.type='search';searchInput.placeholder='Tên file hoặc một phần tên…';searchInput.maxLength=512;searchInput.required=true;
    searchInput.setAttribute('aria-label',area==='nas'?'Search NAS filenames':'Search Storage filenames');recursiveSearch.checked=true;
    const searchSubmit=el('button','Search');searchSubmit.type='submit';
    const cancelSearch=button('Cancel search',()=>{searchController?.abort();requestEpoch++;busy=false;cancelSearch.hidden=true;searchSubmit.disabled=false;update();message(status,'Search canceled. No files changed.');});cancelSearch.hidden=true;
    searchForm.append(searchInput,label('Include subfolders',recursiveSearch),searchSubmit,cancelSearch,button('Clear search',()=>{searchInput.value='';load(path);}));
    searchForm.addEventListener('submit',async event=>{
      event.preventDefault();searchController?.abort();const controller=new AbortController();searchController=controller;
      const epoch=++requestEpoch;busy=true;update();cancelSearch.hidden=false;searchSubmit.disabled=true;message(status,'Searching filenames in this folder…');
      try{
        const data=await api('/api/fs/search',{method:'POST',body:{area,path,query:searchInput.value,recursive:recursiveSearch.checked},signal:controller.signal});
        if(epoch!==requestEpoch || !session)return;
        searching=true;entries=data.entries||[];total=data.total??entries.length;selected.clear();offset=0;render();
        message(status,`${total} matches · ${data.visited} names checked. `+(data.partial?'Partial results: some folders were skipped or a search limit was reached. Narrow the folder or filename. ':'')+'Filenames only; file contents were not read.');
      }catch(error){if(epoch===requestEpoch)message(status,error.name==='AbortError'?'Search canceled.':error.message,error.name!=='AbortError');}
      finally{if(epoch===requestEpoch){busy=false;update();cancelSearch.hidden=true;searchSubmit.disabled=false;}}
    });
    const selectedEntries = () => entries.filter(entry => selected.has(entry.path));
    const actions = {};
    const action = (name, callback, className) => { const b = button(name, callback, className); toolbar.append(b); actions[name] = b; return b; };
    const update = () => {
      count.textContent = selected.size + ' selected · ' + total + ' items' + (clipboard ? ' · ' + clipboard.entries.length + ' to ' + clipboard.action : '');
      for (const name of ['Download','Rename','Cut','Copy','Delete','Preview']) actions[name].disabled = busy || !selected.size || (['Rename','Preview'].includes(name) && selected.size !== 1);
      actions.Paste.disabled = busy || !clipboard;
      up.disabled = busy || path === '/'; previous.disabled = busy || searching || offset === 0; next.disabled = busy || searching || offset + entries.length >= total;
      all.checked = entries.length > 0 && selected.size === entries.length;
      all.indeterminate = selected.size > 0 && selected.size < entries.length;
      for (const row of body.children) row.dataset.selected = String(selected.has(row.dataset.path));
    };
    function render() {
      body.replaceChildren();
      const visible = [...entries].sort((a,b) => sort.value === 'size' ? (a.size || 0) - (b.size || 0) : String(a[sort.value] || '').localeCompare(String(b[sort.value] || '')));
      for (const entry of visible) {
        const row = el('tr'); row.dataset.path = entry.path;
        const checkbox = input('selected-file', '', 'checkbox'); checkbox.checked = selected.has(entry.path); checkbox.setAttribute('aria-label', 'Select ' + entry.name);
        checkbox.addEventListener('change', () => { if (checkbox.checked) selected.add(entry.path); else selected.delete(entry.path); update(); });
        const cell = el('td'); cell.append(checkbox);
        const name = el('td'); const open = button((entry.kind === 'directory' ? '▤ ' : entry.kind === 'symlink' ? '↗ ' : '') + entry.name, () => entry.kind === 'directory' ? load(entry.path) : preview(area, entry), 'file-open');
        name.append(open);if(searching){name.append(el('small',entry.path));name.append(button('Open folder',()=>load(entry.path.slice(0,entry.path.lastIndexOf('/'))||'/'),'file-open'));} if(entry.temporary) name.append(el('span','Incomplete upload · inspect or delete','product-warning')); row.append(cell, name, el('td', entry.kind === 'directory' ? 'Folder' : fileSize(entry.size)), el('td', entry.modified ? displayDate(entry.modified) : '—'));
        row.addEventListener('contextmenu', event => { event.preventDefault(); selected = new Set([entry.path]); render(); actions.Rename.focus(); });
        row.addEventListener('keydown', event => { if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) { event.preventDefault(); selected = new Set([entry.path]); render(); actions.Rename.focus(); } });
        body.append(row);
      }
      if (!entries.length) { const row = el('tr'), cell = el('td',searching?'No matching filenames in the searched scope.':'This folder is empty. Create a folder or upload a file.'); cell.colSpan = 4; row.append(cell); body.append(row); }
      update();
    }
    async function load(nextPath = path, nextOffset = 0) {
      if (!session) { message(status, 'Owner sign in required.'); signIn(); return; }
      searchController?.abort();const epoch=++requestEpoch;searching=false;cancelSearch.hidden=true;searchSubmit.disabled=false;
      busy = true; update(); message(status, 'Loading files…');
      try {
        const data = await api(fsUrl('list', area, nextPath) + '&offset=' + nextOffset);
        if (!session || epoch!==requestEpoch) return;
        path = data.path; parent = data.parent; pathInput.value = path; offset = nextOffset; entries = data.entries || []; if(nextOffset === 0 && entries.length) pageSize=entries.length; total = data.total ?? entries.length; selected.clear();
        crumbs.replaceChildren(button('/', () => load('/')));
        let current = ''; for (const part of path.split('/').filter(Boolean)) { current += '/' + part; const target = current; crumbs.append(el('span','/'), button(part, () => load(target))); }
        capacity.replaceChildren();
        if (data.capacity) {
          const grid = el('div', undefined, 'product-capacity');
          for (const key of ['total','used','free','available']) { const cell = el('div'); cell.append(el('span',key[0].toUpperCase() + key.slice(1)),el('strong',units(data.capacity[key]))); grid.append(cell); }
          capacity.append(grid,el('p','Free includes reserved blocks; available is usable by the browsing identity. Sampled ' + new Date().toLocaleTimeString() + '. 1 GiB = 1,073,741,824 bytes.','panel-note'));
        }
        if(area === 'nas') privacy.textContent=data.private === true ? 'Private · server confirmed' : 'Isolation unconfirmed';
        render(); message(status, area === 'nas' ? (data.private === true ? 'Private owner NAS confirmed by the service. See Permissions for managed-worker coverage.' : 'The server has not confirmed NAS privacy. Refresh status before uploading private data.') : 'Listed with owner OS rights. Some host paths may be inaccessible.'); if(entries.some(entry=>entry.temporary)) status.textContent+=' Incomplete uploads were retained after interruption. Inspect or explicitly delete them; no automatic deletion occurs.';
      } catch (error) { if(epoch===requestEpoch)message(status, error.message, true); }
      finally { if(epoch===requestEpoch){busy = false; update();} }
    }
    function nameDialog(title, initial, callback) {
      const d = dialog(title), form = el('form'), field = input('name', initial);
      field.required = true; const submit = el('button', title, 'primary'); submit.type = 'submit';
      form.append(label('Name (no overwrite)',field),submit); d.add(form);
      form.addEventListener('submit',async event => {
        event.preventDefault(); if (field.value === '.' || field.value === '..' || /[\\/\\\\]/.test(field.value)) { message(d.status,'Choose an ordinary file or folder name.',true); return; }
        submit.disabled = true;
        try { await callback(field.value); d.close(); await load(); }
        catch(error) { message(d.status,error.message,true); } finally { submit.disabled = false; }
      });
      field.focus(); field.select();
    }
    const mutate = (actionName, entryPath, destination) => api('/api/fs/mutate', { method:'POST',body:{area,action:actionName,path:entryPath,...(actionName === 'delete' ? {confirmed:true} : {}),...(destination ? {destination} : {})} });
    action('New folder', () => nameDialog('New folder','',name => mutate('mkdir',join(path,name))), 'primary');
    const uploadInput = input('upload','','file'); uploadInput.multiple = true; uploadInput.hidden = true;
    action('Upload',() => uploadInput.click());
    uploadInput.addEventListener('change',async () => { const files = [...uploadInput.files]; uploadInput.value = ''; if (files.length) upload(files); });
    async function upload(files) {
      const d = dialog('Upload to ' + path), progress = el('progress'); progress.max = 100; progress.value = 0;
      d.add(el('p','Existing files are never overwritten. A canceled transfer may already have completed; refresh to check.'), progress);
      let canceled = false, xhr = null;
      d.node.addEventListener('cancel', () => { canceled = true; xhr?.abort(); });
      d.node.addEventListener('close', () => { canceled = true; xhr?.abort(); });
      const results = [];
      for (const file of files) {
        if (canceled) break;
        message(d.status, 'Uploading ' + file.name + '…'); progress.value = 0;
        try {
          await new Promise((resolve,reject) => {
            xhr = new XMLHttpRequest(); xhr.open('PUT',fsUrl('upload',area,join(path,file.name)));
            xhr.setRequestHeader('X-H07P-CSRF',csrf); xhr.withCredentials = true;
            xhr.upload.addEventListener('progress', event => { if(event.lengthComputable) progress.value = event.loaded / event.total * 100; });
            xhr.onload = () => { if(xhr.status >= 200 && xhr.status < 300) resolve(); else { if(xhr.status === 401) signIn(); let detail = 'HTTP ' + xhr.status; try { detail = JSON.parse(xhr.responseText).error || detail; } catch {} reject(new Error(String(detail))); } };
            xhr.onerror = () => reject(new Error('Network error; retry after refreshing.')); xhr.onabort = () => reject(new Error('Canceled. Refresh to check whether finalization completed.'));
            xhr.send(file);
          }); results.push(file.name + ': uploaded');
        } catch(error) { results.push(file.name + ': ' + error.message); }
      }
      if (d.node.isConnected) { progress.value = 100; message(d.status,results.join('\n')); d.actions.firstChild.textContent = 'Close'; }
      await load();
    }
    action('Download', async () => { for(const entry of selectedEntries()) { if(entry.kind === 'directory') { message(status,'Download individual files; folder archives are not supported.'); continue; } try { await download(area,entry.path); } catch(error) { message(status,error.message,true); break; } } });
    action('Preview', () => preview(area,selectedEntries()[0]));
    action('Rename', () => { const entry=selectedEntries()[0]; nameDialog('Rename',entry.name,name => mutate('rename',entry.path,join(path,name))); });
    for (const name of ['Cut','Copy']) action(name, () => { clipboard={action:name === 'Cut' ? 'move' : 'copy',entries:selectedEntries()}; update(); });
    action('Paste', () => {
      const d=dialog('Confirm ' + clipboard.action), pending=clipboard, destination=input('destination',path);
      let stopped=false;d.node.addEventListener('close',()=>{stopped=true;});
      d.add(label('Destination folder',destination),el('p',pending.entries.map(entry=>entry.name).join(', ')),el('p','Conflicts are skipped; existing files are never overwritten. Moves remove a source only after the server completes its durable destination. Stop remaining leaves any operation already in progress to finish.','product-warning'));
      const run=button('Paste here',async () => {
        run.disabled=true;d.actions.firstChild.textContent='Stop remaining'; const failures=[],results=[];
        for(const entry of pending.entries) {
          if(stopped){failures.push(entry);results.push(entry.name + ': not started');continue;}
          message(d.status,'Processing ' + entry.name + '…');
          try { const result=await mutate(pending.action,entry.path,join(destination.value,entry.name)); if(result.ok === false || result.results?.some(item=>item.ok === false || item.error)) throw new Error(JSON.stringify(result.results || result)); results.push(entry.name + ': complete'); }
          catch(error) { failures.push(entry); results.push(entry.name + ': ' + error.message); }
        }
        clipboard=failures.length ? {...pending,entries:failures} : null;
        message(d.status,results.join('\n'),!!failures.length); run.remove(); d.actions.firstChild.textContent='Close'; await load();
      },'primary'); d.actions.append(run);
    });
    action('Delete', () => {
      const targets=selectedEntries(), d=dialog('Permanently delete ' + targets.length + ' item(s)?');
      let stopped=false;d.node.addEventListener('close',()=>{stopped=true;});
      d.add(el('p',targets.map(entry=>entry.name).join(', ')),el('p','This cannot be undone. Folder contents are also permanently removed.','product-warning'));
      const remove=button('Permanently delete', async () => {
        remove.disabled=true;d.actions.firstChild.textContent='Stop remaining'; const results=[];
        for(const entry of targets) { if(stopped) break;try { await mutate('delete',entry.path); results.push(entry.name + ': deleted'); } catch(error) { results.push(entry.name + ': ' + error.message); } }
        message(d.status,results.join('\n')); remove.remove(); d.actions.firstChild.textContent='Close'; await load();
      },'danger'); d.actions.append(remove);
    },'danger');
    action('Refresh',() => load());
    all.addEventListener('change',() => { selected = new Set(all.checked ? entries.map(entry=>entry.path) : []); render(); });
    sort.addEventListener('change',render); pathForm.addEventListener('submit',event=>{event.preventDefault();load(pathInput.value);});
    panel.addEventListener('dragover',event=>{event.preventDefault();});
    panel.addEventListener('drop',event=>{event.preventDefault();if(session && event.dataTransfer.files.length) upload([...event.dataTransfer.files]);});
    panel.addEventListener('keydown',event=>{
      if(event.target.matches('input,select,textarea')) return;
      if((event.ctrlKey || event.metaKey) && ['c','x','v'].includes(event.key.toLowerCase())) { event.preventDefault(); actions[{c:'Copy',x:'Cut',v:'Paste'}[event.key.toLowerCase()]].click(); }
      if(event.key === 'Delete') actions.Delete.click();
      if(event.key === 'F2') actions.Rename.click();
    });
    panel.append(heading,capacity,pathbar,crumbs,searchForm,toolbar,uploadInput,status,table,footer); root.append(panel); update();
    const browser={ load,clear:()=>{requestEpoch++;searchController?.abort();busy=false;searching=false;searchInput.value='';searchSubmit.disabled=false;cancelSearch.hidden=true;entries=[];selected.clear();clipboard=null;total=0;body.replaceChildren();capacity.replaceChildren();crumbs.replaceChildren();path='/';pathInput.value='/';message(status,'Owner sign in required.');update();} };
    browsers.push(browser); return browser;
  }
  const nas=fileBrowser($('nas-browser'),'nas'), storage=fileBrowser($('host-browser'),'storage');
  const permissions=$('permissions-panel');
  function policyBody() { return {expected_revision:draft.revision,preset:draft.preset,workspace:draft.workspace,rules:draft.rules,worker_settings:draft.worker_settings||{}}; }
  function ruleDescription(rule) {
    return (rule.action === 'block' ? 'Private · Block' : 'Allow') + ' · ' + (rule.operations || []).join(', ') + ' · ' + (rule.worker || 'all managed workers') + (rule.recursive ? ' · recursive' : '') + (rule.expires_at ? ' · expires ' + displayDate(rule.expires_at) : '') + ' · ' + (rule.source || 'manual') + (rule.inherited ? ' · inherited' : '');
  }
  function markDirty() { dirty=true; renderPolicy(); }
  function renderPolicy() {
    permissions.replaceChildren();
    if(!policy || !draft) { permissions.append(el('p','Sign in to manage worker access.','product-status')); return; }
    const panel=el('section',undefined,'panel');
    const summary=el('div',undefined,'product-summary');
    const enforced=policy.enforced_revision != null && policy.enforced_revision === policy.revision;
    summary.append(el('strong', 'Desired revision ' + policy.revision + ' · ' + (enforced ? 'Enforced revision ' + policy.enforced_revision : 'Enforcement pending / unavailable') + (dirty ? ' · Unapplied draft' : '')));
    summary.append(el('span','Effective template: ' + policy.preset + (dirty ? ' · Draft: Custom (' + draft.preset + ')' : '')));
    const workers=policy.workers || [];if(policyScope!=='*'&&!workers.some(w=>w.name===policyScope))policyScope='*';
    summary.append(el('span',workers.length ? 'Managed workers: ' + workers.map(w=>w.name + ' (' + w.state + ', ' + w.preset + ')').join(', ') : 'No managed-worker coverage reported.'));
    const warning=el('p','Coverage is limited to workers launched by H07P. Shared-home ACLs cannot independently isolate directory write/create/delete, or prevent an interpreter from reading a script. Unsupported rights must be rejected by the backend. Revocation cannot erase bytes already read.','product-warning');
    const capabilities=el('details'), capTitle=el('summary','Enforcement capabilities and limitations'); capabilities.append(capTitle,el('pre',JSON.stringify(policy.capabilities || {},null,2)));
    const scoped=policyScope==='*'?draft:{...draft,...(draft.worker_settings?.[policyScope]||{})};
    const scope=select([['*','All managed workers'],...workers.map(w=>[w.name,w.name])],policyScope);scope.setAttribute('aria-label','Configure worker');scope.addEventListener('change',()=>{policyScope=scope.value;renderPolicy();});
    const setScoped=(key,value)=>{draft.worker_settings ||= {};if(policyScope==='*'){draft[key]=value;for(const setting of Object.values(draft.worker_settings))delete setting[key];}else{draft.worker_settings[policyScope] ||= {};draft.worker_settings[policyScope][key]=value;}};
    const preset=select([['none','None · existing OS rights'],['minimal','Minimal · confirmed sensitive rules'],['balance','Balance · approval outside workspace'],['strict','Strict · no outside workspace data']],scoped.preset);
    preset.setAttribute('aria-label','Security Level');
    preset.addEventListener('change',()=>{
      const choice=preset.value, d=dialog('Review Security Level change');
      d.add(el('p','Change to ' + choice + '. This is a draft until Review impact and Apply.'),el('p',choice === 'none' ? 'None adds no privileges. Owner administration and NAS remain private.' : choice === 'minimal' ? 'Minimal protects only owner-confirmed sensitive rules. A scan has not been applied automatically.' : choice === 'strict' ? 'Strict denies outside-workspace data; declared runtime dependencies remain readable. Worker restart may stop tasks.' : 'Balance requires explicit broker approval outside the workspace. Direct OS access remains denied.','product-warning'));
      d.actions.append(button('Keep custom rules',()=>{setScoped('preset',choice);d.close();markDirty();},'primary'),button('Reset draft rules',()=>{setScoped('preset',choice);draft.rules=policyScope==='*'?[]:draft.rules.filter(rule=>rule.worker!==policyScope);d.close();markDirty();},'danger'));
      d.node.addEventListener('close',()=>{preset.value=scoped.preset;});
    });
    const workspace=input('workspace',scoped.workspace || '/'); workspace.setAttribute('aria-label','Worker workspace');
    workspace.addEventListener('change',()=>{setScoped('workspace',workspace.value);markDirty();});
    const configuration=el('div',undefined,'product-toolbar');configuration.append(label('Configure',scope),label('Security Level',preset),label('Workspace (absolute path)',workspace));
    const toolbar=el('div',undefined,'product-toolbar');
    toolbar.append(button('Block',()=>editRule({action:'block',worker:policyScope})),button('Allow',()=>editRule({action:'allow',worker:policyScope})),button('Auto Detect',scan),button('Review impact',reviewPolicy,'primary'));
    const discard=button('Discard draft',()=>{draft=structuredClone(policy);dirty=false;renderPolicy();});discard.disabled=!dirty;toolbar.append(discard);
    const rules=el('div');rules.setAttribute('aria-label','Permission rules');
    if(!draft.rules.length) rules.append(el('p','No custom rules. The selected preset and immutable owner/NAS boundary still apply.','panel-note'));
    for(const rule of draft.rules.filter(rule=>policyScope==='*'||!rule.worker||rule.worker==='*'||rule.worker===policyScope)) {
      const row=el('article',undefined,'product-rule'),head=el('div',undefined,'product-rule-head');
      head.append(el('strong',rule.target),el('span',dirty?'Draft':enforced?'Enforced':'Desired','badge'),button('Edit',()=>editRule(rule)),button('Remove',()=>{draft.rules=draft.rules.filter(item=>item.id!==rule.id);markDirty();},'danger'));
      row.append(head,el('p',ruleDescription(rule)));
      if(rule.effective_rights) row.append(el('p','Effective rights: ' + JSON.stringify(rule.effective_rights)));
      if(rule.conflict_reason) row.append(el('p','Conflict: ' + rule.conflict_reason,'product-warning'));
      rules.append(row);
    }
    panel.append(summary,warning,capabilities,configuration,toolbar,rules);
    const approvals=el('section',undefined,'panel');approvals.append(el('h2','Approval requests'));
    if(!(policy.approvals || []).length) approvals.append(el('p','No pending approval requests. Workers request scoped access through the broker.','panel-note'));
    for(const approval of policy.approvals || []) {
      const row=el('article',undefined,'product-rule');
      row.append(el('strong',approval.worker + ' · ' + approval.operation + ' · ' + approval.target),el('p','Workspace: ' + (approval.workspace || policy.workspace) + ' · Revision ' + (approval.revision ?? approval.policy_revision) + ' · Expires ' + displayDate(approval.expires_at)),el('p',approval.reason || 'No reason supplied.'));
      const expired=!Number.isFinite(dateMs(approval.expires_at)) || dateMs(approval.expires_at) <= Date.now() || (approval.revision ?? approval.policy_revision) !== policy.revision || (approval.state && approval.state !== 'pending');
      if(expired) row.append(el('p','Request is expired, stale, or already decided. The worker must request access again.','product-warning'));
      const approve=button('Approve once',()=>decideApproval(approval,true),'primary');approve.disabled=expired;
      const deny=button('Deny',()=>decideApproval(approval,false));deny.disabled=expired;
      const actions=el('div',undefined,'product-toolbar');actions.append(approve,deny);row.append(actions);approvals.append(row);
    }
    const history=el('section',undefined,'panel');history.append(el('h2','Audit and rollback'));
    for(const event of (policy.audit || []).slice().reverse().slice(0,30)) {
      const row=el('article',undefined,'product-rule');
      row.append(el('p',(event.at || event.timestamp || event.time ? displayDate(event.at || event.timestamp || event.time) : '') + ' · ' + (event.action || event.event || 'Policy change') + (event.revision != null ? ' · Revision ' + event.revision : '')));
      if(event.revision != null && event.revision !== policy.revision) row.append(button('Restore revision ' + event.revision,()=>rollback(event.revision)));
      history.append(row);
    }
    if(!(policy.audit || []).length) history.append(el('p','No audit entries reported.','panel-note'));
    if(policy.revision > 0) {
      const revisionForm=el('form',undefined,'product-toolbar'),revisionInput=input('rollback_revision',String(policy.revision-1),'number');
      revisionInput.min='0';revisionInput.max=String(policy.revision-1);revisionInput.required=true;revisionInput.step='1';
      const restore=el('button','Review rollback');restore.type='submit';
      revisionForm.append(label('Revision to restore',revisionInput),restore);
      revisionForm.addEventListener('submit',event=>{event.preventDefault();rollback(Number(revisionInput.value));});history.append(revisionForm);
    }
    history.append(el('p','Owner recovery is available through the installed host control plane. Worker sessions cannot use owner recovery.','panel-note'));
    permissions.append(panel,approvals,history);
  }
  async function loadPolicy({preserveDraft=false}={}) {
    if(!session) { renderPolicy(); signIn(); return; }
    if(dirty && !preserveDraft) {
      const d=dialog('Refresh without losing the draft');
      d.add(el('p','Your current draft is unapplied. Discard it to load current server policy.'));
      d.actions.append(button('Discard and refresh',()=>{dirty=false;d.close();loadPolicy();},'danger')); return;
    }
    if(!preserveDraft) permissions.replaceChildren(el('p','Loading permission status…','product-status'));
    try { const current=await api('/api/control/status');if(!session)return;policy=current;if(!dirty) draft=structuredClone(current);draft.rules ||= [];renderPolicy();return true; }
    catch(error) { const status=el('p',error.message,'product-status product-error');permissions.replaceChildren(status,button('Retry',()=>loadPolicy()));return false; }
  }
  async function browsePath(onSelect, initial='/') {
    const d=dialog('Browse host path'), path=input('browse-path',initial), form=el('form'), list=el('div');
    const go=el('button','Go');go.type='submit';form.append(label('Absolute host path',path),go);d.add(form,list);
    const choose=button('Use this path',()=>{onSelect(path.value);d.close();},'primary');d.actions.append(choose);
    async function listPath(target) {
      message(d.status,'Loading…');choose.disabled=true;
      try {
        const data=await api(fsUrl('list','storage',target));path.value=data.path;list.replaceChildren();
        if(data.parent) list.append(button('Up',()=>listPath(data.parent)));
        for(const entry of data.entries) {
          const row=el('div',undefined,'product-toolbar');
          row.append(el('span',entry.name + ' · ' + entry.kind),button('Select',()=>{onSelect(entry.path);d.close();}));
          if(entry.kind==='directory') row.append(button('Open',()=>listPath(entry.path)));list.append(row);
        }
        message(d.status,(data.total>data.entries.length?'Only the first page is displayed; enter a full path to select another target. ':'')+'Selecting a path does not modify files.');choose.disabled=false;
      } catch(error) { message(d.status,error.message,true); }
    }
    form.addEventListener('submit',event=>{event.preventDefault();listPath(path.value);});await listPath(initial);
  }
  function editRule(existing={}) {
    const d=dialog(existing.id?'Edit permission rule':'New permission rule'), form=el('form');
    const target=input('target',existing.target || '');target.required=true;target.pattern='/.*';target.placeholder='/absolute/path';
    const worker=select([['*','All managed workers'],...(policy.workers || []).map(item=>[item.name,item.name])],existing.worker || '*');
    const action=select([['block','Block · Private'],['allow','Allow']],existing.action || 'block');
    const kind=select([['directory','Directory'],['file','File']],existing.kind || 'directory');
    const recursive=input('recursive','','checkbox');recursive.checked=existing.recursive ?? true;
    const expires=input('expires_at','','datetime-local');
    if(existing.expires_at && Number.isFinite(dateMs(existing.expires_at))) { const date=new Date(dateMs(existing.expires_at)); expires.value=new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16); }
    const operations=el('fieldset'), legend=el('legend','Concrete operations'), checks=el('div',undefined,'checks'), operationInputs=[];
    for(const operation of ['list','read','write','create','delete','execute']) {
      const checkbox=input(operation,'','checkbox');checkbox.checked=(existing.operations || ['list','read','write','create','delete','execute']).includes(operation);
      checks.append(label(operation,checkbox));operationInputs.push(checkbox);
    }
    operations.append(legend,checks);
    const browse=button('Browse',()=>browsePath(value=>{target.value=value;},target.value || '/'));
    const pathRow=el('div',undefined,'product-toolbar');pathRow.append(browse);
    const add=el('button','Save draft rule','primary');add.type='submit';
    form.append(label('Absolute target path',target),pathRow,label('Target kind',kind),label('Worker scope',worker),label('Action',action),operations,label('Include descendants',recursive),label('Expiry (optional, local time)',expires),el('p','Linux directory ACLs couple write, create, and delete rights. Unsupported combinations are rejected by dry-run/apply; selecting an operation never claims independent OS enforcement. Execute does not stop an interpreter reading a script.','product-warning'),add);
    d.add(form);
    form.addEventListener('submit',event=>{
      event.preventDefault();const selected=operationInputs.filter(box=>box.checked).map(box=>box.name);
      if(!selected.length) {message(d.status,'Select at least one operation.',true);return;}
      if(expires.value && Date.parse(expires.value)<=Date.now()) {message(d.status,'Expiry must be in the future.',true);return;}
      const rule={...existing,id:existing.id || uniqueId(),worker:worker.value,target:target.value,kind:kind.value,action:action.value,operations:selected,recursive:recursive.checked,source:existing.source || 'manual',expires_at:expires.value?Math.floor(Date.parse(expires.value)/1000):null};
      const index=draft.rules.findIndex(item=>item.id===rule.id);
      if(index<0) draft.rules.push(rule);else draft.rules[index]=rule;
      d.close();markDirty();
    });target.focus();
  }
  async function reviewPolicy() {
    const d=dialog('Review permission impact');message(d.status,'Validating the draft against current revision…');
    const controller=new AbortController();d.node.addEventListener('close',()=>controller.abort());
    try {
      const body=policyBody(), result=await api('/api/control/dry-run',{method:'POST',body,signal:controller.signal});
      d.add(el('p','Preset: ' + draft.preset + ' · Workspace: ' + draft.workspace),el('p',draft.rules.length + ' draft rules · expected revision ' + body.expected_revision),el('p','Individual worker settings: '+JSON.stringify(body.worker_settings||{})));
      for(const rule of draft.rules) d.add(el('p',rule.target + ' · ' + ruleDescription(rule)));
      const impact=result.impact || {};d.add(el('pre',JSON.stringify(impact,null,2)));
      if(impact.restart_workers?.length) d.add(el('p','Applying will stop tasks and restart these workers: ' + impact.restart_workers.join(', ') + '. Cancel to keep them running.','product-warning'));
      d.add(el('p','Blocks take precedence over overlapping allows. Broad parent-directory changes affect descendants. Revoked access does not erase existing copies.','product-warning'));
      if(result.ok===false || result.valid===false || result.status==='rejected' || result.status==='failed') {message(d.status,result.error || 'The backend rejected this draft. Edit the rules and retry.',true);return;}
      message(d.status,'Draft validated. Nothing has changed yet.');
      const apply=button('Apply changes',async()=>{
        apply.disabled=true;d.actions.firstChild.textContent='Close (apply continues)';message(d.status,'Applying… waiting for backend confirmation.');
        try {
          const response=await api('/api/control/apply',{method:'POST',body});
          if(response.ok===false || response.status==='failed') throw new Error(response.error || 'Apply failed. The draft is preserved.');
          dirty=false; const loaded=await loadPolicy();message(d.status,loaded && policy?.enforced_revision===policy?.revision?'Backend confirmed enforced revision ' + policy.revision + '.':'Apply submitted. Enforcement could not be confirmed; refresh status to verify.'); apply.remove();d.actions.firstChild.textContent='Close';
        }catch(error){message(d.status,error.message + ' Draft preserved; refresh status before retrying a stale revision.',true);apply.disabled=false;}
      },'primary');d.actions.append(apply);
    } catch(error) {if(error.name!=='AbortError') message(d.status,error.message,true);}
  }
  async function decideApproval(approval,allow) {
    const d=dialog(allow?'Approve one operation':'Deny request');d.add(el('p',approval.worker + ' · ' + approval.operation + ' · ' + approval.target));
    const confirm=button(allow?'Approve once':'Deny',async()=>{
      confirm.disabled=true;
      try {await api('/api/control/approve',{method:'POST',body:{id:approval.id,allow}});d.close();await loadPolicy({preserveDraft:true});}
      catch(error){message(d.status,error.message,true);confirm.disabled=false;}
    },allow?'primary':'danger');d.actions.append(confirm);
  }
  function rollback(revision) {
    const d=dialog('Restore policy revision ' + revision);
    d.add(el('p','The backend validates this revision before activation. Managed workers may restart and their current tasks may stop. Current expected revision: ' + policy.revision,'product-warning'));
    const restore=button('Restore revision',async()=>{
      restore.disabled=true;message(d.status,'Restoring…');
      try{await api('/api/control/rollback',{method:'POST',body:{revision,expected_revision:policy.revision}});dirty=false;await loadPolicy();message(d.status,'Restore submitted. Review Desired / Enforced status for confirmation.');restore.remove();}
      catch(error){message(d.status,error.message,true);restore.disabled=false;}
    },'primary');d.actions.append(restore);
  }
  function scan() {
    const detectionScope=policyScope;
    const d=dialog('Auto Detect · review suggestions'),form=el('form'),scope=input('scope',draft.workspace || '/'),mode=select([['block','Block sensitive candidates'],['allow','Allow ordinary candidates']],'block');
    scope.required=true;scope.pattern='/.*';
    const content=input('content-scan','','checkbox'), contentLabel=label('Include bounded content scan (Gitleaks)',content);contentLabel.className='check';
    const start=el('button','Start scan','primary');start.type='submit';
    const results=el('div');form.append(label('Scope (absolute path)',scope),button('Browse scope',()=>browsePath(path=>{scope.value=path;},scope.value || '/')),label('Detection mode',mode),contentLabel,el('p','Metadata detection is the default. Content scanning runs only when selected, within this scope and server limits. Results include paths and reasons only; matching contents are never displayed. Allow means “No known sensitive marker”, never proven safe. Skipped and unreadable paths remain unknown.','product-warning'),start);
    d.add(form,results);
    let controller=null, findings=[],selected=new Set();
    const cancel=button('Cancel scan',()=>{controller?.abort();message(d.status,'Scan canceled. No policy changed.');});cancel.hidden=true;d.actions.prepend(cancel);
    d.node.addEventListener('close',()=>controller?.abort());
    form.addEventListener('submit',async event=>{
      event.preventDefault();controller=new AbortController();start.disabled=true;cancel.hidden=false;results.replaceChildren();findings=[];selected.clear();
      for(const old of d.actions.querySelectorAll('[data-review]')) old.remove();
      const scanMode=mode.value;message(d.status,'Scanning selected scope… no changes will be applied.');
      try {
        const data=await api('/api/control/scan',{method:'POST',body:{scope:scope.value,mode:scanMode,content:content.checked},signal:controller.signal});
        findings=data.findings || [];
        for(const [index,finding] of findings.entries()) {
          const row=el('div',undefined,'product-scan-row'),check=input('finding','','checkbox');
          check.addEventListener('change',()=>{if(check.checked)selected.add(index);else selected.delete(index);review.disabled=!selected.size;});
          row.append(label(finding.path,check),el('small',finding.reason + ' · Confidence: ' + finding.confidence));results.append(row);
        }
        if(data.skipped?.length) results.append(el('p','Skipped / unknown: ' + data.skipped.map(item=>typeof item==='string'?item:item.path + ': ' + (item.reason || item.error || 'skipped')).join('; '),'product-warning'));
        message(d.status,(findings.length?'Select individual findings to add to the draft.':'No suggestions found.') + (data.partial?' Partial scan: coverage is incomplete.':'') + (data.content_scanned ? ' Bounded content scan completed.' : ' Metadata scan only.') + ' Nothing has changed.');
        const review=button('Review selected',()=>{
          const chosen=[...selected].map(index=>findings[index]),confirm=dialog('Review ' + chosen.length + ' selected suggestions');
          confirm.add(el('p',chosen.map(finding=>finding.path).join('\n')),el('p','These ' + scanMode + ' rules will be added to the draft only. Review impact and Apply are required before enforcement.','product-warning'));
          confirm.actions.append(button('Add selected to draft',()=>{
            for(const finding of chosen) draft.rules.push({id:uniqueId(),worker:detectionScope,target:finding.path,action:scanMode,operations:['list','read','write','create','delete','execute'],recursive:true,source:'detection',expires_at:null});
            confirm.close();d.close();markDirty();
          },'primary'));
        },'primary');review.dataset.review='true';review.disabled=true;d.actions.append(review);
      }catch(error){if(error.name==='AbortError')message(d.status,'Scan canceled. No policy changed.');else message(d.status,error.message,true);}
      finally{start.disabled=false;cancel.hidden=true;}
    });
  }
  $('policy-refresh').addEventListener('click',()=>loadPolicy());
  $('apps-discover').addEventListener('click', async () => {
    const d=dialog('Detect web services'), results=el('div'), controller=new AbortController();
    d.add(el('p','Check web services listening on this server only. Detection reads no passwords and keeps each app’s authentication unchanged. Nothing is added automatically.','panel-note'),results);
    d.node.addEventListener('close',()=>controller.abort());
    message(d.status,'Checking host listeners…');
    try {
      const data=await api('/api/apps/discover',{method:'POST',body:{},signal:controller.signal});
      if(!d.node.isConnected)return;
      if(!data.available)throw new Error(data.reason || 'Discovery unavailable. Enter an application URL manually.');
      for(const candidate of data.apps || []) {
        const row=el('div',undefined,'product-scan-row');
        row.append(el('strong',candidate.url),el('p',candidate.scope+' · HTTP '+candidate.http_status+' · Login unchanged','panel-note'));
        if(candidate.loopback_only)row.append(el('p','This localhost link opens on the device using the browser. Configure its VPN relay before using it remotely.','product-warning'));
        row.append(button('Use this service',()=>{
          // Reuse the registry's existing validation/review form; never auto-save discovery.
          $('app-cancel').click();
          const form=$('app-form');
          form.elements.name.value=candidate.name;
          form.elements.url.value=candidate.url;
          form.elements.description.value='Detected web service on this server';
          $('app-form-status').textContent='Review the name and reachable URL, then choose Add application. Login remains unchanged.';
          d.close();form.elements.name.focus();form.scrollIntoView({block:'center'});
        }),button('Set up VPN access',()=>setupAppVpn(candidate)));results.append(row);
      }
      message(d.status,((data.apps || []).length+' web services detected. ')+(data.partial?'Partial result: listener limit reached. ':'')+(data.note || ''));
    }catch(error){if(error.name!=='AbortError'&&d.node.isConnected)message(d.status,error.message,true);}
  });
  function setupAppVpn(candidate) {
    const d=dialog('Set up app VPN access'), name=input('vpn-name',candidate.name), port=input('vpn-port',candidate.port,'number');
    port.min='1024';port.max='65535';name.maxLength=60;
    d.add(label('App name',name),label('VPN port',port),el('p','Forward '+candidate.url+' through WireGuard at 10.8.0.1. Only devices authorized by your VPN can reach this relay. Each app keeps its existing login behavior; apps without passwords stay without passwords.','panel-note'),el('p','Choose a different VPN port if this port is already in use. This does not configure your router or create a WireGuard tunnel.','product-warning'));
    const apply=button('Create VPN relay',async()=>{
      if(!name.value.trim()||!port.checkValidity()) {message(d.status,'Enter an app name and a valid VPN port.',true);return;}
      apply.disabled=true;message(d.status,'Creating the selected relay…');
      try {
        const target=new URL(candidate.url), backend=target.hostname.includes(':')?target.hostname.replace(/^\[|\]$/g,''):target.hostname;
        const address=(backend.includes(':')?'['+backend+']':backend)+':'+(target.port||(target.protocol==='https:'?'443':'80'));
        await api('/api/setup/vpn/apps/add',{method:'POST',body:{config:{name:name.value.trim(),target:address,port:Number(port.value)}}});
        target.hostname='10.8.0.1';target.port=port.value;
        $('app-cancel').click();const form=$('app-form');form.elements.name.value=name.value.trim();form.elements.url.value=target.href;
        $('app-form-status').textContent='VPN relay created. Choose Add application to save this shortcut. App login is unchanged.';
        message(d.status,'Relay configured at '+target.href+'. Add its shortcut in the application form.');apply.remove();d.actions.firstChild.textContent='Close';
      }catch(error){message(d.status,error.message,true);apply.disabled=false;}
    },'primary');d.actions.append(apply);
  }
  $('apps-vpn').addEventListener('click',async()=>{
    const d=dialog('App VPN relays'),list=el('div');d.add(list);message(d.status,'Loading VPN configuration…');
    const load=async()=>{
      const data=await api('/api/setup/vpn/apps');if(!d.node.isConnected)return;
      list.replaceChildren(el('p',data.wireguard_present?'WireGuard interface wg0 is present.':'WireGuard wg0 is unavailable. Open your existing WireGuard administration app to finish tunnel setup.','panel-note'));
      for(const relay of data.relays||[]) {
        const row=el('div',undefined,'product-scan-row');row.append(el('strong',relay.name),el('p',relay.target+' → '+relay.host+':'+relay.port+' · '+(relay.listening?'Listening':'Unavailable — remove and detect again')));
        row.append(button('Remove relay',()=>{
          const confirm=dialog('Remove VPN relay');confirm.add(el('p','Close '+relay.host+':'+relay.port+' and disconnect its active relay connections. The app and its saved shortcut remain.'));
          const remove=button('Confirm removal',async()=>{remove.disabled=true;try{await api('/api/setup/vpn/apps/remove',{method:'POST',body:{port:relay.port}});confirm.close();await load();}catch(error){message(confirm.status,error.message,true);remove.disabled=false;}},'danger');confirm.actions.append(remove);
        }));list.append(row);
      }
      message(d.status,(data.relays||[]).length+' additional app relays. Built-in relays are managed by the installed package. App authentication is unchanged.');
    };
    try{await load();}catch(error){if(d.node.isConnected)message(d.status,error.message,true);}
  });
  async function route() {
    await window.h07pSessionReady;
    const current=location.hash.slice(2);
    if(!['files','storage','permissions'].includes(current)) return;
    if(!session) { signIn(); return; }
    if(current==='files') await nas.load();
    if(current==='storage') await storage.load();
    if(current==='permissions') await loadPolicy({preserveDraft:true});
  }
  window.addEventListener('h07p-route',()=>{route().catch(error=>{account.title=error.message;signIn();});});
  window.h07pSessionReady = loadSession(false);
  window.h07pSessionReady.then(() => { if(!session) signIn(); }).catch(error=>{
    account.title=error.message;
    if(['files','storage','permissions'].includes(location.hash.slice(2))) signIn();
  });
})();
