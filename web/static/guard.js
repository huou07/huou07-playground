(() => {
  'use strict';
  const panel = document.getElementById('credential-guard');
  let signedIn = false, generation = 0, busy = false;
  const node = (tag, text, cls) => { const n = document.createElement(tag); if(text !== undefined)n.textContent=text; if(cls)n.className=cls; return n; };
  const button = (text, action) => { const b=node('button',text);b.type='button';b.addEventListener('click',action);return b; };
  const field = (text, input) => { const label=node('label',text);label.append(input);return label; };
  async function api(op, body) {
    const response=await window.h07pFetch('/api/security/credential-guard/'+op,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await response.json();if(!response.ok)throw new Error(data.error||'Guard request failed');return data;
  }
  async function load() {
    if(!signedIn || busy || location.hash!=='#/permissions')return;
    const epoch=++generation;busy=true;
    try {
      const [data, incidents]=await Promise.all([api('status'),api('events')]);
      if(epoch!==generation || !signedIn)return;
      const title=node('h2','Credential Guard · '+data.state), status=node('p','', 'product-status');status.setAttribute('role','status');
      const warning=node('p',data.limitation,'product-warning');
      const watcher=node('p','Configuration revision: '+data.config.revision+' · Watcher: '+data.watcher.state+' · '+(data.watcher.watches||0)+' watched folders. '+(data.watcher.reason||''),'product-status');
      const form=node('form'),enabled=node('input'),content=node('input'),scopes=node('textarea'),exports=node('textarea');
      enabled.type=content.type='checkbox';enabled.checked=data.config.enabled;content.checked=data.config.content;
      scopes.value=data.config.scopes.join('\n');exports.value=data.config.safe_exports.join('\n');
      scopes.rows=exports.rows=2;scopes.placeholder=exports.placeholder='/home/huou07/Projects/…/log-exports';
      const save=node('button','Save Guard settings');save.type='submit';
      form.className='guard-form';
      form.append(field('Monitor filesystem metadata',enabled),field('Scan closed registered exports for known secret signatures',content),field('Watch folders (one per line, within Projects)',scopes),field('Closed export folders allowed for cleanup (one per line)',exports),node('p','Only closed UTF-8 text exports up to 1 MiB are supported. Native authentication stores and live journals are excluded. Content scanning is opt-in; existing OS protections remain active when monitoring is off.','product-status'),save);
      const run=async(action)=>{
        if(busy)return;busy=true;status.textContent='Working…';
        const buttons=[...panel.querySelectorAll('button')].map(b=>[b,b.disabled]);
        for(const [b] of buttons)b.disabled=true;
        try{await action();}catch(e){if(epoch===generation)status.textContent=e.message;}
        finally{busy=false;if(epoch===generation)for(const [b,disabled] of buttons)if(b.isConnected)b.disabled=disabled;}
      };
      form.addEventListener('submit',event=>{event.preventDefault();run(async()=>{
        const split=s=>s.split('\n').map(p=>p.trim()).filter(Boolean);
        await api('configure',{revision:data.config.revision,enabled:enabled.checked,content:content.checked,scopes:split(scopes.value),safe_exports:split(exports.value)});
        busy=false;await load();
      });});
      const path=node('input');path.type='text';path.placeholder='/home/huou07/Projects/…/log-exports/closed.log';path.id='guard-log-path';
      const review=node('div'), cleanArea=node('div');cleanArea.className='product-path';
      const preview=button('Preview log cleanup',()=>run(async()=>{
        review.replaceChildren();const result=await api('plan',{path:path.value});if(epoch!==generation)return;
        const s=result.summary;
        review.append(node('p',`${s.redacted_lines} / ${s.lines} lines redacted · ${s.bytes_before} → ${s.bytes_after} bytes${s.fully_suppressed?' · Entire export suppressed because signatures remain':''}. Original retained privately. Cleaned file becomes owner-only (0600).`,'product-warning'));
        const confirm=node('input');confirm.type='checkbox';
        const apply=button('Clean reviewed export',()=>run(async()=>{
          await api('clean',{plan_id:result.plan_id,confirmed:confirm.checked});busy=false;await load();
        }));apply.disabled=true;confirm.addEventListener('change',()=>{apply.disabled=!confirm.checked;});
        review.append(field('I confirm this closed export may be replaced',confirm),apply);
        status.textContent=s.claim;
      }));
      cleanArea.append(field('Closed log export path',path),preview);
      const recoveries=node('div');recoveries.append(node('h3','Retained originals'));
      for(const entry of data.quarantine){
        const row=node('div',undefined,'product-rule');row.append(node('p',entry.path+' · '+entry.state+' · '+entry.bytes+' bytes'),button('Restore original to private NAS',()=>run(async()=>{
          const result=await api('restore',{id:entry.id});status.textContent='Restored to private NAS: '+result.path+'. Original backup remains private.';
        })));recoveries.append(row);
      }
      if(!data.quarantine.length)recoveries.append(node('p','No retained originals.','product-status'));
      const events=node('div');events.append(node('h3','Recent metadata events'));
      for(const entry of incidents.events){
        const row=node('div',undefined,'product-rule');row.append(node('p',new Date(entry.at*1000).toLocaleString()+' · '+entry.kind+(entry.path?' · '+entry.path:'')));
        if(!entry.acknowledged)row.append(button('Acknowledge event',()=>run(async()=>{await api('ack',{id:entry.id});busy=false;await load();})));
        events.append(row);
      }
      const refresh=button('Refresh Guard',()=>load());
      panel.replaceChildren(title,warning,watcher,node('p',data.source_redaction,'product-status'),form,cleanArea,review,status,recoveries,events,refresh);
    }catch(e){if(epoch===generation)panel.replaceChildren(node('h2','Credential Guard'),node('p',e.message,'product-status product-error'),button('Retry Guard',()=>load()));}
    finally{busy=false;}
  }
  window.addEventListener('h07p-owner-session',event=>{
    signedIn=!!event.detail;generation++;
    if(!signedIn){panel.replaceChildren(node('h2','Credential Guard'),node('p','Sign in to view Guard status.','product-status'));busy=false;}
    else load();
  });
  window.addEventListener('h07p-route',()=>load());
})();
