# ETSI TeraFlowSDN Upstream Contribution Guide

## 1. Prerequisites

1. **ETSI GitLab Account**: Register at [https://labs.etsi.org/](https://labs.etsi.org/).
2. **Contributor Agreement**: Ensure Ceragon Networks Ltd. has signed the ETSI OSG TeraFlowSDN Contributor License Agreement (CLA) or is a member of the ETSI TeraFlowSDN Open Source Group.
3. **Git Configuration**:
   ```bash
   git config --global user.name "Your Name"
   git config --global user.email "your.name@ceragon.com"
   ```

---

## 2. Git Workflow for Upstream Merge Request (MR)

### Step 1: Fork and Clone
Clone your fork on GitHub or ETSI GitLab:
```bash
git clone https://github.com/efidvir/teraflowsdn.git
cd teraflowsdn
git remote add upstream https://labs.etsi.org/rep/tfs/controller.git
git fetch upstream
```

### Step 2: Switch to Feature Branch
```bash
git checkout -b feat/ceragon-transport-driver upstream/master
```

### Step 3: Apply the Contribution
The Ceragon driver files are organized as follows:
* `src/device/service/drivers/ceragon/` — Driver implementation & 51 YANG schemas
* `proto/context.proto` — `DEVICEDRIVER_CERAGON = 22;`
* `src/common/DeviceTypes.py` — `CERAGON_WIRELESS`
* `src/device/service/drivers/__init__.py` — Registration in `DRIVERS` list
* `src/device/tests/test_driver_ceragon.py` — Unit test suite
* `manifests/ceragon_mh_t261_descriptor.json` — Sample onboarding descriptor
* `docs/CERAGON_DRIVER_SPECIFICATION.md` — Driver specification

### Step 4: Commit with DCO (Signed-off-by)
ETSI TeraFlowSDN enforces the Developer Certificate of Origin (DCO):
```bash
git add proto/context.proto src/common/DeviceTypes.py src/device/
git commit -s -m "feat(device): add Ceragon wireless transport Southbound REST driver"
```
*(The `-s` flag automatically attaches `Signed-off-by: Your Name <your.name@ceragon.com>`)*.

### Step 5: Push and Open Merge Request
```bash
git push -u origin feat/ceragon-transport-driver
```
Then navigate to:
[https://labs.etsi.org/rep/tfs/controller/-/merge_requests/new](https://labs.etsi.org/rep/tfs/controller/-/merge_requests/new)
* **Source branch**: `feat/ceragon-transport-driver`
* **Target branch**: `master`
* **Title**: `feat(device): Add Ceragon Wireless Transport REST Driver`
* **Description**: Reference `docs/CERAGON_DRIVER_SPECIFICATION.md`.
