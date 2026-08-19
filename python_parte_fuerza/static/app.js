(function () {
    const state = {
        funcionarios: window.ParteFuerza.funcionarios || [],
        categorias: window.ParteFuerza.categorias || {},
        novedades: [],
        editIndex: null,
        cargaVigentes: 0,
    };

    const $ = (id) => document.getElementById(id);

    const PSI_TIPOS = ["Permiso", "Franquicia"];
    const psiRequerido = (tipo) => PSI_TIPOS.includes(tipo);
    const otraNovedadRequerida = (tipo) => tipo === "Otra novedad";
    const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    }[char]));

    const efectivaIds = {
        oficiales: "efectiva_oficiales",
        nivel_ejecutivo: "efectiva_nivel_ejecutivo",
        patrulleros: "efectiva_patrulleros",
        patrulleros_policia: "efectiva_patrulleros_policia",
        auxiliares: "efectiva_auxiliares",
    };

    function intValue(id) {
        return parseInt($(id).value, 10) || 0;
    }

    function dateTime(fecha, hora) {
        if (!fecha || !hora) return null;
        const value = new Date(`${fecha}T${hora}`);
        return Number.isNaN(value.getTime()) ? null : value;
    }

    function formatDate(value) {
        if (!value) return "";
        const [y, m, d] = value.split("-");
        return `${d}/${m}/${y}`;
    }

    function fechaHoraActual() {
        const now = new Date();
        const pad = (value) => String(value).padStart(2, "0");
        return {
            fecha: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`,
            hora: `${pad(now.getHours())}:${pad(now.getMinutes())}`,
        };
    }

    function actualizarFechaHoraParte() {
        const actual = fechaHoraActual();
        $("fecha").value = actual.fecha;
        $("hora_parte").value = actual.hora;
        return actual;
    }

    function efectivaPorCategoria() {
        const efectiva = {};
        Object.entries(efectivaIds).forEach(([categoria, id]) => {
            efectiva[categoria] = intValue(id);
        });
        return efectiva;
    }

    function novedadesPorCategoria() {
        const conteo = {};
        Object.keys(state.categorias).forEach((categoria) => conteo[categoria] = 0);
        state.novedades.forEach((novedad) => {
            conteo[novedad.categoria] = (conteo[novedad.categoria] || 0) + 1;
        });
        return conteo;
    }

    function calcularDias() {
        const inicio = dateTime($("fecha_inicio").value, $("hora_inicio").value);
        const fin = dateTime($("fecha_fin").value, $("hora_fin").value);
        if (!inicio || !fin || fin <= inicio) {
            $("diasTexto").textContent = "0 días";
            return 0;
        }

        const totalHoras = (fin - inicio) / 36e5;
        const diasDecimal = totalHoras / 24;
        const dias = Math.floor(totalHoras / 24);
        const horas = Math.round(totalHoras % 24);
        $("diasTexto").textContent = `${dias} ${dias === 1 ? "día" : "días"} y ${horas} ${horas === 1 ? "hora" : "horas"} (${diasDecimal.toFixed(2)} días)`;
        return Number(diasDecimal.toFixed(2));
    }

    function novedadesPorCategoria() {
        const conteo = {};
        Object.keys(state.categorias).forEach((categoria) => conteo[categoria] = 0);
        state.novedades.forEach((novedad) => {
            conteo[novedad.categoria] = (conteo[novedad.categoria] || 0) + 1;
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

            $(`ef_${categoria}`).textContent = ef;
            $(`nov_${categoria}`).textContent = nov;
            $(`disp_${categoria}`).textContent = disp;
        });

        $("total_efectiva").textContent = totalEfectiva;
        $("total_efectiva_2").textContent = totalEfectiva;
        $("total_novedades").textContent = totalNovedades;
        $("totalNovedadesTabla").textContent = totalNovedades;
        $("total_disponible").textContent = totalDisponible;
        $("res_efectiva").textContent = totalEfectiva;
        $("res_novedades").textContent = totalNovedades;
        $("res_disponible").textContent = totalDisponible;
        $("porcentaje_disponible").textContent = totalEfectiva ? `${((totalDisponible / totalEfectiva) * 100).toFixed(1)}%` : "0%";
    }

    function renderFuncionarios() {
        const unidadId = Number($("unidad_novedad_id").value || $("unidad_id").value);
        const select = $("funcionario_id");
        const selected = select.value;
        select.innerHTML = '<option value="">Seleccione...</option>';

        state.funcionarios
            .filter((funcionario) => Number(funcionario.unidad_id) === unidadId)
            .forEach((funcionario) => {
                const option = document.createElement("option");
                option.value = funcionario.id;
                option.textContent = `${funcionario.grado} ${funcionario.nombres} ${funcionario.apellidos}`;
                select.appendChild(option);
            });

        select.value = selected;
        renderCargoFuncionario();
    }

    function renderCargoFuncionario() {
        const box = $("cargoFuncionario");
        const text = $("cargoFuncionarioTexto");
        if (!box || !text) return;

        const funcionario = funcionarioActual();
        if (!funcionario) {
            box.style.display = "none";
            text.textContent = "";
            return;
        }

        text.textContent = funcionario.cargo || "Sin cargo registrado en la matriz";
        box.style.display = "grid";
    }

    function actualizarEfectivaPorUnidad() {
        const unidadId = Number($("unidad_id").value);
        const conteo = {};
        Object.keys(state.categorias).forEach((categoria) => conteo[categoria] = 0);

        if (unidadId) {
            state.funcionarios
                .filter((funcionario) => Number(funcionario.unidad_id) === unidadId)
                .forEach((funcionario) => {
                    conteo[funcionario.categoria] = (conteo[funcionario.categoria] || 0) + 1;
                });
        }

        Object.entries(efectivaIds).forEach(([categoria, id]) => {
            $(id).value = conteo[categoria] || 0;
        });

        calcularFuerzaDisponible();
    }

    function funcionarioActual() {
        return state.funcionarios.find((funcionario) => Number(funcionario.id) === Number($("funcionario_id").value));
    }

    function novedadFormulario() {
        const funcionario = funcionarioActual();
        return {
            unidad_id: $("unidad_novedad_id").value,
            unidad_nombre: funcionario ? funcionario.unidad_nombre : "",
            tipo_novedad: $("tipo_novedad").value,
            funcionario_id: $("funcionario_id").value,
            funcionario: funcionario ? `${funcionario.nombres} ${funcionario.apellidos}` : "",
            grado: funcionario ? funcionario.grado : "",
            categoria: funcionario ? funcionario.categoria : "",
            categoria_nombre: funcionario ? state.categorias[funcionario.categoria] : "",
            fecha_inicio: $("fecha_inicio").value,
            hora_inicio: $("hora_inicio").value,
            fecha_fin: $("fecha_fin").value,
            hora_fin: $("hora_fin").value,
            dias_calculados: calcularDias(),
            observaciones: otraNovedadRequerida($("tipo_novedad").value) ? $("otra_novedad_detalle").value.trim() : "",
            solicitud_psi: $("solicitud_psi").value,
        };
    }

    async function cargarNovedadesVigentes() {
        actualizarFechaHoraParte();
        const unidadId = $("unidad_id").value;
        const fecha = $("fecha").value;
        const hora = $("hora_parte").value || "07:00";
        state.cargaVigentes += 1;
        const token = state.cargaVigentes;

        state.novedades = state.novedades.filter((novedad) => !novedad.automatica);
        if (!unidadId || !fecha || !hora) {
            renderNovedades();
            return;
        }

        const params = new URLSearchParams({unidad_id: unidadId, fecha, hora});
        try {
            const response = await fetch(`/api/novedades-vigentes?${params.toString()}`, {headers: {"Accept": "application/json"}});
            const data = await response.json();
            if (token !== state.cargaVigentes) return;
            if (!response.ok) return;

            const manuales = new Set(
                state.novedades
                    .filter((novedad) => !novedad.automatica)
                    .map((novedad) => String(novedad.funcionario_id))
            );
            (data.novedades || []).forEach((novedad) => {
                if (!manuales.has(String(novedad.funcionario_id))) {
                    state.novedades.push(novedad);
                }
            });
        } catch (error) {
            console.warn("No fue posible cargar novedades vigentes", error);
        }
        renderNovedades();
    }

    function validarNovedad(novedad, ignoreIndex = null) {
        if (!$("unidad_novedad_id").value) return "Debe seleccionar la unidad de la novedad.";
        if (!novedad.tipo_novedad) return "Debe seleccionar el tipo de novedad.";
        if (psiRequerido(novedad.tipo_novedad) && !novedad.solicitud_psi) return "Debe indicar si la solicitud de permiso es por PSI (Sí o No).";
        if (otraNovedadRequerida(novedad.tipo_novedad) && !novedad.observaciones) return "Debe escribir qué novedad tiene el funcionario.";
        if (!novedad.funcionario_id) return "Debe seleccionar el funcionario.";
        if (!novedad.fecha_inicio || !novedad.hora_inicio) return "Debe ingresar fecha y hora de inicio.";
        if (!novedad.fecha_fin || !novedad.hora_fin) return "Debe ingresar fecha y hora de finalización.";

        const inicio = dateTime(novedad.fecha_inicio, novedad.hora_inicio);
        const fin = dateTime(novedad.fecha_fin, novedad.hora_fin);
        if (!inicio || !fin || fin <= inicio) return "La fecha y hora final debe ser posterior a la inicial.";

        const solapada = state.novedades.some((actual, index) => {
            if (index === ignoreIndex || Number(actual.funcionario_id) !== Number(novedad.funcionario_id)) return false;
            const ini = dateTime(actual.fecha_inicio, actual.hora_inicio);
            const end = dateTime(actual.fecha_fin, actual.hora_fin);
            return inicio < end && fin > ini;
        });
        if (solapada) return "Ya existe una novedad simultánea para este funcionario.";

        const efectiva = efectivaPorCategoria();
        const copia = state.novedades.slice();
        if (ignoreIndex === null) copia.push(novedad);
        else copia[ignoreIndex] = novedad;

        const ocupacion = {};
        Object.keys(state.categorias).forEach((categoria) => ocupacion[categoria] = 0);
        copia.forEach((item) => {
            ocupacion[item.categoria] = (ocupacion[item.categoria] || 0) + 1;
        });

        if (ocupacion[novedad.categoria] > efectiva[novedad.categoria]) {
            return `No es posible registrar esta novedad. La unidad solamente cuenta con ${efectiva[novedad.categoria]} funcionarios de ${state.categorias[novedad.categoria]} y ya están registrados en novedad.`;
        }

        return null;
    }

    function limpiarFormularioNovedad() {
        state.editIndex = null;
        $("tipo_novedad").value = "";
        $("funcionario_id").value = "";
        $("solicitud_psi").value = "";
        $("otra_novedad_detalle").value = "";
        $("psiField").style.display = "none";
        $("otraNovedadField").style.display = "none";
        $("guardarNovedad").textContent = "Guardar Novedad";
        calcularDias();
    }

    function abrirFormularioNovedad() {
        $("novedadForm").classList.add("open");
        document.body.classList.add("novedad-modal-open");
    }

    function cerrarFormularioNovedad() {
        $("novedadForm").classList.remove("open");
        document.body.classList.remove("novedad-modal-open");
        limpiarFormularioNovedad();
    }

    function renderNovedades() {
        const body = $("novedadesBody");
        body.innerHTML = "";

        state.novedades.forEach((novedad, index) => {
            const tr = document.createElement("tr");
            const etiqueta = novedad.automatica ? '<br><span class="mini-badge">Vigente</span>' : "";
            const detalle = otraNovedadRequerida(novedad.tipo_novedad) && novedad.observaciones ? `<br><small>${escapeHtml(novedad.observaciones)}</small>` : "";
            const unidad = novedad.unidad_nombre ? `<br><small>${escapeHtml(novedad.unidad_nombre)}</small>` : "";
            tr.innerHTML = `
                <td><strong>${escapeHtml(novedad.tipo_novedad)}</strong>${detalle}${etiqueta}</td>
                <td><strong>${escapeHtml(novedad.grado)}</strong><br>${escapeHtml(novedad.funcionario)}${unidad}</td>
                <td>${escapeHtml(formatDate(novedad.fecha_inicio))}<br>${escapeHtml(novedad.hora_inicio)}</td>
                <td>${escapeHtml(formatDate(novedad.fecha_fin))}<br>${escapeHtml(novedad.hora_fin)}</td>
                <td>${Number(novedad.dias_calculados).toFixed(2)}</td>
                <td>${escapeHtml(novedad.solicitud_psi || "-")}</td>
                <td>
                    <div class="actions-inline">
                        <button type="button" class="edit-btn" data-edit="${index}">Editar</button>
                        <button type="button" class="delete-btn" data-delete="${index}">Eliminar</button>
                    </div>
                </td>
            `;
            body.appendChild(tr);
        });

        calcularFuerzaDisponible();
    }

    function guardarNovedad() {
        const novedad = novedadFormulario();
        const error = validarNovedad(novedad, state.editIndex);
        if (error) {
            alert(error);
            return;
        }

        if (state.editIndex === null) state.novedades.push(novedad);
        else state.novedades[state.editIndex] = novedad;

        cerrarFormularioNovedad();
        renderNovedades();
    }

    function payloadParte() {
        actualizarFechaHoraParte();
        return {
            unidad_id: $("unidad_id").value,
            fecha: $("fecha").value,
            hora_parte: $("hora_parte").value,
            turno: "",
            comandante: $("comandante").value,
            fuerza_efectiva_oficiales: intValue("efectiva_oficiales"),
            fuerza_efectiva_nivel_ejecutivo: intValue("efectiva_nivel_ejecutivo"),
            fuerza_efectiva_patrulleros: intValue("efectiva_patrulleros"),
            fuerza_efectiva_patrulleros_policia: intValue("efectiva_patrulleros_policia"),
            fuerza_efectiva_auxiliares: intValue("efectiva_auxiliares"),
            observaciones: $("observaciones").value,
            novedades: state.novedades,
        };
    }

    function mostrarParteGuardado(message) {
        const modal = document.createElement("div");
        modal.className = "save-modal";
        modal.innerHTML = `
            <div class="save-modal-card" role="dialog" aria-modal="true" aria-labelledby="saveModalTitle">
                <h2 id="saveModalTitle">Parte guardado correctamente</h2>
                <p>${message || "La información fue registrada en reportes."}</p>
                <div class="save-modal-actions">
                    <a class="btn outline" href="/historial">Ver reportes</a>
                    <a class="btn danger" href="/logout">Cerrar sesión</a>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        modal.querySelector("a").focus();
    }

    async function guardarParte(event) {
        if (event) event.preventDefault();
        if (!$("unidad_id").value) {
            alert("Debe seleccionar la unidad que reporta el parte.");
            return;
        }
        const response = await fetch("/api/partes", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payloadParte()),
        });
        const data = await response.json();
        if (!response.ok) {
            alert(data.error || "No fue posible guardar el parte.");
            return;
        }
        mostrarParteGuardado(data.message);
    }

    document.querySelectorAll(".efectiva").forEach((input) => input.addEventListener("input", calcularFuerzaDisponible));
    ["fecha_inicio", "hora_inicio", "fecha_fin", "hora_fin"].forEach((id) => $(id).addEventListener("input", calcularDias));
    $("unidad_id").addEventListener("change", () => {
        calcularFuerzaDisponible();
        cargarNovedadesVigentes();
    });
    $("unidad_novedad_id").addEventListener("change", () => {
        $("funcionario_id").value = "";
        renderFuncionarios();
    });
    $("funcionario_id").addEventListener("change", renderCargoFuncionario);
    $("toggleNovedad").addEventListener("click", () => {
        limpiarFormularioNovedad();
        abrirFormularioNovedad();
    });
    $("tipo_novedad").addEventListener("change", () => {
        const tipo = $("tipo_novedad").value;
        $("psiField").style.display = psiRequerido(tipo) ? "block" : "none";
        $("otraNovedadField").style.display = otraNovedadRequerida(tipo) ? "block" : "none";
        if (!otraNovedadRequerida(tipo)) $("otra_novedad_detalle").value = "";
    });
    $("guardarNovedad").addEventListener("click", guardarNovedad);
    $("cancelarNovedad").addEventListener("click", cerrarFormularioNovedad);
    $("guardarParteBtn").addEventListener("click", guardarParte);
    $("parteForm").addEventListener("submit", (event) => event.preventDefault());
    $("parteForm").addEventListener("keydown", (event) => {
        if (event.key === "Enter" && event.target.tagName !== "TEXTAREA") {
            event.preventDefault();
        }
    });

    $("novedadesBody").addEventListener("click", (event) => {
        const edit = event.target.dataset.edit;
        const del = event.target.dataset.delete;

        if (edit !== undefined) {
            const novedad = state.novedades[Number(edit)];
            state.editIndex = Number(edit);
            $("unidad_novedad_id").value = novedad.unidad_id || "";
            renderFuncionarios();
            $("tipo_novedad").value = novedad.tipo_novedad;
            $("funcionario_id").value = novedad.funcionario_id;
            renderCargoFuncionario();
            $("fecha_inicio").value = novedad.fecha_inicio;
            $("hora_inicio").value = novedad.hora_inicio;
            $("fecha_fin").value = novedad.fecha_fin;
            $("hora_fin").value = novedad.hora_fin;
            $("solicitud_psi").value = novedad.solicitud_psi || "";
            $("otra_novedad_detalle").value = novedad.observaciones || "";
            $("psiField").style.display = psiRequerido(novedad.tipo_novedad) ? "block" : "none";
            $("otraNovedadField").style.display = otraNovedadRequerida(novedad.tipo_novedad) ? "block" : "none";
            $("guardarNovedad").textContent = "Actualizar Novedad";
            abrirFormularioNovedad();
            calcularDias();
        }

        if (del !== undefined && confirm("¿Eliminar esta novedad?")) {
            state.novedades.splice(Number(del), 1);
            renderNovedades();
        }
    });

    actualizarFechaHoraParte();
    renderFuncionarios();
    calcularDias();
    renderNovedades();
    cargarNovedadesVigentes();
})();
