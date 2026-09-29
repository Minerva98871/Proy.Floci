const API_URL = 'http://localhost:5000';
let productosCache = [];

// MOSTRAR VISTA
function mostrarVista(vista) {
    document.querySelectorAll('.vista').forEach(v => v.classList.remove('activa'));
    document.getElementById(`vista-${vista}`).classList.add('activa');
    
    document.querySelectorAll('.nav-link').forEach(link => link.classList.remove('active'));
    event.target.closest('.nav-link')?.classList.add('active');
    
    if (vista === 'catalogo') {
        cargarCatalogo();
    }
}

// CARGAR CATEGORÍAS
async function cargarCategorias() {
    try {
        const res = await fetch(`${API_URL}/categorias`);
        const data = await res.json();
        
        const selectRegistro = document.getElementById('categoria');
        const selectFiltro = document.getElementById('filtro-categoria');
        
        data.data.forEach(cat => {
            const opt1 = document.createElement('option');
            opt1.value = cat.categoria_id;
            opt1.textContent = cat.nombre;
            selectRegistro.appendChild(opt1);
            
            const opt2 = document.createElement('option');
            opt2.value = cat.categoria_id;
            opt2.textContent = cat.nombre;
            selectFiltro.appendChild(opt2);
        });
    } catch (e) {
        console.error('Error cargando categorías:', e);
    }
}

// CARGAR CATÁLOGO
async function cargarCatalogo() {
    try {
        const res = await fetch(`${API_URL}/productos?t=${Date.now()}`);
        const data = await res.json();
        productosCache = data.data || [];
        
        actualizarGrid(productosCache);
        document.getElementById('total-productos').textContent = productosCache.length;
    } catch (e) {
        console.error('Error cargando catálogo:', e);
        document.getElementById('productos-grid').innerHTML = 
            '<p style="grid-column: 1/-1; text-align: center; color: #999;">Error al cargar productos</p>';
    }
}

// ACTUALIZAR GRID
function actualizarGrid(productos) {
    const grid = document.getElementById('productos-grid');
    grid.innerHTML = '';
    
    if (productos.length === 0) {
        grid.innerHTML = '<p style="grid-column: 1/-1; text-align: center; color: #999; padding: 2rem;">No hay productos disponibles</p>';
        return;
    }
    
    productos.forEach(prod => {
        const card = document.createElement('div');
        card.className = 'producto-card';
        card.onclick = () => verDetalle(prod.producto_id);
        
        // La miniatura la genera lambda/handler.py y la sirve el backend
        const imagen = prod.miniatura_disponible
            ? `<img src="${API_URL}${prod.miniatura_url}" alt="${prod.nombre}" loading="lazy">`
            : '<i class="fas fa-box"></i>';
        
        card.innerHTML = `
            <div class="producto-imagen">
                ${imagen}
            </div>
            <div class="producto-info">
                <h3>${prod.nombre}</h3>
                <div class="producto-precio">$${prod.precio.toFixed(2)}</div>
                <span class="producto-categoria">${prod.categoria}</span>
            </div>
        `;
        grid.appendChild(card);
    });
}

// FILTRAR PRODUCTOS
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('buscar')?.addEventListener('input', (e) => {
        const filtrados = productosCache.filter(p => 
            p.nombre.toLowerCase().includes(e.target.value.toLowerCase())
        );
        actualizarGrid(filtrados);
    });
    
    document.getElementById('filtro-categoria')?.addEventListener('change', (e) => {
        const filtrados = e.target.value 
            ? productosCache.filter(p => p.producto_id === parseInt(e.target.value) || p.categoria === e.target.value)
            : productosCache;
        actualizarGrid(filtrados);
    });
});

// VER DETALLE
async function verDetalle(id) {
    try {
        const res = await fetch(`${API_URL}/productos/${id}`);
        const data = await res.json();
        const prod = data.data;
        
        let atributosHTML = '';
        if (prod.atributos && Object.keys(prod.atributos).length > 0) {
            atributosHTML = '<div class="detalle-atributos"><h3><i class="fas fa-list"></i> Atributos</h3>';
            for (const [key, value] of Object.entries(prod.atributos)) {
                atributosHTML += `
                    <div class="atributo-item">
                        <span class="atributo-key">${key}</span>
                        <span class="atributo-value">${value}</span>
                    </div>
                `;
            }
            atributosHTML += '</div>';
        }
        
        const estadoColor = prod.estado === 'PUBLICADO' ? '#10b981' : '#f59e0b';
        const estadoIcon = prod.estado === 'PUBLICADO' ? 'check-circle' : 'clock';
        
        document.getElementById('detalle-producto').innerHTML = `
            <div class="detalle-header">
                <h2><i class="fas fa-box-open"></i> ${prod.nombre}</h2>
            </div>
            <div class="detalle-contenido">
                <div class="detalle-grid">
                    <div>
                        <div class="producto-imagen" style="height: 300px; margin-bottom: 1rem;">
                            ${prod.miniatura_disponible
                                ? `<img src="${API_URL}/productos/${id}/imagen" alt="${prod.nombre}" style="width:100%; height:100%; object-fit:contain;">`
                                : '<i class="fas fa-box" style="font-size: 4rem;"></i>'}
                        </div>
                    </div>
                    <div>
                        <div class="detalle-meta">
                            <div class="meta-item">
                                <div class="meta-label">Precio</div>
                                <div class="meta-valor">$${prod.precio.toFixed(2)}</div>
                            </div>
                            <div class="meta-item">
                                <div class="meta-label">Código</div>
                                <div class="meta-valor">${prod.codigo}</div>
                            </div>
                            <div class="meta-item">
                                <div class="meta-label">Categoría</div>
                                <div class="meta-valor">${prod.categoria}</div>
                            </div>
                            <div class="meta-item">
                                <div class="meta-label">Estado</div>
                                <div class="meta-valor">
                                    <i class="fas fa-${estadoIcon}" style="color: ${estadoColor}; margin-right: 0.5rem;"></i>
                                    ${prod.estado}
                                </div>
                            </div>
                        </div>
                        <div style="margin-top: 1rem;">
                            <h3 style="margin-bottom: 0.5rem; color: #1f2937;">Descripción</h3>
                            <p style="color: #6b7280; line-height: 1.6;">${prod.descripcion}</p>
                        </div>
                    </div>
                </div>
                ${atributosHTML}
            </div>
        `;
        
        document.getElementById('vista-detalle').classList.add('activa');
        document.querySelectorAll('.vista').forEach(v => {
            if (v.id !== 'vista-detalle') v.classList.remove('activa');
        });
    } catch (e) {
        console.error('Error cargando detalle:', e);
    }
}

// REGISTRAR PRODUCTO
document.getElementById('formProducto')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const codigo = document.getElementById('codigo').value;
    const nombre = document.getElementById('nombre').value;
    const descripcion = document.getElementById('descripcion').value;
    const precio = parseFloat(document.getElementById('precio').value);
    const categoria_id = parseInt(document.getElementById('categoria').value);
    const imagen = document.getElementById('imagen').files[0];
    
    const mensaje = document.getElementById('mensaje');
    mensaje.className = '';
    
    try {
        // Crear producto
        const res1 = await fetch(`${API_URL}/productos`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                codigo, nombre, descripcion, precio, categoria_id,
                atributos: {prueba: 'si'}
            })
        });
        
        if (!res1.ok) {
            const err = await res1.json();
            mostrarMensaje('❌ ' + (err.error || 'Error creando producto'), 'error');
            return;
        }
        
        const data1 = await res1.json();
        const producto_id = data1.producto_id;
        
        // Si hay imagen, subirla
        if (imagen) {
            const formData = new FormData();
            formData.append('file', imagen);
            
            const res2 = await fetch(`${API_URL}/productos/${producto_id}/imagen`, {
                method: 'POST',
                body: formData
            });
            
            const data2 = await res2.json();
            
            // El endpoint responde 200 tambien cuando la Lambda no logra
            // generar la miniatura, asi que hay que mirar el estado real.
            if (!res2.ok) {
                mostrarMensaje('⚠️ Imagen: ' + (data2.error || 'Error subiendo imagen'), 'error');
            } else if (data2.estado !== 'PUBLICADO') {
                mostrarMensaje(
                    `⚠️ Producto #${producto_id} creado pero la imagen no se procesó ` +
                    `(${data2.estado_procesamiento || 'ERROR'}). ` +
                    `Reintenta desde el detalle del producto.`,
                    'error'
                );
            } else {
                mostrarMensaje(`✅ Producto #${producto_id} registrado y publicado exitosamente`, 'exito');
            }
        } else {
            mostrarMensaje(`✅ Producto #${producto_id} registrado (sin imagen - estado: PENDIENTE)`, 'exito');
        }
        
        document.getElementById('formProducto').reset();
        setTimeout(() => {
            mostrarVista('catalogo');
        }, 2000);
        
    } catch (e) {
        mostrarMensaje('❌ Error: ' + e.message, 'error');
    }
});

function mostrarMensaje(texto, tipo) {
    const msg = document.getElementById('mensaje');
    msg.textContent = texto;
    msg.className = `mensaje-alert ${tipo}`;
}

// RECARGAR AUTOMÁTICO
setInterval(() => {
    if (document.getElementById('vista-catalogo').classList.contains('activa')) {
        cargarCatalogo();
    }
}, 5000);

// INICIALIZAR
document.addEventListener('DOMContentLoaded', () => {
    cargarCategorias();
    cargarCatalogo();
});