'use strict';

// Confirmação para formulários com data-confirm
document.querySelectorAll('form[data-confirm]').forEach(form => {
  form.addEventListener('submit', event => {
    if (!window.confirm(form.dataset.confirm)) {
      event.preventDefault();
      return;
    }
  });
});

// Prevenção contra duplo clique e feedback de envio em formulários
document.querySelectorAll('form').forEach(form => {
  form.addEventListener('submit', event => {
    if (event.defaultPrevented) return;

    if (form.dataset.submitting === 'true') {
      event.preventDefault();
      return;
    }

    form.dataset.submitting = 'true';
    const submitBtn = form.querySelector('button[type="submit"], input[type="submit"], button:not([type])');
    if (submitBtn) {
      submitBtn.style.pointerEvents = 'none';
      submitBtn.style.opacity = '0.75';
      submitBtn.setAttribute('aria-busy', 'true');
    }

    // Timeout de segurança para reabilitar após 8s se a resposta demorar ou falhar
    setTimeout(() => {
      form.dataset.submitting = 'false';
      if (submitBtn) {
        submitBtn.style.pointerEvents = '';
        submitBtn.style.opacity = '';
        submitBtn.removeAttribute('aria-busy');
      }
    }, 8000);
  });
});

