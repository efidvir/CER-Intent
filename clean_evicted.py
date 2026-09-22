import os
import subprocess

out = subprocess.check_output(['/snap/microk8s/5872/kubectl', '--kubeconfig=/tmp/mykubeconfig', 'get', 'pods', '-n', 'default', '--no-headers']).decode()
for line in out.splitlines():
    if 'Evicted' in line:
        pod = line.split()[0]
        print(f"Deleting {pod}...")
        subprocess.run(['/snap/microk8s/5872/kubectl', '--kubeconfig=/tmp/mykubeconfig', 'delete', 'pod', pod, '-n', 'default'])
