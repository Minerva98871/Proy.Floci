# Etapa 7 — Manifiestos de Kubernetes para el despliegue de Lomax SA
#
# El proxy sigue siendo la unica entrada de usuarios. Los upstreams cambian de
# nombre respecto a Docker Compose (aqui son Services del clúster), pero la
# imagen del proxy es la misma: su configuracion es una plantilla que el
# entrypoint de nginx completa con las variables LOMAX_BACKEND y
# LOMAX_FRONTEND.
#
# RDS, DynamoDB, S3 y Lambda quedan FUERA del clúster. Son servicios
# gestionados y por eso sobreviven a que un Pod muera, que es lo que exige la
# E7.
#
# Valores sustituidos por scripts/stage7_eks.ps1 antes de aplicar:
#   __IMAGE_TAG__        etiqueta publicada en la Etapa 6
#   __AWS_ENDPOINT__     endpoint de los servicios AWS visto desde el clúster
#   __RDS_HOST__         host de MySQL visto desde el clúster
#   __RDS_PORT__         puerto de MySQL visto desde el clúster
