 // MAIN DASHBOARD SCRIPT

 // Function
const element = id => document.getElementById(id);
let rows = [];
let dataframe = null;


// Alert trigger
const alertPlaceholder = document.getElementById('liveAlertPlaceholder');
const appendAlert = (message, type) => {
    const wrapper = document.createElement('div');
    wrapper.innerHTML = [
    `<div class="alert alert-${type} alert-dismissible fade show" id="alert" role="alert">`,
    `   <div>${message}</div>`,
    '   <button type="button" class="btn-close" data-coreui-dismiss="alert" aria-label="Close"></button>',
    '</div>'
    ].join('');

    alertPlaceholder.append(wrapper);

    const alertElement = wrapper.firstElementChild;
    setTimeout(() => {
    coreui.Alert.getOrCreateInstance(alertElement).close();
    }, 3000);
}         

// New csv input
element('btnOpen').onclick = () => element('inputNew').click();
element('inputNew').onchange = async e => {
    const file = e.target.files[0];
    if (!file) return; // end if file is empty
    dataframe = null;
    const text = await file.text();
    rows = text.trim().split(/\r?\n/).map(l => l.split(','));
    element('projectName').value = file.name.replace(/\.[^.]+$/, '');

    // Pack the form data into a FormData object
    const formData = new FormData();
    formData.append('newFile', file);

    try {
    // Send the file via background HTTP POST request
    const response = await fetch('/upload', {
        method: 'POST',
        body: formData // Fetch automatically sets the correct Multipart headers
    });

    const data = await response.json();

    if (response.ok && data.success && Array.isArray(data.dataframe)) {
        dataframe = data.dataframe;
        renderCsv(rows);
    } else {
        dataframe = null;
        appendAlert(data.err_message || 'The uploaded file did not contain a dataset.', 'warning');
    }
    } catch (error) {
    dataframe = null;
    console.error('Error uploading file:', error);
    appendAlert('Unable to upload the selected file.', 'danger');
    }
}

function renderCsv(data) {
    let head;
    let body;
    if (data.length && Array.isArray(data[0])) {
        [head, ...body] = data;
    } else if (data.length && data[0] && typeof data[0] === 'object') {
        head = Object.keys(data[0]);
        body = data.map(row => head.map(column => row[column]));
    } else {
        throw new Error('CSV data must contain rows or object records.');
    }

    const table = element('csvTable');
    table.querySelector('thead').innerHTML =
    '<tr>' + head.map(h => `<th>${h}</th>`).join('') + '</tr>';
    table.querySelector('tbody').innerHTML =
    body.map(r => '<tr>' + r.map(c => `<td>${c}</td>`).join('') + '</tr>').join('');
    element('csvInfo').textContent = body.length + ' rows';
}

// Fitting
let layout = {
    plot_bgcolor: '#212631',
    paper_bgcolor: '#282d37',
    font: { color: '#ffffff'},
    autosize: true,
    xaxis: { title: 'Time', gridcolor: '#282c37', zerolinecolor: '#ffffff' },
    yaxis: { title: 'Concentration', gridcolor: '#282c37', zerolinecolor: '#ffffff'  },
    legend: { orientation: 'h' },
    margin: { t: 24, r: 24, b: 56, l: 64 }
}

function updateCoeff(data) {
    const coefficientElements = {
        mu: data.umax,
        Ks: data.Ks,
        Yxs: data.Ysx,
        Ypx: data.Ypx
    }
    for (const [id, value] of Object.entries(coefficientElements)) {
        element(id).textContent = value;
    }

    const rSquaredElements = {
        R2X: data.r2.X,
        R2S: data.r2.S,
        R2P: data.r2.P
    }
    for (const [id, value] of Object.entries(rSquaredElements)) {
        element(id).textContent = value;
    }
}

element('btnFit').onclick = async () => {
    if (!dataframe) {
    appendAlert('Upload a valid dataset before fitting.', 'warning');
    return;
    }

    const button = element('btnFit');
    button.disabled = true;
    element('fitStatus').textContent = 'Sending data...';

    try {
    const response = await fetch('/fit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataframe })
    });
    const result = await response.json();

    if (!response.ok || !result.success) {
        throw new Error(result.err_message || 'Fit request failed.');
    }

    // plot
    await Plotly.newPlot('plotArea', result.plotter, layout, { responsive: true });

    // update coefficients
    updateCoeff(result.coeff)

    element('plot-placeholder-text').style.display = 'none';

    element('fitStatus').textContent = 'Fit complete';
    
    } catch (error) {
    element('fitStatus').textContent = 'Fit request failed';
    appendAlert(error.message, 'danger');
    } finally {
    button.disabled = false;
    }
}

// Save project
function sanitizeProjectname(projectname, replacement = '_') {
  if (!projectname || typeof projectname !== 'string') return '';

  // 1. Remove control characters (0x00–0x1f and 0x80–0x9f)
  // 2. Remove illegal OS characters: / ? < > \ : * | "
  let sanitized = projectname
    .replace(/[\x00-\x1f\x80-\x9f]/g, '')
    .replace(/[\/\\?%*:|"<>]/g, replacement);

  // 3. Remove Unix/Linux relative directory path rules (. and ..)
  if (sanitized === '.' || sanitized === '..') {
    return '';
  }

  // 4. Protect against Windows reserved filenames (e.g., CON, PRN, NUL)
  const windowsReservedRegex = /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$/i;
  if (windowsReservedRegex.test(sanitized)) {
    sanitized = replacement + sanitized;
  }

  // 5. Truncate strictly to 255 bytes (NOT characters) for filesystem safety
  const uint8Array = new TextEncoder().encode(sanitized);
  if (uint8Array.length > 255) {
    sanitized = new TextDecoder('utf-8').decode(uint8Array.slice(0, 255));
  }

  // 6. Strip trailing periods and spaces (problematic for Windows)
  return sanitized.replace(/[. ]+$/, '');
}

element('btnSave').onclick = async () => { 
    let projectName = element('projectName').value; 
    if (!projectName) {
    appendAlert('Provide a project name', 'warning');
    return;
    }
    //sanitize the projectname
    projectName = sanitizeProjectname(projectName);
    // send to /save route
    try {
        const response = await fetch('/save', {
            method: 'POST',
            headers: { 'Content-Type': 'text/plain' },
            body: projectName
        }) 
        const result = await response.json();
        if (result.success) {
            appendAlert(result.message, 'success');
    } 
    } catch (error) {
        appendAlert(`Unable to save ${error.message}`, 'danger');
    }
}


// Open project dropdown
const dropdownEl  = document.getElementById('openProjectDropdown');
const projectList = document.getElementById('projectList');

// 1. Get the saved projects
async function fetchProjects() {
    const res = await fetch('/open', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request: 'fetchProjects' })
    });
    if (!res.ok) throw new Error('Failed to fetch projects');
    return await res.json();
}

// 2. Load one project
const coeff_default = {
    umax: "\u2013",
    Ks: "\u2013",
    Ysx: "\u2013",
    Ypx: "\u2013",
    r2: {
        X: "\u2013",
        S: "\u2013",
        P: "\u2013"
    }
};


async function loadProject(name) {
    const res = await fetch('/open', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request: 'loadProject', projectName: name })         
    });
    if (!res.ok) throw new Error('Failed to load project');
    const project = await res.json();

    if (project.df != null) { 
        renderCsv(project.df); 
    } else {
        const table = element('csvTable');
        table.querySelector('thead').innerHTML =
            '<tr><th>time</th><th>biomass</th><th>substrate</th><th>product</th></tr>';
        table.querySelector('tbody').innerHTML =
            '<tr><td colspan="4" class="text-center text-body-secondary py-4">No data loaded</td></tr>';
        element('csvInfo').textContent = '0 rows';
        dataframe = null;
        rows = [];
    }

    if (project.plotter != null) {
        await Plotly.newPlot('plotArea', project.plotter, layout, { responsive: true });
        element('plot-placeholder-text').style.display = 'none';
        element('fitStatus').textContent = 'Fit complete';
    } else {
        Plotly.purge('plotArea');
        element('plot-placeholder-text').style.display = '';
        element('fitStatus').textContent = 'No fit yet';
    }

    if (project.coeff != null) { 
        updateCoeff(project.coeff); 
    } else {
        updateCoeff(coeff_default);
    }

    element('projectName').value = project.name;

    return project;
}

// 3. Render the list
function renderProjects(projects) {
    projectList.replaceChildren();

    if (!projects.length) {
    projectList.innerHTML =
        '<li><span class="dropdown-item-text text-body-secondary">No saved projects</span></li>'
    return;
    }

    projects.forEach(p => {
    const li = document.createElement('li');
    const a  = document.createElement('a');
    a.className = 'dropdown-item d-flex justify-content-between align-items-center gap-3';
    a.href = '#';
    a.dataset.projectName = p.name;

    const name = document.createElement('span');
    name.textContent = p.name;            // textContent avoids XSS

    a.append(name);
    li.append(a);
    projectList.append(li);
    });
}

// 4. Refresh the list each time the dropdown opens
dropdownEl.addEventListener('show.coreui.dropdown', async () => {
    try {
    renderProjects(await fetchProjects());
    } catch (err) {
    projectList.innerHTML =
        '<li><span class="dropdown-item-text text-danger">Could not load list</span></li>';
    }
})

// 5. Handle clicks (event delegation, so it works for dynamic items)
projectList.addEventListener('click', async (e) => {
    const item = e.target.closest('[data-project-name]');
    if (!item) return;
    e.preventDefault();

    try {
    const project = await loadProject(item.dataset.projectName);
    // Reuses the alert placeholder from before
    appendAlert(`Project "${project.name}" loaded.`, 'success');
    } catch (err) {
    console.error('Could not load project:', err);
    appendAlert('Could not load the project.', 'danger');
    }
})
