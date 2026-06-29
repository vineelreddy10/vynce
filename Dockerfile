# Dockerfile — builds custom bench image with all 3 apps
# Uses the Frappe Docker base image (Frappe v16 + ERPNext)
FROM frappe/erpnext:v16

ARG GITLAB_PAT
ARG VYNCE_BRANCH=main
ARG DFP_BRANCH=main

# Install custom apps
RUN bench get-app https://github.com/vineelreddy10/vynce.git --branch ${VYNCE_BRANCH} && \
    bench get-app https://gitlab-ci-token:${GITLAB_PAT}@gitlab.asakta.com/asakta/frappe_dfp_minio.git --branch ${DFP_BRANCH}

