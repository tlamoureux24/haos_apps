"""Dependency-free administration UI assets served only by the Ingress listener."""

ADMIN_CSS = """
:root{color-scheme:light dark;font-family:Inter,system-ui,sans-serif;background:#f4f7fb;color:#13233a}
*{box-sizing:border-box}body{margin:0}header{background:#102a43;color:#fff;padding:28px clamp(20px,5vw,64px)}
header p{color:#9fd8ed;margin:.4rem 0 0}.shell{max-width:1120px;margin:auto;padding:28px 20px 60px}
.summary,.panel{background:#fff;border:1px solid #dbe5ef;border-radius:14px;box-shadow:0 8px 24px #102a4312}
.summary{display:flex;gap:32px;padding:20px;margin-bottom:22px}.metric strong{display:block;font-size:1.7rem}.metric span,.muted{color:#60758a}
.grid{display:grid;grid-template-columns:minmax(280px,380px) 1fr;gap:22px}.panel{padding:22px}h1,h2{margin-top:0}
label{display:block;font-weight:600;margin:14px 0 6px}input,select{width:100%;padding:10px;border:1px solid #b9c8d8;border-radius:8px;background:#fff;color:#13233a}
fieldset{border:0;padding:0;margin:14px 0}fieldset label{font-weight:400;margin:8px 0}fieldset input{width:auto;margin-right:8px}
button{border:0;border-radius:8px;padding:10px 14px;background:#087ea4;color:#fff;font-weight:700;cursor:pointer}button.danger{background:#b42318}button:disabled{opacity:.5}
.identity{border-top:1px solid #e2eaf2;padding:16px 0}.identity:first-child{border-top:0}.identity-head{display:flex;justify-content:space-between;gap:12px}.tag{padding:3px 8px;border-radius:99px;background:#e5f5fb;color:#075b78;font-size:.8rem}.revoked{background:#fbe9e7;color:#8f1d15}
.actions{font-family:ui-monospace,monospace;font-size:.82rem;color:#52677b}.credential{display:none;margin-top:18px;padding:16px;background:#fff4d6;border:1px solid #efbd49;border-radius:10px}.credential.show{display:block}.credential code{display:block;overflow-wrap:anywhere;margin:10px 0}.error{color:#b42318}
@media(max-width:760px){.grid{grid-template-columns:1fr}.summary{flex-wrap:wrap}}
@media(prefers-color-scheme:dark){:root{background:#101820;color:#e7eef6}.summary,.panel{background:#182430;border-color:#304253}input,select{background:#101820;color:#e7eef6;border-color:#506579}.muted,.metric span{color:#a9bacb}.identity{border-color:#304253}.actions{color:#b9c8d8}}
"""

ADMIN_JS = r"""
const root=document.querySelector('main'),base=root.dataset.base,csrf=root.dataset.csrf;
const api=(path,options={})=>fetch(base+path,{...options,headers:{'X-CSRF-Token':csrf,'Content-Type':'application/json',...(options.headers||{})}}).then(async r=>{const body=await r.json();if(!r.ok)throw new Error(body.error?.code||`HTTP ${r.status}`);return body});
const esc=value=>String(value??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
async function refresh(){const [status,data]=await Promise.all([api('/admin/api/v1/status'),api('/admin/api/v1/identities')]);document.querySelector('#total').textContent=status.identities;document.querySelector('#active').textContent=status.active_identities;document.querySelector('#identities').innerHTML=data.identities.length?data.identities.map(i=>`<article class="identity"><div class="identity-head"><div><strong>${esc(i.display_name)}</strong><div class="muted">${esc(i.identity_type)} · ${esc(i.created_at)}</div></div><span class="tag ${i.status==='revoked'?'revoked':''}">${esc(i.status)}</span></div><p class="actions">${esc(i.gateway_actions.join(', ')||'aucune permission')}</p>${i.status==='active'?`<button class="danger revoke" data-id="${esc(i.id)}">Révoquer</button>`:''}</article>`).join(''):'<p class="muted">Aucune identité configurée.</p>';document.querySelectorAll('.revoke').forEach(b=>b.onclick=async()=>{if(confirm('Révoquer immédiatement cette identité et ses identifiants ?')){await api('/admin/api/v1/identities/revoke',{method:'POST',body:JSON.stringify({identity_id:b.dataset.id})});refresh()}})}
document.querySelector('#create').onsubmit=async event=>{event.preventDefault();const form=new FormData(event.target),actions=form.getAll('actions');try{const result=await api('/admin/api/v1/identities',{method:'POST',body:JSON.stringify({display_name:form.get('display_name'),identity_type:form.get('identity_type'),actions})});const box=document.querySelector('#credential');box.classList.add('show');box.querySelector('code').textContent=result.credential;event.target.reset();await refresh()}catch(error){document.querySelector('#message').textContent=error.message}};
refresh().catch(error=>document.querySelector('#message').textContent=error.message);
"""
