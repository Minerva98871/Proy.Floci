CREATE DATABASE IF NOT EXISTS lomax_catalogo
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE lomax_catalogo;

CREATE TABLE IF NOT EXISTS Categorias (
  categoria_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  nombre VARCHAR(100) NOT NULL,
  PRIMARY KEY (categoria_id),
  UNIQUE KEY uq_categorias_nombre (nombre)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Productos (
  producto_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  codigo VARCHAR(40) NOT NULL,
  nombre VARCHAR(160) NOT NULL,
  descripcion TEXT NOT NULL,
  precio DECIMAL(10,2) NOT NULL,
  categoria_id INT UNSIGNED NOT NULL,
  fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  estado ENUM('PENDIENTE', 'PUBLICADO') NOT NULL DEFAULT 'PENDIENTE',
  PRIMARY KEY (producto_id),
  UNIQUE KEY uq_productos_codigo (codigo),
  KEY ix_productos_categoria_estado (categoria_id, estado),
  CONSTRAINT chk_productos_precio_no_negativo CHECK (precio >= 0),
  CONSTRAINT fk_productos_categoria
    FOREIGN KEY (categoria_id) REFERENCES Categorias (categoria_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB;