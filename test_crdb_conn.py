import socket

for ip in ["169.254.1.1", "10.20.120.84", "172.17.0.1", "10.1.17.1"]:
    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect((ip, 26257))
        print("SUCCESS connecting to", ip)
        s.close()
    except Exception as e:
        print("Failed", ip, ":", e)
