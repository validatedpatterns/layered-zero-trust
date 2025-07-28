#!/bin/bash

export EXTERNAL_TEST="true"
export PATTERN_NAME="LayeredZeroTrust"
export PATTERN_SHORTNAME="layeredzerotrust"

if [ -z "${KUBECONFIG}" ]; then
    echo "No kubeconfig file set for hub cluster"
    exit 1
fi

if [ -z "${INFRA_PROVIDER}" ]; then
    echo "INFRA_PROVIDER is not defined"
    exit 1
fi

if [ -z "${WORKSPACE}" ]; then
    export WORKSPACE=/tmp
fi

pytest -lv --disable-warnings test_subscription_status_hub.py --kubeconfig $KUBECONFIG --junit-xml $WORKSPACE/test_subscription_status_hub.xml

pytest -lv --disable-warnings test_validate_hub_site_components.py --kubeconfig $KUBECONFIG --junit-xml $WORKSPACE/test_validate_hub_site_components.xml

pytest -lv --disable-warnings test_validate_layer_0.py --kubeconfig $KUBECONFIG --junit-xml $WORKSPACE/test_validate_layer_0.xml

pytest -lv --disable-warnings test_validate_layer_0_keycloak.py --kubeconfig $KUBECONFIG --junit-xml $WORKSPACE/test_validate_layer_0_keycloak.xml

python3 create_ci_badge.py
