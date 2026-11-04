FROM postgres:18@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6
RUN apt-get update && apt-get install -y --no-install-recommends pgbouncer=1.26.1-1.pgdg13+1 && rm -rf /var/lib/apt/lists/*
USER postgres
ENTRYPOINT ["pgbouncer"]
CMD ["/etc/pgbouncer.ini"]
