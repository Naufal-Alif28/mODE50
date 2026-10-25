// Script for triggering an alert
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

document.getElementById("auth-form").addEventListener("submit", async (event) => {
    event.preventDefault();

    const form = event.currentTarget;

    try {
    const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form)
    });
    const data = await response.json();

    if (response.ok && data.success) {
        window.location.href = "/";
    } else {
        appendAlert(data.err_message, 'warning');
    }
    } catch (error) {
    console.error("request failed:", error);
    alert("Unable to log in. Please try again.");
    }
});