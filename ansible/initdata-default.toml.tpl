# NOTE: PodVMs run in separate VMs outside the cluster network, so they cannot
# resolve cluster-internal service DNS (*.svc.cluster.local). Therefore, we must
# use the external KBS route even for same-cluster deployments.
# For multi-cluster deployments, this also points to the trusted cluster's KBS.

algorithm = "sha256"
version = "0.1.0"

[data]
"aa.toml" = '''
[token_configs]
[token_configs.coco_as]
url = "https://kbs.{{ hub_domain }}"

[token_configs.kbs]
url = "https://kbs.{{ hub_domain }}"
cert = """{{ trustee_cert }}"""
'''

"cdh.toml"  = '''
socket = 'unix:///run/confidential-containers/cdh.sock'
credentials = []

[kbc]
name = "cc_kbc"
url = "https://kbs.{{ hub_domain }}"
kbs_cert = """{{ trustee_cert }}"""

[image]
# Container image signature verification policy
# Options: insecure, reject, signed (configured via coco.imageSecurityPolicy in values)
image_security_policy_uri = "kbs:///default/security-policy/{{ image_security_policy }}"
'''

"policy.rego" = '''
package agent_policy

import future.keywords.in
import future.keywords.if
import future.keywords.every

default AddARPNeighborsRequest := true
default AddSwapRequest := true
default CloseStdinRequest := true
default CopyFileRequest := true
default CreateContainerRequest := true
default CreateSandboxRequest := true
default DestroySandboxRequest := true
default GetMetricsRequest := true
default GetOOMEventRequest := true
default GuestDetailsRequest := true
default ListInterfacesRequest := true
default ListRoutesRequest := true
default MemHotplugByProbeRequest := true
default OnlineCPUMemRequest := true
default PauseContainerRequest := true
default PullImageRequest := true
default ReadStreamRequest := true
default RemoveContainerRequest := true
default RemoveStaleVirtiofsShareMountsRequest := true
default ReseedRandomDevRequest := true
default ResumeContainerRequest := true
default SetGuestDateTimeRequest := true
default SignalProcessRequest := true
default StartContainerRequest := true
default StartTracingRequest := true
default StatsContainerRequest := true
default StopTracingRequest := true
default TtyWinResizeRequest := true
default UpdateContainerRequest := true
default UpdateEphemeralMountsRequest := true
default UpdateInterfaceRequest := true
default UpdateRoutesRequest := true
default WaitProcessRequest := true
default ExecProcessRequest := false
default SetPolicyRequest := true
default WriteStreamRequest := false
'''