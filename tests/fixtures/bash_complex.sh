#!/usr/bin/env bash
# Deployment script with heredocs and conditionals.

set -euo pipefail

source /etc/profile
export DEPLOY_ENV="${DEPLOY_ENV:-staging}"
export VERSION="1.2.3"

usage() {
    cat <<USAGE
Usage: $0 [--env ENV] [--version V]

Options:
  --env       Deploy environment (staging|prod)
  --version   Version tag to deploy
USAGE
}

log() {
    local level="$1"; shift
    printf "[%s] [%s] %s\n" "$(date -Is)" "$level" "$*"
}

check_prerequisites() {
    if ! command -v kubectl >/dev/null 2>&1; then
        log ERROR "kubectl is required"
        return 1
    fi
    if [[ -z "${KUBE_CONTEXT:-}" ]]; then
        log ERROR "KUBE_CONTEXT must be set"
        return 1
    fi
    return 0
}

deploy() {
    local manifest=/tmp/deploy.yaml
    cat <<MANIFEST > "$manifest"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: webapp
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: app
          image: webapp:${VERSION}
MANIFEST
    kubectl apply -f "$manifest"
    rm -f "$manifest"
}

cleanup() {
    log INFO "cleaning up"
    kubectl delete pods --field-selector=status.phase=Failed
}

main() {
    case "${1:-deploy}" in
        deploy)
            check_prerequisites && deploy
            ;;
        cleanup)
            cleanup
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

main "$@"
