(() => {
    const form = document.getElementById('reagendamento');
    if (!form) return;
    const status = document.getElementById('previa-status');
    const preview = document.getElementById('previa-titulos');
    const confirm = document.getElementById('confirmar-previa');
    const signature = form.elements.assinatura;
    let timer, controller, revision = 0;

    function schedule(event) {
        const field = event.target;
        if (!['nova_data', 'dia', 'proporcional', 'futuros'].includes(field.name)) return;
        if (field.name === 'nova_data' && field.value) form.elements.dia.value = '';
        if (field.name === 'dia' && field.value) form.elements.nova_data.value = '';
        clearTimeout(timer);
        controller?.abort();
        const current = ++revision;
        confirm.disabled = true;
        signature.value = '';
        preview.replaceChildren();
        status.textContent = 'Atualizando prévia…';
        timer = setTimeout(async () => {
            controller = new AbortController();
            // A prévia não envia os campos de senha ou motivo.
            const data = new URLSearchParams();
            for (const name of ['csrf_token', 'titulo_id', 'nova_data', 'dia', 'proporcional', 'futuros']) {
                for (const value of new FormData(form).getAll(name)) data.append(name, value);
            }
            data.set('acao', 'prever');
            try {
                const response = await fetch(form.action, {method: 'POST', body: data,
                    headers: {'X-Receivable-Preview': '1'}, signal: controller.signal});
                if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) {
                    throw new Error('Não foi possível atualizar. Recarregue a página ou use Calcular prévia.');
                }
                const result = await response.json();
                if (current !== revision) return;
                preview.innerHTML = result.html;
                signature.value = result.assinatura;
                confirm.disabled = Boolean(result.erro) || !result.assinatura;
                status.textContent = result.erro || 'Prévia atualizada. Confira os valores antes de confirmar.';
            } catch (error) {
                if (current === revision && error.name !== 'AbortError') status.textContent = error.message;
            }
        }, 300);
    }
    form.addEventListener('input', schedule);
    form.addEventListener('change', schedule);
})();
