(function () {
    const state = {
        funcionarios: window.ParteFuerza.funcionarios || [],
        novedades: window.ParteFuerza.novedades || [],
        categorias: window.ParteFuerza.categorias || {},
        editIndex: null,
    };

    const ids = (id) => document.getElementById(id);
    const money = (value) => parseInt(value, 10) || 0;

    const efectivaIds = {
        oficiales: 'efectiva_oficiales',
        nivel_ejecutivo: 'efectiva_nivel_ejecutivo',
        patrulleros: 'efectiva_patrulleros',
        patrulleros_policia: 'efectiva_patrulleros_policia',
        auxiliares: 'efectiva_auxiliares',
    };

    function dateTime(fecha, hora) {
        if (!fecha || !hora) return null;
        const value = new Date(`${fecha}T${hora}`);
        return Number.isNaN(value.getTime()) ? null : value;
    }

    function fechaHoraParte() {
        return dateTime(ids('fecha').value, ids('hora_parte').value || '12:00');
    }

    function formatDate(value) {
        if (!value) return '';
        const [y, m, d] = value.split('-');
        return `${d}/${m}/${y}`;
    }

    function vigenteParaParte(novedad) {
        const parte = fechaHoraParte();
        const inicio = dateTime(novedad.fecha_inicio, novedad.hora_inicio);
        const fin = dateTime(novedad.fecha_fin, novedad.hora_fin);
        return parte && inicio && fin && inicio <= parte && fin >= parte && (novedad.estado || 'activa') === 'activa';
    }

    function calcularDias() {
        const inicio = dateTime(ids('fecha_inicio').value, ids('hora_inicio').value);
        const fin = dateTime(ids('fecha_fin').value, ids('hora_fin').value);
        if (!inicio || !fin || fin <= inicio) {
            ids('dias_calculados').value = 0;
            ids('diasTexto').textContent = '0 días';
            return 0;
        }

        const diferencia = fin - inicio;
        const horasTotales = diferencia / (1000 * 60 * 60);
        const diasDecimal = horasTotales / 24;
        const dias = Math.floor(horasTotales / 24);
        const horas = Math.round(horasTotales % 24);
        const texto = `${dias} ${dias === 1 ? 'día' : 'días'} y ${horas} ${horas === 1 ? 'hora' : 'horas'} (${diasDecimal.toFixed(2)} días)`;
        ids('dias_calculados').value = diasDecimal.toFixed(2);
        ids('diasTexto').textContent = texto;
        return diasDecimal;
    }

    function efectivaPorCategoria() {
        return Object.fromEntries(Object.entries(efectivaIds).map(([key, id]) => [key, money(ids(id).value)]));
    }

    function novedadesPorCategoria() {
        const conteo = Object.fromEntries(Object.keys(state.categorias).map((key) => [key, 0]));
        state.novedades.forEach((novedad) => {
            if (vigenteParaParte(novedad)) {
                conteo[novedad.categoria] = (conteo[novedad.categoria] || 0) + 1;
            }
        });
        return conteo;
    }

    function calcularFuerzaDisponible() {
        const efectiva = efectivaPorCategoria();
        const novedades = novedadesPorCategoria();
        let totalEfectiva = 0;
        let totalNovedades = 0;
        let totalDisponible = 0;

        Object.keys(state.categorias).forEach((categoria) => {
            const ef = efectiva[categoria] || 0;
            const nov = novedades[categoria] || 0;
            const disp = Math.max(0, ef - nov);
            totalEfectiva += ef;
            totalNovedades += nov;
            totalDisponible += disp;
            ids(`ef_${categoria}`).textContent = ef;
            ids(`nov_${categoria}`).textContent = nov;
            ids(`disp_${categoria}`).textContent = disp;
        });

        ids('total_efectiva').textContent = totalEfectiva;
        ids('total_efectiva_2').textContent = totalEfectiva;
        ids('total_novedades').textContent = totalNovedades;
        ids('totalNovedadesTabla').textContent = totalNovedades;
        ids('total_disponible').textContent = totalDisponible;
        ids('res_efectiva').textContent = totalEfectiva;
        ids('res_novedades').textContent = totalNovedades;
        ids('res_disponible').textContent = totalDisponible;
        ids('porcentaje_disponible').textContent = totalEfectiva ? `${((totalDisponible / totalEfectiva) * 100).toFixed(1)}%` : '0%';
    }

    function renderFuncionarios() {
        const unidadId = Number(ids('unidad_id').value);
        const select = ids('funcionario_id');
        const current = select.value;
        select.innerHTML = '<option value="">Seleccione...</option>';
        state.funcionarios
            .filter((f) => Number(f.unidad_id) === unidadId)
            .forEach((f) => {
                const option = document.createElement('option');
                option.value = f.id;
                option.dataset.categoria = f.categoria;
                option.dataset.grado = f.grado;
                option.textContent = `${f.grado} ${f.nombres} ${f.apellidos} - ${f.categoria_nombre}`;
                select.appendChild(option);
            });
        select.value = current;
    }

    function renderNovedades() {
        const tbody = ids('novedadesBody');
        tbody.innerHTML = '';
        state.novedades.forEach((novedad, index) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${novedad.tipo_novedad}</td>
                <td><strong>${novedad.grado}</strong><br>${novedad.funcionario}</td>
                <td>${formatDate(novedad.fecha_inicio)}<br>${novedad.hora_inicio}</td>
                <td>${formatDate(novedad.fecha_fin)}<br>${novedad.hora_fin}</td>
                <td>${Number(novedad.dias_calculados).toFixed(2)}</td>
                <td class="actions-inline">
                    <button type="button" class="link-btn" data-edit="${index}">Editar</button>
                    <button type="button" class="delete-btn" data-delete="${index}">Eliminar</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
        calcularFuerzaDisponible();
    }

    function validarNovedad(novedad, ignoreIndex = null) {
        if (!novedad.tipo_novedad) return 'Debe seleccionar el tipo de novedad.';
        if (!novedad.funcionario_id) return 'Debe seleccionar el funcionario.';
        if (!novedad.fecha_inicio || !novedad.hora_inicio) return 'Debe ingresar la fecha y hora de inicio.';
        if (!novedad.fecha_fin || !novedad.hora_fin) return 'Debe ingresar la fecha y hora de finalización.';

        const inicio = dateTime(novedad.fecha_inicio, novedad.hora_inicio);
        const fin = dateTime(novedad.fecha_fin, novedad.hora_fin);
        if (!inicio || !fin || fin <= inicio) return 'La fecha y hora final debe ser posterior a la inicial.';

        const solapada = state.novedades.some((actual, index) => {
            if (index === ignoreIndex || Number(actual.funcionario_id) !== Number(novedad.funcionario_id)) return false;
            const a = dateTime(actual.fecha_inicio, actual.hora_inicio);
            const b = dateTime(actual.fecha_fin, actual.hora_fin);
            return inicio < b && fin > a;
        });
        if (solapada) return 'Ya existe una novedad simultánea para este funcionario.';

        if (vigenteParaParte(novedad)) {
            const efectiva = efectivaPorCategoria();
            const copia = state.novedades.slice();
            if (ignoreIndex === null) copia.push(novedad);
            else copia[ignoreIndex] = novedad;
            const ocupacion = Object.fromEntries(Object.keys(state.categorias).map((key) => [key, 0]));
            copia.forEach((item) => {
                if (vigenteParaParte(item)) ocupacion[item.categoria] = (ocupacion[item.categoria] || 0) + 1;
            });
            if (ocupacion[novedad.categoria] > efectiva[novedad.categoria]) {
                return `No es posible registrar esta novedad. La unidad solamente cuenta con ${efectiva[novedad.categoria]} funcionarios de ${state.categorias[novedad.categoria]} y ya existen ${efectiva[novedad.categoria]} funcionarios registrados en novedad.`;
            }
        }

        return null;
    }

    function novedadDesdeFormulario() {
        const funcionario = state.funcionarios.find((f) => Number(f.id) === Number(ids('funcionario_id').value));
        return {
            tipo_novedad: ids('tipo_novedad').value,
            funcionario_id: ids('funcionario_id').value,
            funcionario: funcionario ? `${funcionario.nombres} ${funcionario.apellidos}` : '',
            grado: funcionario ? funcionario.grado : '',
            categoria: funcionario ? funcionario.categoria : '',
            categoria_nombre: funcionario ? funcionario.categoria_nombre : '',
            fecha_inicio: ids('fecha_inicio').value,
            hora_inicio: ids('hora_inicio').value,
            fecha_fin: ids('fecha_fin').value,
            hora_fin: ids('hora_fin').value,
            dias_calculados: calcularDias(),
            observaciones: '',
            estado: 'activa',
        };
    }

    function limpiarNovedad() {
        state.editIndex = null;
        ids('tipo_novedad').value = '';
        ids('funcionario_id').value = '';
        calcularDias();
        ids('guardarNovedad').textContent = 'Guardar Novedad';
    }

    function guardarNovedad() {
        const novedad = novedadDesdeFormulario();
        const error = validarNovedad(novedad, state.editIndex);
        if (error) {
            alert(error);
            return;
        }

        if (state.editIndex === null) state.novedades.push(novedad);
        else state.novedades[state.editIndex] = novedad;
        limpiarNovedad();
        renderNovedades();
    }

    function payload() {
        return {
            unidad_id: ids('unidad_id').value,
            fecha: ids('fecha').value,
            hora_parte: ids('hora_parte').value,
            turno: ids('turno').value,
            comandante: ids('comandante').value,
            fuerza_efectiva_oficiales: ids('efectiva_oficiales').value,
            fuerza_efectiva_nivel_ejecutivo: ids('efectiva_nivel_ejecutivo').value,
            fuerza_efectiva_patrulleros: ids('efectiva_patrulleros').value,
            fuerza_efectiva_patrulleros_policia: ids('efectiva_patrulleros_policia').value,
            fuerza_efectiva_auxiliares: ids('efectiva_auxiliares').value,
            observaciones: ids('observaciones').value,
            novedades: state.novedades,
        };
    }

    async function guardarParte(event) {
        event.preventDefault();
        const form = ids('parteForm');
        const method = form.dataset.mode === 'edit' ? 'PUT' : 'POST';
        const response = await fetch(form.dataset.action, {
            method,
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
            },
            body: JSON.stringify(payload()),
        });
        const data = await response.json();
        if (!response.ok) {
            const messages = data.errors ? Object.values(data.errors).flat().join('\n') : (data.message || 'No fue posible guardar.');
            alert(messages);
            return;
        }
        alert(data.message);
        window.location.href = data.redirect;
    }

    document.querySelectorAll('.efectiva').forEach((input) => input.addEventListener('input', calcularFuerzaDisponible));
    ['fecha_inicio', 'hora_inicio', 'fecha_fin', 'hora_fin'].forEach((id) => ids(id).addEventListener('input', calcularDias));
    ids('fecha').addEventListener('input', () => {
        ids('fecha_top').value = ids('fecha').value;
        calcularFuerzaDisponible();
    });
    ids('hora_parte').addEventListener('input', calcularFuerzaDisponible);
    ids('fecha_top').addEventListener('input', () => {
        ids('fecha').value = ids('fecha_top').value;
        calcularFuerzaDisponible();
    });
    ids('unidad_id').addEventListener('change', () => {
        renderFuncionarios();
        state.novedades = [];
        renderNovedades();
    });
    ids('toggleNovedad').addEventListener('click', () => ids('novedadForm').classList.toggle('open'));
    ids('guardarNovedad').addEventListener('click', guardarNovedad);
    ids('parteForm').addEventListener('submit', guardarParte);
    ids('imprimirParte').addEventListener('click', () => {
        const url = ids('parteForm').dataset.print;
        if (url) window.open(url, '_blank');
        else alert('Guarde el parte antes de imprimir.');
    });
    ids('novedadesBody').addEventListener('click', (event) => {
        const edit = event.target.dataset.edit;
        const del = event.target.dataset.delete;
        if (edit !== undefined) {
            const novedad = state.novedades[Number(edit)];
            state.editIndex = Number(edit);
            ids('tipo_novedad').value = novedad.tipo_novedad;
            ids('funcionario_id').value = novedad.funcionario_id;
            ids('fecha_inicio').value = novedad.fecha_inicio;
            ids('hora_inicio').value = novedad.hora_inicio;
            ids('fecha_fin').value = novedad.fecha_fin;
            ids('hora_fin').value = novedad.hora_fin;
            ids('guardarNovedad').textContent = 'Actualizar Novedad';
            ids('novedadForm').classList.add('open');
            calcularDias();
        }
        if (del !== undefined && confirm('¿Eliminar esta novedad?')) {
            state.novedades.splice(Number(del), 1);
            renderNovedades();
        }
    });

    ids('fecha_top').value = ids('fecha').value;
    renderFuncionarios();
    calcularDias();
    renderNovedades();
})();
