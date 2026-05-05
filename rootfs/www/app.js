const jobsTableBody = document.querySelector('#jobs-table tbody');
const addJobBtn = document.getElementById('add-job');
const saveJobsBtn = document.getElementById('save-jobs');

function createRow(job, index) {
    const tr = document.createElement('tr');

    const nameTd = document.createElement('td');
    const srcTd = document.createElement('td');
    const dstTd = document.createElement('td');
    const cronTd = document.createElement('td');
    const actionsTd = document.createElement('td');

    const nameInput = document.createElement('input');
    nameInput.value = job.name || '';
    const srcInput = document.createElement('input');
    srcInput.value = job.source || '';
    const dstInput = document.createElement('input');
    dstInput.value = job.target || '';
    const cronInput = document.createElement('input');
    cronInput.value = job.cron || '';

    nameTd.appendChild(nameInput);
    srcTd.appendChild(srcInput);
    dstTd.appendChild(dstInput);
    cronTd.appendChild(cronInput);

    const dryBtn = document.createElement('button');
    dryBtn.textContent = 'Dry-run';
    dryBtn.onclick = () => runJob(index, true);

    const runBtn = document.createElement('button');
    runBtn.textContent = 'Run';
    runBtn.onclick = () => runJob(index, false);

    const delBtn = document.createElement('button');
    delBtn.textContent = 'Supprimer';
    delBtn.onclick = () => {
        tr.remove();
        renumberRows();
    };

    actionsTd.appendChild(dryBtn);
    actionsTd.appendChild(runBtn);
    actionsTd.appendChild(delBtn);

    tr.appendChild(nameTd);
    tr.appendChild(srcTd);
    tr.appendChild(dstTd);
    tr.appendChild(cronTd);
    tr.appendChild(actionsTd);

    tr.dataset.index = index;

    return tr;
}

function renumberRows() {
    const rows = jobsTableBody.querySelectorAll('tr');
    rows.forEach((row, idx) => {
        row.dataset.index = idx;
    });
}

async function loadJobs() {
    const res = await fetch('cgi-bin/api.sh?action=list');
    const data = await res.json();
    jobsTableBody.innerHTML = '';
    data.forEach((job, index) => {
        jobsTableBody.appendChild(createRow(job, index));
    });
}

function collectJobs() {
    const rows = jobsTableBody.querySelectorAll('tr');
    const jobs = [];
    rows.forEach(row => {
        const inputs = row.querySelectorAll('input');
        const [name, source, target, cron] = Array.from(inputs).map(i => i.value.trim());
        if (name && source && target && cron) {
            jobs.push({ name, source, target, cron });
        }
    });
    return jobs;
}

// Remplacez la fonction saveJobs existante par celle-ci
async function saveJobs() {
    const jobs = collectJobs();
    // On ajoute un \n à la fin de la chaîne pour que le fichier se termine proprement
    const body = jobs.map(j => `${j.name}|${j.source}|${j.target}|${j.cron}`).join('\n') + '\n';

    await fetch('cgi-bin/api.sh?action=save', {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain' },
        body
    });
    alert('Jobs enregistrés et planification mise à jour');
    await loadJobs();
}

async function runJob(index, dry) {
    const action = dry ? 'dry' : 'run';
    await fetch(`cgi-bin/api.sh?action=${action}&index=${index}`, { method: 'POST' });
    alert((dry ? 'Dry-run' : 'Rsync') + ' lancé pour le job ' + index + '. Regarde les logs de l’addon.');
}

addJobBtn.onclick = () => {
    const job = { name: '', source: '', target: '', cron: '' };
    const index = jobsTableBody.querySelectorAll('tr').length;
    jobsTableBody.appendChild(createRow(job, index));
};

saveJobsBtn.onclick = saveJobs;

// Email

async function loadEmail() {
    const res = await fetch('cgi-bin/api.sh?action=get_email');
    const data = await res.json();

    document.getElementById('email-to').value = data.to || '';
    document.getElementById('email-host').value = data.smtp_host || '';
    document.getElementById('email-port').value = data.smtp_port || '';
    document.getElementById('email-user').value = data.smtp_user || '';
    document.getElementById('email-pass').value = data.smtp_pass || '';
}

async function saveEmail() {
    const body =
    `to=${document.getElementById('email-to').value}\n` +
    `smtp_host=${document.getElementById('email-host').value}\n` +
    `smtp_port=${document.getElementById('email-port').value}\n` +
    `smtp_user=${document.getElementById('email-user').value}\n` +
    `smtp_pass=${document.getElementById('email-pass').value}\n`;

    await fetch('cgi-bin/api.sh?action=save_email', {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain' },
        body
    });

    alert('Email enregistré');
}

async function testEmail() {
    const res = await fetch('cgi-bin/api.sh?action=test_email', { method: 'POST' });
    const data = await res.json();
    if (data.status === 'sent') {
        alert('Email de test envoyé (regarde les logs si tu ne le reçois pas).');
    } else {
        alert('Erreur envoi email : ' + (data.error || 'inconnue'));
    }
}

document.getElementById('save-email').onclick = saveEmail;
document.getElementById('test-email').onclick = testEmail;

loadJobs();
loadEmail();
