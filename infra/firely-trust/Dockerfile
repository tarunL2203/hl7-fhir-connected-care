FROM firely-learning-tls:local
USER root
COPY local-rootCA.crt /usr/local/share/ca-certificates/firely-learning-local.crt
RUN update-ca-certificates
USER firely:firely
