const API='cgi-bin/api.sh';
let jobs=[],jobStatuses={},editingJobId=null;
const statusTimers={};
const supportedLanguages=['fr','en'];
const storedLanguage=localStorage.getItem('rsync-manager-language');
const browserLanguage=(navigator.language||'fr').slice(0,2);
let language=supportedLanguages.includes(storedLanguage)?storedLanguage:(browserLanguage==='en'?'en':'fr');

const EN={
    'Changer de langue':'Change language','Changer de thème':'Change theme','Gestion':'Management',
    'Synchronisations':'Synchronizations','Planifiez, lancez et contrôlez les copies locales ou SMB/CIFS.':'Schedule, run and monitor local or SMB/CIFS copies.',
    'Actualiser':'Refresh','Ajouter un job':'Add job','Synthèse des jobs':'Job summary','Jobs configurés':'Configured jobs','Jobs actifs':'Active jobs',
    'Dernières réussites':'Latest successes','Derniers échecs':'Latest failures','Une carte résume la planification et la dernière exécution.':'Each card summarizes scheduling and the latest run.',
    'Notifications SMTP':'SMTP notifications','Configurez les rapports envoyés après les synchronisations.':'Configure reports sent after synchronizations.',
    'Serveur et sécurité':'Server and security','Connexion au relais de messagerie.':'Mail relay connection.','Activer les emails':'Enable email',
    'Envoyer les résultats des jobs selon leur configuration.':'Send job results according to their configuration.','Serveur':'Server','Port':'Port',
    'Authentification':'Authentication','Oui':'Yes','Non':'No','TLS actif':'TLS enabled','STARTTLS (port 587)':'STARTTLS (port 587)',
    'Compte et destinataire':'Account and recipient','Les identifiants sont conservés dans les données privées de l’App.':'Credentials are stored in the App private data.',
    'Utilisateur':'Username','Mot de passe':'Password','Expéditeur':'Sender','Destinataire':'Recipient','Envoyer un test':'Send test','Enregistrer':'Save',
    'Import et export':'Import and export','Sauvegardez ou restaurez séparément les notifications et les jobs.':'Back up or restore notifications and jobs separately.',
    'Informations sensibles':'Sensitive information','Les exports contiennent les mots de passe SMTP et SMB/CIFS en clair. Conservez ces fichiers dans un emplacement sûr.':'Exports contain SMTP and SMB/CIFS passwords in plain text. Keep these files in a secure location.',
    'Configuration SMTP':'SMTP configuration','Serveur, sécurité, compte et destinataire.':'Server, security, account and recipient.','Importer':'Import','Exporter':'Export',
    'Configuration des jobs':'Job configuration','Planifications, chemins, partages et exclusions.':'Schedules, paths, shares and exclusions.',
    'Fermer':'Close','Nom':'Name','Nom du job (obligatoire)':'Job name (required)','0 3 * * * (obligatoire)':'0 3 * * * (required)',
    'Actif':'Enabled','Inclure dans la planification cron.':'Include in cron scheduling.','Source':'Source','Données à synchroniser.':'Data to synchronize.',
    'Cible':'Target','Destination de la synchronisation.':'Synchronization destination.','Type':'Type','Chemin local':'Local path',
    'Chemin local (obligatoire)':'Local path (required)','Hôte':'Host','Adresse IP ou nom (obligatoire)':'IP address or hostname (required)',
    'Partage':'Share','Partage réseau (obligatoire)':'Network share (required)','Sous-dossier':'Subfolder','Sous-dossier dans le partage (optionnel)':'Subfolder in share (optional)',
    'Login (optionnel)':'Username (optional)','Mot de passe (optionnel)':'Password (optional)','Domaine / Workgroup':'Domain / Workgroup',
    'Domaine/Workgroup (optionnel)':'Domain/Workgroup (optional)','Exclusions rsync':'rsync exclusions',
    'Exclusions optionnelles, une règle par ligne\ncache/\n*.tmp\n@eaDir/':'Optional exclusions, one rule per line\ncache/\n*.tmp\n@eaDir/',
    'Supprimer':'Delete','Tester les montages':'Test mounts','Simuler':'Dry run','Lancer':'Run','Journal d’exécution':'Execution log','Dernier log':'Latest log',
    'Chargement…':'Loading…','Aucun job créé.':'No jobs created.','Créez un premier job pour commencer.':'Create your first job to get started.',
    'Job sans nom':'Unnamed job','Désactivé':'Disabled','Jamais exécuté':'Never run','Planification':'Schedule','Dernière exécution':'Latest run',
    'Voir le dernier log':'View latest log','Modifier le job':'Edit job','Statut inconnu':'Unknown status','manuel':'manual','test montages':'mount test',
    'Jobs enregistrés et planification cron mise à jour.':'Jobs saved and cron schedule updated.','Sauvegarde jobs refusée':'Job save rejected',
    'Job enregistré et planification cron mise à jour.':'Job saved and cron schedule updated.','Job supprimé et planification cron mise à jour.':'Job deleted and cron schedule updated.',
    'Job activé.':'Job enabled.','Job désactivé.':'Job disabled.','Export de la configuration email prêt.':'Email configuration export ready.',
    'Export de la configuration jobs prêt.':'Job configuration export ready.','La configuration email doit être un objet JSON.':'The email configuration must be a JSON object.',
    'Import email refusé':'Email import rejected','Configuration email importée et prise en compte.':'Email configuration imported and applied.',
    'La configuration jobs doit être un tableau JSON.':'The job configuration must be a JSON array.','Import jobs refusé':'Job import rejected',
    'Configuration jobs importée, cron régénéré.':'Job configuration imported and cron regenerated.','Erreur sauvegarde inconnue':'Unknown save error',
    'Configuration enregistrée.':'Configuration saved.','Test email en cours…':'Email test in progress…','Email de test envoyé.':'Test email sent.',
    'Log indisponible':'Log unavailable','Action refusée':'Action rejected','Succès':'Success','Échec':'Failed','Erreur montage':'Mount error','Montages OK':'Mounts OK',
    'Configuration JSON invalide':'Invalid configuration JSON','Impossible de sauvegarder la configuration':'Unable to save configuration',
    'Jobs JSON invalide':'Invalid jobs JSON','Jobs sauvegardés, mais impossible de régénérer le cron':'Jobs saved, but unable to regenerate cron',
    'Impossible de sauvegarder les jobs':'Unable to save jobs','Id job invalide':'Invalid job ID','Aucun log disponible pour ce job':'No log available for this job',
    'Action inconnue':'Unknown action','Fichier JSON invalide.':'Invalid JSON file.','Impossible de lire le fichier.':'Unable to read the file.'
};
const t=text=>language==='en'?(EN[text]||text):text;

function applyLanguage(){
    document.documentElement.lang=language;
    document.querySelectorAll('body *').forEach(element=>{
        if(['SCRIPT','STYLE'].includes(element.tagName))return;
        element.childNodes.forEach(node=>{if(node.nodeType===Node.TEXT_NODE){const value=node.nodeValue.trim();if(value&&EN[value])node.nodeValue=node.nodeValue.replace(value,t(value));}});
        ['placeholder','title','aria-label'].forEach(attribute=>{const value=element.getAttribute(attribute);if(value&&EN[value])element.setAttribute(attribute,t(value));});
    });
    document.querySelector('#language-toggle').textContent=language==='fr'?'EN':'FR';
    render();
}
function setLanguage(){language=language==='fr'?'en':'fr';localStorage.setItem('rsync-manager-language',language);location.reload();}
function setTheme(value){const theme=value==='dark'?'dark':'light';document.documentElement.dataset.theme=theme;localStorage.setItem('rsync-manager-theme',theme);const button=document.querySelector('#theme-toggle');button.textContent=theme==='dark'?'☀':'☾';button.title=theme==='dark'?(language==='en'?'Light theme':'Mode clair'):(language==='en'?'Dark theme':'Mode sombre');}

function setView(name){
    const safe=['jobs','smtp','management'].includes(name)?name:'jobs';
    document.querySelectorAll('.view').forEach(view=>view.classList.toggle('active',view.id===safe));
    document.querySelectorAll('.nav a').forEach(link=>link.classList.toggle('active',link.dataset.view===safe));
    if(location.hash!==`#${safe}`)history.replaceState(null,'',`#${safe}`);
}
function setStatus(message,type='info',target='jobs-status',autoHide=true){
    const element=document.getElementById(target);clearTimeout(statusTimers[target]);element.className=`notice ${type}`;element.textContent=t(message);element.hidden=false;
    if(autoHide)statusTimers[target]=setTimeout(()=>{element.hidden=true;element.textContent='';},5000);
}
async function apiFetch(action,options={}){const response=await fetch(`${API}?action=${action}`,{cache:'no-store',...options});const body=await response.text();if(!response.ok)throw new Error(`HTTP ${response.status}: ${body||response.statusText}`);try{return JSON.parse(body);}catch{throw new Error(`${language==='en'?'Non-JSON API response for':'Réponse API non JSON pour'} ${action}: ${body.slice(0,300)}`);}}
function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));}
function downloadJson(data,filename){const blob=new Blob([`${JSON.stringify(data,null,2)}\n`],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=filename;document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);}
function readJsonFile(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>{try{resolve(JSON.parse(reader.result));}catch{reject(new Error(t('Fichier JSON invalide.')));}};reader.onerror=()=>reject(new Error(t('Impossible de lire le fichier.')));reader.readAsText(file);});}
function generateJobId(){return `job_${Date.now()}_${Math.random().toString(36).slice(2,10)}`;}
function normalizeSide(side={}){if(typeof side==='string')return{type:'local',path:side,host:'',share:'',subpath:'',domain:'',user:'',pass:''};let host=side.host||'',share=side.share||'',subpath=side.subpath||'',path=side.path||'';if(side.type==='cifs'&&(!host||!share)&&path.startsWith('//')){const parts=path.replace(/^\/+/, '').split('/');host=host||parts.shift()||'';share=share||parts.shift()||'';subpath=subpath||parts.join('/');}if(side.type==='cifs'&&share.includes('/')){const parts=share.replace(/^\/+/, '').split('/');if(host&&parts[0]===host)parts.shift();share=parts.shift()||'';subpath=subpath||parts.join('/');}return{type:side.type||'local',path,host,share,subpath,domain:side.domain||'',user:side.user||'',pass:side.pass||''};}
function ensureJobIds(){const seen=new Set();jobs=jobs.map(job=>{let id=typeof job.id==='string'&&/^job_[A-Za-z0-9_-]+$/.test(job.id)?job.id:'';if(!id||seen.has(id))id=generateJobId();seen.add(id);return{...job,id,enabled:job.enabled!==false,excludes:Array.isArray(job.excludes)?job.excludes:[],source:normalizeSide(job.source),target:normalizeSide(job.target)};});}
function defaultJob(){return{id:generateJobId(),enabled:true,excludes:[],name:'',cron:'',source:normalizeSide(),target:normalizeSide()};}
function formatDate(value){if(!value)return'';const date=new Date(value);return Number.isNaN(date.getTime())?value:date.toLocaleString(language==='en'?'en-GB':'fr-FR');}
function formatDuration(seconds){seconds=Number(seconds||0);if(seconds<60)return`${seconds}s`;const minutes=Math.floor(seconds/60),rest=seconds%60;if(minutes<60)return`${minutes}min ${rest}s`;return`${Math.floor(minutes/60)}h ${minutes%60}min ${rest}s`;}
function endpointLabel(side){side=normalizeSide(side);if(side.type==='cifs')return`//${side.host||'?'}/${side.share||'?'}${side.subpath?`/${side.subpath}`:''}`;return side.path||'—';}
function statusClass(status){if(status==='success')return'success';if(status==='failed'||status==='mount_error')return status;if(status==='running')return'running';return'';}
function modeLabel(mode){if(mode==='mount_test')return t('test montages');return mode==='dry'?'dry-run':'run';}

function updateMetrics(){
    document.querySelector('#metric-total').textContent=jobs.length;
    document.querySelector('#metric-active').textContent=jobs.filter(job=>job.enabled!==false).length;
    document.querySelector('#metric-success').textContent=jobs.filter(job=>jobStatuses[job.id]?.status==='success').length;
    document.querySelector('#metric-failed').textContent=jobs.filter(job=>['failed','mount_error'].includes(jobStatuses[job.id]?.status)).length;
    document.querySelector('#jobs-count').textContent=jobs.length;
}
function render(){
    ensureJobIds();updateMetrics();const list=document.querySelector('#jobs-list');if(!list)return;
    if(!jobs.length){list.innerHTML=`<div class="empty"><div class="empty-icon">⇄</div><strong>${t('Aucun job créé.')}</strong><p>${t('Créez un premier job pour commencer.')}</p></div>`;return;}
    list.innerHTML=jobs.map(job=>{const status=jobStatuses[job.id];const state=job.enabled===false?`<span class="pill disabled">${t('Désactivé')}</span>`:status?`<span class="pill ${statusClass(status.status)}">${escapeHtml(t(status.label||'Statut inconnu'))}</span>`:`<span class="pill">${t('Jamais exécuté')}</span>`;const details=status?[status.finished_at?`${t('Dernière exécution')} : ${formatDate(status.finished_at)}`:'',status.trigger==='cron'?'cron':t('manuel'),status.mode?modeLabel(status.mode):'',Number.isFinite(Number(status.duration_seconds))?formatDuration(status.duration_seconds):''].filter(Boolean).join(' · '):'';const stats=status?[status.bytes_sent?`${language==='en'?'sent':'envoyé'} ${status.bytes_sent}`:'',status.bytes_received?`${language==='en'?'received':'reçu'} ${status.bytes_received}`:'',status.total_size?`total ${status.total_size}`:''].filter(Boolean).join(' · '):'';return`<article class="job-item"><div class="job-main" data-edit-job="${escapeHtml(job.id)}" tabindex="0" role="button"><div class="job-title-row"><span class="job-title">${escapeHtml(job.name||t('Job sans nom'))}</span>${state}</div><div class="job-route"><span>${escapeHtml(endpointLabel(job.source))}</span><span class="arrow">→</span><span>${escapeHtml(endpointLabel(job.target))}</span></div><div class="job-meta"><span class="pill">${t('Planification')} · ${escapeHtml(job.cron||'—')}</span>${details?`<span>${escapeHtml(details)}</span>`:''}</div>${stats?`<div class="job-stats">${escapeHtml(stats)}</div>`:''}</div><div class="job-side"><label class="switch-row compact" title="${job.enabled!==false?t('Actif'):t('Désactivé')}"><input type="checkbox" data-toggle-job="${escapeHtml(job.id)}" ${job.enabled!==false?'checked':''}><span><strong>${job.enabled!==false?t('Actif'):t('Désactivé')}</strong></span></label><div class="job-actions"><button class="icon-button" data-log-job="${escapeHtml(job.id)}" type="button" title="${t('Voir le dernier log')}" aria-label="${t('Voir le dernier log')}">≡</button><button class="icon-button" data-edit-job="${escapeHtml(job.id)}" type="button" title="${t('Modifier le job')}" aria-label="${t('Modifier le job')}">✎</button></div></div></article>`;}).join('');
}
async function load(){try{jobs=await apiFetch('list_jobs');ensureJobIds();jobStatuses=await apiFetch('get_status');const config=await apiFetch('get_config');Object.entries(config).forEach(([key,value])=>{const element=document.getElementById(key);if(element)element.type==='checkbox'?element.checked=value:element.value=value;});render();}catch(error){setStatus(error.message,'error');}}
async function persistJobs(message=t('Jobs enregistrés et planification cron mise à jour.')){ensureJobIds();const result=await apiFetch('save_jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(jobs)});if(result.status!=='ok')throw new Error(result.error||t('Sauvegarde jobs refusée'));jobs=await apiFetch('list_jobs');ensureJobIds();jobStatuses=await apiFetch('get_status');render();if(message)setStatus(message,'success');}

function openShell(id){document.getElementById(id).hidden=false;document.body.classList.add('drawer-open');document.querySelector(`#${id} .drawer`)?.focus();}
function closeShell(id){document.getElementById(id).hidden=true;if(document.querySelectorAll('.drawer-shell:not([hidden])').length===0)document.body.classList.remove('drawer-open');}
function setModalSide(name,side){side=normalizeSide(side);['type','path','host','share','subpath','user','pass','domain'].forEach(key=>{document.getElementById(`job_${name}_${key}`).value=side[key]||'';});}
function getModalSide(name){return normalizeSide({type:document.getElementById(`job_${name}_type`).value,path:document.getElementById(`job_${name}_path`).value.trim(),host:document.getElementById(`job_${name}_host`).value.trim(),share:document.getElementById(`job_${name}_share`).value.trim(),subpath:document.getElementById(`job_${name}_subpath`).value.trim(),user:document.getElementById(`job_${name}_user`).value.trim(),pass:document.getElementById(`job_${name}_pass`).value,domain:document.getElementById(`job_${name}_domain`).value.trim()});}
function updateSideVisibility(){['source','target'].forEach(name=>{const cifs=document.getElementById(`job_${name}_type`).value==='cifs';document.getElementById(`job_${name}_local`).hidden=cifs;document.getElementById(`job_${name}_cifs`).hidden=!cifs;});document.getElementById('modal-mount-test-btn').hidden=!['source','target'].some(name=>document.getElementById(`job_${name}_type`).value==='cifs');}
function clearValidation(){document.querySelectorAll('#job-drawer .invalid').forEach(element=>element.classList.remove('invalid'));document.getElementById('job-validation-message').hidden=true;}
function validateJob(){clearValidation();const errors=[],mark=(id,label)=>{document.getElementById(id)?.classList.add('invalid');errors.push(label);};if(!document.getElementById('job_name').value.trim())mark('job_name',t('Nom'));if(!document.getElementById('job_cron').value.trim())mark('job_cron','Cron');['source','target'].forEach(name=>{const label=name==='source'?t('Source'):t('Cible'),type=document.getElementById(`job_${name}_type`).value;if(type==='local'&&!document.getElementById(`job_${name}_path`).value.trim())mark(`job_${name}_path`,`${label}: ${language==='en'?'local path':'chemin local'}`);if(type==='cifs'){if(!document.getElementById(`job_${name}_host`).value.trim())mark(`job_${name}_host`,`${label}: ${language==='en'?'host':'hôte'}`);if(!document.getElementById(`job_${name}_share`).value.trim())mark(`job_${name}_share`,`${label}: ${language==='en'?'share':'partage'}`);}});if(errors.length){const message=document.getElementById('job-validation-message');message.textContent=`${language==='en'?'Missing required fields':'Champs obligatoires manquants'} : ${errors.join(', ')}.`;message.hidden=false;return false;}return true;}
function jobFromFields(){return{id:editingJobId||generateJobId(),enabled:document.getElementById('job_enabled').checked,excludes:document.getElementById('job_excludes').value.split('\n').map(line=>line.trim()).filter(Boolean),name:document.getElementById('job_name').value.trim(),cron:document.getElementById('job_cron').value.trim(),source:getModalSide('source'),target:getModalSide('target')};}
function openJob(jobId=null){const job=jobs.find(item=>item.id===jobId)||defaultJob(),isNew=!jobId;editingJobId=job.id;document.getElementById('job-drawer-title').textContent=isNew?t('Ajouter un job'):`${language==='en'?'Edit':'Modifier'} : ${job.name||'Job'}`;document.getElementById('job_name').value=job.name||'';document.getElementById('job_cron').value=job.cron||'';document.getElementById('job_enabled').checked=job.enabled!==false;document.getElementById('job_excludes').value=(job.excludes||[]).join('\n');setModalSide('source',job.source);setModalSide('target',job.target);document.getElementById('delete-job-btn').hidden=isNew;clearValidation();updateSideVisibility();openShell('job-drawer-shell');}
async function saveCurrentJob(close=true){try{if(!validateJob())return null;const job=jobFromFields(),index=jobs.findIndex(item=>item.id===job.id);if(index>=0)jobs[index]=job;else jobs.push(job);await persistJobs(t('Job enregistré et planification cron mise à jour.'));if(close)closeShell('job-drawer-shell');return job;}catch(error){setStatus(error.message,'error');return null;}}
async function deleteCurrentJob(){const job=jobFromFields();if(!confirm(language==='en'?`Delete job "${job.name}"?`:`Supprimer le job « ${job.name} » ?`))return;try{jobs=jobs.filter(item=>item.id!==job.id);await persistJobs(t('Job supprimé et planification cron mise à jour.'));closeShell('job-drawer-shell');}catch(error){setStatus(error.message,'error');}}
async function toggleJob(jobId,enabled){const index=jobs.findIndex(item=>item.id===jobId);if(index<0)return;const previous=jobs[index].enabled;jobs[index].enabled=enabled;render();try{await persistJobs(t(enabled?'Job activé.':'Job désactivé.'));}catch(error){jobs[index].enabled=previous;render();setStatus(error.message,'error');}}
async function saveAndRun(mode){const job=await saveCurrentJob(false);if(job)await runJob(job.id,mode);}
async function runJob(id,mode){try{const result=await apiFetch(`${mode}&id=${encodeURIComponent(id)}`);if(result.status!=='started')throw new Error(result.error||t('Action refusée'));const action=mode==='dry'?'Dry-run':mode==='mount_test'?t('Tester les montages'):(language==='en'?'Manual run':'Exécution manuelle');const job=jobs.find(item=>item.id===id),name=job?.name?`${language==='en'?' for ':' pour '}${job.name}`:'';setStatus(`${action}${name}${language==='en'?' started.':' lancée.'}`,'success');setTimeout(load,2000);}catch(error){setStatus(error.message,'error');}}
async function showLog(id){const job=jobs.find(item=>item.id===id);document.getElementById('log-drawer-title').textContent=job?.name?`${t('Dernier log')} : ${job.name}`:t('Dernier log');document.getElementById('job-log-content').textContent=t('Chargement…');openShell('log-drawer-shell');try{const result=await apiFetch(`get_log&id=${encodeURIComponent(id)}`);if(result.status!=='ok')throw new Error(result.error||t('Log indisponible'));document.getElementById('job-log-content').textContent=result.log||'';}catch(error){document.getElementById('job-log-content').textContent=error.message;}}

async function saveConfig(show=true){try{const config={};document.querySelectorAll('#smtp input,#smtp select').forEach(element=>config[element.id]=element.type==='checkbox'?element.checked:element.value);const result=await apiFetch('save_config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});if(result.status!=='ok')throw new Error(result.error||t('Erreur sauvegarde inconnue'));if(show)setStatus(t('Configuration enregistrée.'),'success','email-status');return true;}catch(error){setStatus(error.message,'error','email-status');return false;}}
async function testEmail(){if(!await saveConfig(false))return;setStatus(t('Test email en cours…'),'info','email-status',false);try{const result=await apiFetch('test_email');if(result.status==='sent')setStatus(t('Email de test envoyé.'),'success','email-status');else setStatus(`${language==='en'?'Email sending error':'Erreur envoi email'} : ${result.error||'—'}`,'error','email-status');}catch(error){setStatus(error.message,'error','email-status');}}
async function exportConfig(kind){try{const email=kind==='email',data=await apiFetch(email?'get_config':'list_jobs');downloadJson(data,email?'rsync-manager-email-config.json':'rsync-manager-jobs-config.json');setStatus(t(email?'Export de la configuration email prêt.':'Export de la configuration jobs prêt.'),'success','management-status');}catch(error){setStatus(error.message,'error','management-status');}}
async function importConfig(kind,file){try{const email=kind==='email',data=await readJsonFile(file);if(email&&(!data||Array.isArray(data)||typeof data!=='object'))throw new Error(t('La configuration email doit être un objet JSON.'));if(!email&&!Array.isArray(data))throw new Error(t('La configuration jobs doit être un tableau JSON.'));const result=await apiFetch(email?'save_config':'save_jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});if(result.status!=='ok')throw new Error(result.error||t(email?'Import email refusé':'Import jobs refusé'));await load();setStatus(t(email?'Configuration email importée et prise en compte.':'Configuration jobs importée, cron régénéré.'),'success','management-status');}catch(error){setStatus(error.message,'error','management-status');}}

document.querySelectorAll('.nav a').forEach(link=>link.addEventListener('click',event=>{event.preventDefault();setView(link.dataset.view);}));
window.addEventListener('hashchange',()=>setView(location.hash.slice(1)));
document.getElementById('language-toggle').addEventListener('click',setLanguage);
document.getElementById('theme-toggle').addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark'));
document.getElementById('add-job-btn').addEventListener('click',()=>openJob());
document.getElementById('refresh-jobs-btn').addEventListener('click',load);
document.getElementById('jobs-list').addEventListener('click',event=>{const toggle=event.target.closest('[data-toggle-job]'),log=event.target.closest('[data-log-job]'),edit=event.target.closest('[data-edit-job]');if(toggle)return toggleJob(toggle.dataset.toggleJob,toggle.checked);if(log)return showLog(log.dataset.logJob);if(edit)openJob(edit.dataset.editJob);});
document.getElementById('jobs-list').addEventListener('keydown',event=>{if((event.key==='Enter'||event.key===' ')&&event.target.dataset.editJob){event.preventDefault();openJob(event.target.dataset.editJob);}});
document.querySelectorAll('[data-close-drawer]').forEach(element=>element.addEventListener('click',()=>closeShell('job-drawer-shell')));
document.querySelectorAll('[data-close-log]').forEach(element=>element.addEventListener('click',()=>closeShell('log-drawer-shell')));
document.addEventListener('keydown',event=>{if(event.key==='Escape'){if(!document.getElementById('log-drawer-shell').hidden)closeShell('log-drawer-shell');else if(!document.getElementById('job-drawer-shell').hidden)closeShell('job-drawer-shell');}});
['source','target'].forEach(name=>document.getElementById(`job_${name}_type`).addEventListener('change',updateSideVisibility));
document.querySelectorAll('#job-drawer input,#job-drawer select,#job-drawer textarea').forEach(element=>element.addEventListener('input',()=>{element.classList.remove('invalid');document.getElementById('job-validation-message').hidden=true;}));
document.getElementById('save-job-btn').addEventListener('click',()=>saveCurrentJob(true));document.getElementById('delete-job-btn').addEventListener('click',deleteCurrentJob);document.getElementById('modal-mount-test-btn').addEventListener('click',()=>saveAndRun('mount_test'));document.getElementById('modal-dry-run-btn').addEventListener('click',()=>saveAndRun('dry'));document.getElementById('modal-run-btn').addEventListener('click',()=>saveAndRun('run'));
document.getElementById('save-config-btn').addEventListener('click',()=>saveConfig(true));document.getElementById('test-email-btn').addEventListener('click',testEmail);
document.getElementById('export-email-config-btn').addEventListener('click',()=>exportConfig('email'));document.getElementById('export-jobs-config-btn').addEventListener('click',()=>exportConfig('jobs'));
document.getElementById('import-email-config-btn').addEventListener('click',()=>document.getElementById('import-email-config-file').click());document.getElementById('import-jobs-config-btn').addEventListener('click',()=>document.getElementById('import-jobs-config-file').click());
document.getElementById('import-email-config-file').addEventListener('change',event=>{const file=event.target.files[0];event.target.value='';if(file)importConfig('email',file);});document.getElementById('import-jobs-config-file').addEventListener('change',event=>{const file=event.target.files[0];event.target.value='';if(file)importConfig('jobs',file);});

setTheme(document.documentElement.dataset.theme);setView(location.hash.slice(1));applyLanguage();load();
