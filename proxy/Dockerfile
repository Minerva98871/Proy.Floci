FROM nginx:1.27-alpine

# La configuracion es una plantilla: el entrypoint de nginx la procesa con
# envsubst al arrancar y escribe /etc/nginx/nginx.conf. Asi una sola imagen
# sirve tanto en Docker Compose (upstreams backend/frontend) como en
# Kubernetes (upstreams lomax-backend/lomax-frontend), sin reconstruirla.
#
# NGINX_ENVSUBST_FILTER limita la sustitucion a las variables LOMAX_*. Sin el
# filtro, envsubst tambien vaciaria las variables propias de nginx ($host,
# $remote_addr, $scheme...) y el proxy dejaria de enviar esas cabeceras.
ENV NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx
ENV NGINX_ENVSUBST_FILTER="^LOMAX_"

COPY nginx.conf.template /etc/nginx/templates/nginx.conf.template

# Valores por defecto para Docker Compose; Kubernetes los sobrescribe.
ENV LOMAX_BACKEND=backend:5000
ENV LOMAX_FRONTEND=frontend:80

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
