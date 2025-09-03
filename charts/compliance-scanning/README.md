# OpenShift Compliance Scanning ArgoCD Helm Chart

This Helm chart deploys OpenShift Compliance Operator resources in a negative sync-wave for Argo to perform compliance hardening of an OpenShift cluster using the ocp4-moderate profile with automatic remediation enabled.

## Overview

This chart creates the following resources:
- **ScanSetting**: Configures scanning behavior with auto-remediation enabled
- **ScanSettingBinding**: Binds the ScanSetting to the ocp4-moderate compliance profile
- **PersistentVolumeClaim**: Stores compliance scan results
- **Pod**: Results viewer pod to access and examine scan results

## Prerequisites

- OpenShift 4.17+ cluster
- Compliance Operator installed (included in the pattern)
- Sufficient storage for scan results (default: 2Gi)

## Configuration

### Key Features

- **Automatic Remediation**: Enabled by default with `autoApplyRemediations: true` and `default-auto-apply` annotation
- **ocp4-moderate Profile**: NIST 800-53 Moderate-Impact Baseline for Red Hat OpenShift Container Platform 4
- **Persistent Storage**: Scan results are stored in a PVC for later analysis
- **Results Access**: Dedicated pod with shell access to examine scan results

### Values Configuration

Key configuration options in `values.yaml`:

```yaml
compliance:
  scanSetting:
    autoApplyRemediations: true  # Enable automatic remediation
    schedule: ""                 # Manual trigger (can be set to cron)
    
  scanSettingBinding:
    profiles:
      - name: "ocp4-moderate"    # Compliance profile
        kind: "Profile"
        
  storage:
    enabled: true
    pvc:
      size: "2Gi"               # Storage for results
      
  resultsViewer:
    enabled: true                # Pod to access results
```

## Usage

### Accessing Scan Results

**Via Results Viewer Pod**:
   ```bash
   oc exec -n openshift-compliance compliance-results-viewer -- ls /compliance-results
   oc exec -it -n openshift-compliance compliance-results-viewer -- bash
   ```

### Monitoring Compliance Scans

1. **Check Scan Status**:
   ```bash
   oc get compliancescans -n openshift-compliance
   oc get compliancesuites -n openshift-compliance
   ```

2. **View Remediation Status**:
   ```bash
   oc get complianceremediations -n openshift-compliance
   ```

3. **Check for Non-Compliance**:
   ```bash
   oc get compliancecheckresults -n openshift-compliance
   ```

## Security Considerations

- **Automatic Remediation**: This chart enables automatic application of remediations.
- **Cluster Impact**: Some remediations may require node reboots or service restarts.
- **Profile Selection**: The ocp4-moderate profile applies NIST 800-53 controls suitable for moderate-impact systems.

## Troubleshooting

### Common Issues

1. **Scanner Pods Failing**: Check node tolerations and resource constraints
2. **Storage Issues**: Verify StorageClass availability and permissions
3. **Remediation Failures**: Review compliance operator logs and node conditions

### Useful Commands

```bash
# View compliance operator logs
oc logs -n openshift-compliance deployment/compliance-operator

# Check profile status
oc get profiles.compliance -n openshift-compliance

# View detailed scan results
oc describe compliancescan -n openshift-compliance
```

## Customization

### Disabling Auto-Remediation

To disable automatic remediation:
```yaml
compliance:
  scanSetting:
    autoApplyRemediations: false
```

### Scheduling Scans

To run scans on a schedule (daily at 2 AM):
```yaml
compliance:
  scanSetting:
    schedule: "0 2 * * *"
```

### Custom Storage

To use a specific storage class:
```yaml
compliance:
  storage:
    pvc:
      storageClass: "fast-ssd"
      size: "20Gi"
```

## References

- [OpenShift Compliance Operator Documentation](https://docs.openshift.com/container-platform/latest/security/compliance_operator/compliance-operator-understanding.html)
- [NIST 800-53 Controls](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)
- [ocp4-moderate Profile Details](https://www.open-scap.org/security-policies/choosing-policy/)
