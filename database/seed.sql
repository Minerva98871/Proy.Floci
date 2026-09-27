USE lomax_catalogo;

INSERT INTO Categorias (categoria_id, nombre) VALUES
  (1, 'Electrónica'),
  (2, 'Hogar'),
  (3, 'Oficina'),
  (4, 'Accesorios'),
  (5, 'Computación')
ON DUPLICATE KEY UPDATE nombre = VALUES(nombre);

INSERT INTO Productos (codigo, nombre, descripcion, precio, categoria_id, estado) VALUES
  ('TEC001', 'Teclado Mecanico RGB', 'Teclado mecanico con iluminacion RGB y conexion USB.', 280.00, 1, 'PUBLICADO'),
  ('TEC002', 'Mouse Inalambrico', 'Mouse inalambrico ergonomico para uso diario.', 95.00, 1, 'PUBLICADO'),
  ('TEC003', 'Monitor 24 Pulgadas', 'Monitor Full HD de 24 pulgadas.', 1250.00, 1, 'PUBLICADO'),
  ('TEC004', 'Audifonos Bluetooth', 'Audifonos inalambricos con conexion Bluetooth.', 350.00, 1, 'PUBLICADO'),
  ('TEC005', 'Webcam HD', 'Camara web HD para videoconferencias.', 220.00, 1, 'PUBLICADO'),
  ('TEC006', 'Parlante Bluetooth', 'Parlante portatil con conexion Bluetooth.', 180.00, 1, 'PUBLICADO'),
  ('TEC007', 'Memoria USB 128GB', 'Unidad de almacenamiento USB de 128 GB.', 110.00, 1, 'PUBLICADO'),
  ('HOG001', 'Lampara LED', 'Lampara LED de escritorio con bajo consumo.', 85.00, 2, 'PUBLICADO'),
  ('HOG002', 'Enchufe Inteligente', 'Enchufe inteligente para control de dispositivos.', 120.00, 2, 'PUBLICADO'),
  ('HOG003', 'Camara de Seguridad', 'Camara de seguridad para interiores.', 420.00, 2, 'PUBLICADO'),
  ('HOG004', 'Reloj Digital', 'Reloj digital con pantalla LED.', 150.00, 2, 'PUBLICADO'),
  ('HOG005', 'Aspiradora Robot', 'Aspiradora robot para limpieza automatica.', 1850.00, 2, 'PUBLICADO'),
  ('HOG006', 'Bascula Digital', 'Bascula digital con pantalla LCD.', 130.00, 2, 'PUBLICADO'),
  ('HOG007', 'Cargador Universal', 'Cargador universal para dispositivos electronicos.', 100.00, 2, 'PUBLICADO'),
  ('OFI001', 'Impresora Multifuncion', 'Impresora multifuncion con escaner y copiadora.', 1450.00, 3, 'PUBLICADO'),
  ('OFI002', 'Calculadora Cientifica', 'Calculadora cientifica para oficina y estudio.', 95.00, 3, 'PUBLICADO'),
  ('OFI003', 'Proyector HD', 'Proyector HD para presentaciones.', 2300.00, 3, 'PUBLICADO'),
  ('OFI004', 'Tablet Digitalizadora', 'Tablet digitalizadora para diseño grafico.', 680.00, 3, 'PUBLICADO'),
  ('OFI005', 'Lector de Codigo', 'Lector de codigos de barras para oficina.', 450.00, 3, 'PUBLICADO'),
  ('OFI006', 'Disco Externo 1TB', 'Disco externo USB de 1 TB.', 520.00, 3, 'PUBLICADO')
ON DUPLICATE KEY UPDATE
  nombre = VALUES(nombre),
  descripcion = VALUES(descripcion),
  precio = VALUES(precio),
  categoria_id = VALUES(categoria_id),
  estado = VALUES(estado);