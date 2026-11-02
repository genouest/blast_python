# ---- Build stage: build Python wheels ----
FROM python:3.13-slim AS build

WORKDIR /wheels
COPY requirements.txt /requirements.txt
RUN pip wheel --no-cache-dir --wheel-dir=/wheels -r /requirements.txt

# ---- Runtime stage ----
FROM python:3.13-slim

WORKDIR /srv/blast
# Install from the prebuilt wheels only.
COPY requirements.txt /requirements.txt
RUN --mount=type=bind,from=build,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links=/wheels -r /requirements.txt

# Copy the application.
COPY app ./app
COPY bin ./bin
COPY config ./config
ADD /scripts/ /scripts/

# Install slurm
ADD apt_genouest_priority /etc/apt/preferences.d/apt_genouest_priority
RUN echo "deb [trusted=yes] https://apt.genouest.org/trixie/ trixie main" > /etc/apt/sources.list.d/slurm_genouest.list \
 && apt-get -q update \
 && DEBIAN_FRONTEND=noninteractive apt-get -yq install \
     git libslurm42t64 "slurm-client=24.11.5*" munge locales locales-all \
 && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8
RUN sed -i -e "s/# $LANG.*/$LANG UTF-8/" /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    update-locale LANG=$LANG

ENV SLURMGID='992' \
    SLURMUID='992' \
    MUNGEGID='991' \
    MUNGEUID='991' \
    DRMAA_LIBRARY_PATH='/etc/slurm/drmaa/lib/libdrmaa.so.1'

RUN mkdir -p /var/spool/slurmctld /var/spool/slurmd /var/run/slurm /var/log/slurm /run/munge && \
    chown -R slurm:slurm /var/spool/slurmctld /var/spool/slurmd /var/run/slurm /var/log/slurm && \
    chmod 755 /var/spool/slurmctld /var/spool/slurmd /var/run/slurm /var/log/slurm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BANKS_CONFIG=/srv/blast/config/banks.yml \
    LINKS_CONFIG=/srv/blast/config/links.yml \
    APP_USER='blast' \
    APP_GROUP='blast' \
    UID='' \
    GID=''

EXPOSE 8000

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh


ENTRYPOINT ["/entrypoint.sh"]
