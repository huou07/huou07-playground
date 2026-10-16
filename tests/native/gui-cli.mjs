async page => {
  const fixture = __H07P_SYNTHETIC_FIXTURE__;
  await page.setViewportSize({width:1280,height:900});
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(fixture.base+'/#/files');
  await page.evaluate(()=>window.h07pSessionReady);
  if(!(await page.locator('#owner-account').innerText()).includes('Sign out')){
    const login=page.getByRole('dialog',{name:'Owner sign in'});await login.waitFor();
    await login.getByLabel('Username').fill(fixture.username);await login.getByLabel('Password').fill(fixture.password);
    await login.getByRole('button',{name:'Sign in',exact:true}).click();
  }
  await page.getByRole('button',{name:'fixture.bin',exact:true}).waitFor();
  await page.waitForTimeout(2000);
  const paths=['/api/metrics','/api/services','/api/processes','/api/cockpit','/api/files','/api/apps','/api/vpn'];
  let counts={};const samples=[];
  page.on('request',request=>{const path='/'+request.url().split('/').slice(3).join('/').split('?')[0];if(paths.includes(path))counts[path]=(counts[path]||0)+1;});
  for(let sample=0;sample<1;sample++){
    counts={};await page.waitForTimeout(16000);
    samples.push({seconds:16,requests:{...counts},total:Object.values(counts).reduce((sum,value)=>sum+value,0)});
  }
  const latency=await page.evaluate(async()=>{
    const times=[];
    for(let sample=0;sample<20;sample++){
      const start=performance.now(),response=await window.h07pFetch('/api/fs/list?area=nas&path=%2F');
      if(!response.ok)throw Error('Synthetic NAS list failed');await response.json();times.push(performance.now()-start);
    }
    return times.sort((a,b)=>a-b);
  });
  if(fixture.variant==='candidate'){
    await page.getByRole('searchbox',{name:'Search NAS filenames'}).fill('FIXTURE');
    await page.locator('#nas-browser').getByRole('button',{name:'Search',exact:true}).click();
    await page.locator('#nas-browser').getByText(/Filenames only; file contents were not read/).waitFor();
    await page.locator('#sidebar [data-route="settings"]').click();
    await page.getByRole('button',{name:'Detect harnesses & manage workers'}).click();
    const workers=page.getByRole('dialog',{name:'Harness workers',exact:true});
    await workers.getByLabel('dsh-worker',{exact:true}).waitFor();
    await workers.getByRole('button',{name:'Cancel',exact:true}).click();
    await page.getByRole('button',{name:'Detect web services',exact:true}).click();
    const discovery=page.getByRole('dialog',{name:'Detect web services',exact:true});
    await discovery.getByRole('status').filter({hasText:/web services detected/}).waitFor({timeout:20000});
    await discovery.getByRole('button',{name:'Cancel',exact:true}).click();
    await page.getByRole('button',{name:'Detect passwords',exact:true}).click();
    const logins=page.getByRole('dialog',{name:'Selected app login passwords'});
    await logins.getByRole('checkbox',{name:/OpenCode public web/}).waitFor();
    if(await logins.getByRole('checkbox',{name:/OpenCode public web/}).isChecked())throw Error('Login export must start unselected');
    await logins.getByRole('button',{name:'Cancel',exact:true}).click();
    await page.setViewportSize({width:390,height:844});
    await page.getByRole('button',{name:'Detect harnesses & manage workers'}).click();
    const mobile=page.getByRole('dialog',{name:'Harness workers',exact:true});
    await mobile.getByLabel('dsh-worker',{exact:true}).waitFor();
    const box=await mobile.boundingBox();
    if(!box||box.x<0||box.x+box.width>391)throw Error('Worker dialog exceeds mobile width');
    await mobile.getByRole('button',{name:'Cancel',exact:true}).click();
  }
  if(errors.length)throw Error(errors.join('; '));
  return {variant:fixture.variant,samples,nas_list_ms:{median:latency[9],p95:latency[18]},browser_errors:errors.length,synthetic_login:true,production_credentials_used:false};
}
