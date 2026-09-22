import subprocess
import concurrent.futures

print("Fetching list of zombie pods...")
cmd = ["/snap/microk8s/5872/kubectl", "--kubeconfig=/tmp/mykubeconfig", "get", "pods", "-n", "default", "--no-headers"]
out = subprocess.check_output(cmd).decode()

to_delete = []
for line in out.splitlines():
    parts = line.split()
    if len(parts) >= 3:
        name = parts[0]
        status = parts[2]
        if status in ("ContainerStatusUnknown", "Evicted", "Error", "Unknown"):
            to_delete.append(name)

print(f"Found {len(to_delete)} zombie pods to delete.")

def delete_batch(batch):
    cmd = ["/snap/microk8s/5872/kubectl", "--kubeconfig=/tmp/mykubeconfig", "delete", "pod", "-n", "default", "--force", "--grace-period=0"] + batch
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# Delete in batches of 50
batch_size = 50
batches = [to_delete[i:i + batch_size] for i in range(0, len(to_delete), batch_size)]

print(f"Deleting in {len(batches)} batches...")
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(delete_batch, b) for b in batches]
    completed = 0
    for f in concurrent.futures.as_completed(futures):
        completed += 1
        if completed % 10 == 0 or completed == len(batches):
            print(f"Progress: {completed}/{len(batches)} batches processed")

print("Cleanup complete!")
